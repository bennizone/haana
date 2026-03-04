"""
HAANA Memory – Mem0 + Qdrant Wrapper

Drei Scopes mit separaten Qdrant-Collections:
  alice_memory  – Alicees persönliche Erinnerungen
  bob_memory   – Bobs persönliche Erinnerungen
  bnd_memory    – gemeinsamer Haushaltskontext

LLM für Memory-Extraktion: Ollama (kein API-Key nötig).
Embedder: Ollama bge-m3, Fallback HuggingFace wenn OLLAMA_URL fehlt.
Wenn kein Ollama verfügbar: Memory deaktiviert mit Warn-Log.

Sliding Window:
  Letzte N Nachrichten / M Minuten bleiben im lokalen Window-Buffer.
  Einträge die das Window verlassen werden async zu Qdrant extrahiert.
  Bei Extraktions-Fehler bleibt der Eintrag im Window (kein Datenverlust).

Konfiguration via Env:
  HAANA_WINDOW_SIZE     – max Nachrichten im Window (Standard: 20)
  HAANA_WINDOW_MINUTES  – max Alter in Minuten (Standard: 60)
"""

import asyncio
import os
import logging
import time
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

VALID_SCOPES = {"alice_memory", "bob_memory", "bnd_memory"}

# Schreibberechtigungen pro Instanz
_WRITE_SCOPES: dict[str, set[str]] = {
    "alice":       {"alice_memory", "bnd_memory"},
    "bob":        {"bob_memory", "bnd_memory"},
    "ha-assist":   set(),
    "ha-advanced": set(),
}

# Leseberechtigungen pro Instanz
_READ_SCOPES: dict[str, set[str]] = {
    "alice":       {"alice_memory", "bnd_memory"},
    "bob":        {"bob_memory", "bnd_memory"},
    "ha-assist":   {"alice_memory", "bob_memory", "bnd_memory"},
    "ha-advanced": {"alice_memory", "bob_memory", "bnd_memory"},
}


def _get_qdrant_host_port() -> tuple[str, int]:
    """Parst QDRANT_URL in (host, port)."""
    url = os.environ.get("QDRANT_URL", "http://qdrant:6333")
    url = url.replace("https://", "").replace("http://", "")
    host, _, port_str = url.partition(":")
    port = int(port_str) if port_str else 6333
    return host, port


def _build_mem0_config(collection_name: str) -> Optional[dict]:
    """
    Erstellt vollständige Mem0-Konfiguration für einen Scope.
    Gibt None zurück wenn kein LLM-Backend verfügbar ist.
    """
    host, port = _get_qdrant_host_port()
    ollama_url = os.environ.get("OLLAMA_URL", "").strip()

    if not ollama_url:
        logger.warning(
            f"[{collection_name}] OLLAMA_URL nicht gesetzt. "
            "Memory-Extraktion erfordert ein lokales LLM. "
            "Memory für diesen Scope deaktiviert."
        )
        return None

    memory_llm = os.environ.get("HAANA_MEMORY_MODEL", "ministral-3-32k:3b")

    config = {
        "llm": {
            "provider": "ollama",
            "config": {
                "model": memory_llm,
                "ollama_base_url": ollama_url,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "bge-m3",
                "ollama_base_url": ollama_url,
                "embedding_dims": 1024,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection_name,
                "host": host,
                "port": port,
                "embedding_model_dims": 1024,
            },
        },
    }

    logger.debug(
        f"[{collection_name}] Mem0 config: "
        f"LLM={memory_llm} @ {ollama_url}, "
        f"Embedder=bge-m3, Qdrant={host}:{port}"
    )
    return config


# ── Sliding Window ─────────────────────────────────────────────────────────────

@dataclass
class _WindowEntry:
    user: str
    assistant: str
    scope: str
    timestamp: float = field(default_factory=time.monotonic)
    extracting: bool = False  # True = Hintergrund-Extraktion läuft gerade


class ConversationWindow:
    """
    Sliding Window für die lokale Konversationshistorie.

    Regeln:
      - Mindestens min_messages Einträge bleiben immer im Window
      - Einträge die weder in den letzten max_messages noch in den letzten
        max_age_minutes liegen → Overflow → async zu Qdrant extrahieren
      - Bei Extraktions-Fehler: Eintrag bleibt (kein Datenverlust)
    """

    def __init__(
        self,
        max_messages: int = 20,
        max_age_minutes: int = 60,
        min_messages: int = 5,
    ):
        self.max_messages = max_messages
        self.max_age_minutes = max_age_minutes
        self.min_messages = min_messages
        self._entries: list[_WindowEntry] = []

    def add(self, user: str, assistant: str, scope: str) -> list[_WindowEntry]:
        """Fügt Eintrag hinzu. Gibt Overflow-Kandidaten zurück."""
        self._entries.append(_WindowEntry(user=user, assistant=assistant, scope=scope))
        return self._get_overflow()

    def _get_overflow(self) -> list[_WindowEntry]:
        """
        Bestimmt Einträge die das Window verlassen sollen.
        Ein Eintrag verlässt das Window wenn er KEINER der drei Bedingungen entspricht:
          - in_count: unter den letzten max_messages
          - in_time:  jünger als max_age_minutes
          - in_min:   unter den letzten min_messages (Safety-Floor)
        """
        now = time.monotonic()
        max_age_sec = self.max_age_minutes * 60
        n = len(self._entries)
        overflow = []

        for i, entry in enumerate(self._entries):
            if entry.extracting:
                continue

            # Abstand vom neuesten Eintrag (0 = neuester)
            pos_from_newest = n - 1 - i

            in_count = pos_from_newest < self.max_messages
            in_time  = (now - entry.timestamp) <= max_age_sec
            in_min   = pos_from_newest < self.min_messages

            if not (in_count or in_time or in_min):
                entry.extracting = True
                overflow.append(entry)

        return overflow

    def mark_extracted(self, entry: _WindowEntry):
        """Entfernt erfolgreich extrahierten Eintrag."""
        try:
            self._entries.remove(entry)
        except ValueError:
            pass

    def mark_failed(self, entry: _WindowEntry):
        """Extraktion fehlgeschlagen – Eintrag bleibt im Window."""
        entry.extracting = False

    def size(self) -> int:
        return len(self._entries)


# ── HaanaMemory ────────────────────────────────────────────────────────────────

class HaanaMemory:
    def __init__(self, instance_name: str):
        self.instance = instance_name
        self.write_scopes = _WRITE_SCOPES.get(instance_name, set())
        self.read_scopes = _READ_SCOPES.get(instance_name, set())

        # Lazy-loaded Mem0-Instanzen pro Scope (None = nicht verfügbar)
        self._memories: dict[str, object] = {}

        # Sliding Window (Konfiguration aus Env)
        self._window = ConversationWindow(
            max_messages=int(os.environ.get("HAANA_WINDOW_SIZE", "20")),
            max_age_minutes=int(os.environ.get("HAANA_WINDOW_MINUTES", "60")),
            min_messages=5,
        )

        logger.info(
            f"[{instance_name}] Memory init | "
            f"write={sorted(self.write_scopes)} | "
            f"read={sorted(self.read_scopes)} | "
            f"window={self._window.max_messages}msg / "
            f"{self._window.max_age_minutes}min / min=5"
        )

    def _get_memory(self, scope: str):
        """Lazy-load einer Mem0 Memory-Instanz für einen Scope."""
        if scope not in self._memories:
            config = _build_mem0_config(scope)
            if config is None:
                self._memories[scope] = None
                return None

            try:
                from mem0 import Memory
                self._memories[scope] = Memory.from_config(config)
                logger.info(f"[{self.instance}] Memory-Instanz '{scope}' bereit.")
            except Exception as e:
                logger.error(
                    f"[{self.instance}] Memory-Init '{scope}' fehlgeschlagen: {e}",
                    exc_info=True,
                )
                self._memories[scope] = None

        return self._memories[scope]

    def _resolve_scope(self, assistant_response: str, scope: Optional[str]) -> str:
        """
        Bestimmt den Ziel-Scope für einen Memory-Write.
        Liest Scope aus Agentenantwort oder fällt auf persönlichen Scope zurück.
        """
        if scope is not None:
            return scope

        match = re.search(
            r"\b(alice_memory|bob_memory|bnd_memory)\b",
            assistant_response,
        )
        if match and match.group(1) in self.write_scopes:
            scope = match.group(1)
            logger.debug(f"[{self.instance}] Scope aus Agentenantwort: '{scope}'")
        else:
            personal = {s for s in self.write_scopes if s != "bnd_memory"}
            scope = next(iter(personal), next(iter(self.write_scopes)))
            logger.debug(f"[{self.instance}] Scope nicht erkannt, Fallback: '{scope}'")

        return scope

    def search(self, query: str, scopes: Optional[list[str]] = None) -> str:
        """
        Sucht in allen lesbaren Scopes nach relevantem Kontext.
        Gibt formatierten String zurück: "[scope] erinnerung\n..."
        Leerer String wenn nichts gefunden oder Memory nicht verfügbar.
        """
        if scopes is None:
            scopes = list(self.read_scopes)

        all_results: list[tuple[float, str, str]] = []

        for scope in scopes:
            if scope not in self.read_scopes:
                logger.warning(f"[{self.instance}] Lesezugriff auf '{scope}' verweigert.")
                continue

            mem = self._get_memory(scope)
            if mem is None:
                continue

            try:
                user_id = scope.replace("_memory", "")
                results = mem.search(query=query, user_id=user_id, limit=5)
                for r in results.get("results", []):
                    content = r.get("memory") or r.get("content", "")
                    score = float(r.get("score", 0))
                    if content:
                        all_results.append((score, scope, content))
            except Exception as e:
                logger.error(
                    f"[{self.instance}] Memory-Suche in '{scope}' fehlgeschlagen: {e}"
                )

        if not all_results:
            return ""

        all_results.sort(reverse=True)
        lines = [f"[{scope}] {content}" for _, scope, content in all_results[:10]]
        return "\n".join(lines)

    def add(
        self,
        messages: list[dict],
        scope: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Schreibt Konversation synchron in Mem0/Qdrant.
        Wird vom async Extraktions-Task im Thread-Executor aufgerufen.
        """
        if scope not in VALID_SCOPES:
            logger.error(f"[{self.instance}] Ungültiger Scope: '{scope}'")
            return False

        if scope not in self.write_scopes:
            logger.error(
                f"[{self.instance}] Schreibzugriff auf '{scope}' verweigert "
                f"(erlaubt: {sorted(self.write_scopes)})"
            )
            return False

        mem = self._get_memory(scope)
        if mem is None:
            return False

        try:
            user_id = scope.replace("_memory", "")
            result = mem.add(
                messages=messages,
                user_id=user_id,
                infer=True,
                metadata=metadata or {},
            )
            logger.info(
                f"[{self.instance}] Memory gespeichert | "
                f"scope={scope} | user_id={user_id} | result={result}"
            )
            return True
        except Exception as e:
            logger.error(
                f"[{self.instance}] Memory-Write in '{scope}' fehlgeschlagen: {e}",
                exc_info=True,
            )
            return False

    async def _extract_entry(self, entry: _WindowEntry):
        """
        Extrahiert einen Window-Eintrag async zu Qdrant.
        Läuft im Thread-Executor → blockiert den Event-Loop nicht.
        Bei Fehler: Eintrag bleibt im Window (kein Datenverlust).
        """
        messages = [
            {"role": "user",      "content": entry.user},
            {"role": "assistant", "content": entry.assistant},
        ]
        loop = asyncio.get_event_loop()
        try:
            success = await loop.run_in_executor(None, self.add, messages, entry.scope)
            if success:
                self._window.mark_extracted(entry)
                logger.debug(
                    f"[{self.instance}] Async-Extraktion OK | "
                    f"scope={entry.scope} | window={self._window.size()}"
                )
            else:
                self._window.mark_failed(entry)
                logger.warning(
                    f"[{self.instance}] Async-Extraktion fehlgeschlagen | "
                    f"scope={entry.scope} | Eintrag bleibt im Window"
                )
        except Exception as e:
            self._window.mark_failed(entry)
            logger.error(f"[{self.instance}] Async-Extraktion Fehler: {e}", exc_info=True)

    async def add_conversation_async(
        self,
        user_message: str,
        assistant_response: str,
        scope: Optional[str] = None,
    ):
        """
        Fügt Konversation zum Sliding Window hinzu und extrahiert Overflow async.

        Non-blocking: kehrt sofort zurück. Mem0-Write (LLM-Inferenz + Embedding)
        läuft als asyncio.Task im Hintergrund, ohne den Event-Loop zu blockieren.
        ha-assist / ha-advanced (keine write_scopes) → no-op.
        """
        if not self.write_scopes:
            return

        scope = self._resolve_scope(assistant_response, scope)
        overflow = self._window.add(user_message, assistant_response, scope)

        for entry in overflow:
            asyncio.create_task(self._extract_entry(entry))

        logger.debug(
            f"[{self.instance}] Window +1 | "
            f"scope={scope} | size={self._window.size()} | "
            f"overflow={len(overflow)}"
        )
