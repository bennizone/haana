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

Persistenz:
  Window wird nach jeder Nachricht als JSON gespeichert (data/context/).
  Beim Start: JSON laden → pending Einträge sofort extrahieren.
  Bei Absturz: maximal die letzte Nachricht geht verloren.

Konfiguration via Env:
  HAANA_WINDOW_SIZE     – max Nachrichten im Window (Standard: 20)
  HAANA_WINDOW_MINUTES  – max Alter in Minuten (Standard: 60)
"""

import asyncio
import json
import os
import logging
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
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
    # Wall-clock (time.time()) für Persistenz über Neustarts hinweg
    timestamp: float = field(default_factory=time.time)
    extracting: bool = False  # True = Hintergrund-Task läuft gerade


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
        now = time.time()
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

    # ── Persistenz ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialisiert Window-Zustand als dict (JSON-kompatibel)."""
        return {
            "version": 1,
            "saved_at": time.time(),
            "config": {
                "max_messages": self.max_messages,
                "max_age_minutes": self.max_age_minutes,
                "min_messages": self.min_messages,
            },
            "entries": [
                {
                    "user": e.user,
                    "assistant": e.assistant,
                    "scope": e.scope,
                    "timestamp": e.timestamp,
                    # War der Task aktiv als gespeichert wurde? → pending auf nächsten Start
                    "pending_extraction": e.extracting,
                }
                for e in self._entries
            ],
        }

    def from_dict(self, d: dict) -> list[_WindowEntry]:
        """
        Stellt Window-Zustand aus dict wieder her.
        Gibt Liste der Einträge zurück die sofort extrahiert werden sollen:
          - Einträge die beim letzten Speichern extracting=True waren
          - Einträge die jetzt durch Overflow das Window verlassen würden
        """
        self._entries.clear()
        immediately_pending: list[_WindowEntry] = []

        for item in d.get("entries", []):
            entry = _WindowEntry(
                user=item["user"],
                assistant=item["assistant"],
                scope=item["scope"],
                timestamp=item["timestamp"],
                extracting=False,
            )
            self._entries.append(entry)
            if item.get("pending_extraction", False):
                entry.extracting = True
                immediately_pending.append(entry)

        # Zusätzlich: Overflow aus aktuellem Stand neu berechnen
        # (z.B. wenn max_messages seit letztem Start verkleinert wurde)
        new_overflow = self._get_overflow()
        immediately_pending.extend(new_overflow)

        return immediately_pending


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

        # Tracking laufender Extraktions-Tasks (für flush_pending / shutdown)
        self._pending_tasks: set[asyncio.Task] = set()

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

    # ── Lesen ─────────────────────────────────────────────────────────────────

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

    # ── Schreiben (synchron, für Thread-Executor) ──────────────────────────────

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

    # ── Async Extraktion ───────────────────────────────────────────────────────

    def _track_task(self, task: asyncio.Task):
        """Registriert einen Task und entfernt ihn automatisch bei Abschluss."""
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

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
        loop = asyncio.get_running_loop()
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

    def _schedule_extraction(self, entry: _WindowEntry):
        """Erstellt und trackt einen Extraktions-Task."""
        task = asyncio.create_task(self._extract_entry(entry))
        self._track_task(task)

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
            self._schedule_extraction(entry)

        logger.debug(
            f"[{self.instance}] Window +1 | "
            f"scope={scope} | size={self._window.size()} | "
            f"overflow={len(overflow)} | pending_tasks={len(self._pending_tasks)}"
        )

    # ── Task-Verwaltung ────────────────────────────────────────────────────────

    def pending_count(self) -> int:
        """Anzahl laufender Extraktions-Tasks."""
        return len(self._pending_tasks)

    async def flush_pending(self, timeout: float = 30.0) -> int:
        """
        Wartet auf alle laufenden Extraktions-Tasks.
        Gibt Anzahl der Tasks zurück die nach timeout abgebrochen wurden.
        """
        if not self._pending_tasks:
            return 0

        tasks = set(self._pending_tasks)
        logger.info(f"[{self.instance}] Warte auf {len(tasks)} Extraktions-Tasks...")

        done, still_pending = await asyncio.wait(tasks, timeout=timeout)

        for task in still_pending:
            task.cancel()

        if still_pending:
            logger.warning(
                f"[{self.instance}] {len(still_pending)} Tasks nach {timeout}s abgebrochen"
            )

        return len(still_pending)

    # ── Persistenz ─────────────────────────────────────────────────────────────

    def save_context(self, path: Path):
        """
        Schreibt den aktuellen Window-Zustand als JSON.
        Wird nach jeder Nachricht aufgerufen → bei Absturz geht max. 1 Nachricht verloren.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = self._window.to_dict()
            # Atomares Schreiben via temp-Datei → kein korruptes JSON bei Absturz
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            logger.debug(
                f"[{self.instance}] Context gespeichert | "
                f"{self._window.size()} Einträge → {path}"
            )
        except Exception as e:
            logger.error(f"[{self.instance}] Context-Speichern fehlgeschlagen: {e}")

    async def load_context(self, path: Path) -> int:
        """
        Lädt Window-Zustand aus JSON und plant pending Einträge zur Extraktion ein.
        Gibt Anzahl der sofort gestarteten Extraktions-Tasks zurück.
        Kein Fehler wenn Datei nicht existiert (erster Start).
        """
        if not path.exists():
            logger.info(f"[{self.instance}] Kein gespeicherter Context gefunden ({path})")
            return 0

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[{self.instance}] Context-Laden fehlgeschlagen: {e}")
            return 0

        pending_entries = self._window.from_dict(data)

        for entry in pending_entries:
            self._schedule_extraction(entry)

        saved_at = data.get("saved_at", 0)
        age_min = (time.time() - saved_at) / 60

        logger.info(
            f"[{self.instance}] Context geladen | "
            f"{self._window.size()} Einträge | "
            f"gespeichert vor {age_min:.1f}min | "
            f"{len(pending_entries)} pending → sofortige Extraktion"
        )
        return len(pending_entries)
