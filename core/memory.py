"""
HAANA Memory – Mem0 + Qdrant Wrapper

Drei Scopes mit separaten Qdrant-Collections:
  alice_memory  – Alicees persönliche Erinnerungen
  bob_memory   – Bobs persönliche Erinnerungen
  bnd_memory    – gemeinsamer Haushaltskontext

LLM für Memory-Extraktion: Ollama (kein API-Key nötig).
Embedder: Ollama bge-m3, Fallback HuggingFace wenn OLLAMA_URL fehlt.

Wenn kein Ollama verfügbar: Memory deaktiviert mit Warn-Log.
"""

import os
import logging
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
    Gibt None zurück wenn keine LLM-Backend verfügbar ist.

    Kein API-Key nötig: LLM und Embeddings laufen über Ollama.
    Fallback Embedder: HuggingFace (kein LLM-Fallback – ohne LLM kein Memory).
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

    # Modell für Memory-Extraktion (8B+ empfohlen – kleinere Modelle liefern oft
    # keine validen Strings für Mem0s Extraktions-Schema)
    memory_llm = os.environ.get("HAANA_MEMORY_MODEL", "ministral-3:8b")

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


class HaanaMemory:
    def __init__(self, instance_name: str):
        self.instance = instance_name
        self.write_scopes = _WRITE_SCOPES.get(instance_name, set())
        self.read_scopes = _READ_SCOPES.get(instance_name, set())

        # Lazy-loaded Mem0-Instanzen pro Scope (None = nicht verfügbar)
        self._memories: dict[str, object] = {}

        logger.info(
            f"[{instance_name}] Memory init | "
            f"write={sorted(self.write_scopes)} | "
            f"read={sorted(self.read_scopes)}"
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
                    # Mem0 v1.0+: Text unter Schlüssel "memory"
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

        # Nach Score sortieren, maximal 10 Treffer
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
        Speichert Konversation in einem Scope.

        messages: [{"role": "user"|"assistant", "content": "..."}]
        scope: muss in write_scopes liegen
        Gibt True zurück wenn erfolgreich.
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
            # infer=True: LLM (ministral-3:8b) extrahiert kompakte Fakten aus der
            # Konversation bevor sie embedded werden. 8B-Modelle liefern valide Strings
            # für Mem0s Extraktions-Schema (im Gegensatz zu qwen2.5:1.5b).
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

    def add_conversation(
        self,
        user_message: str,
        assistant_response: str,
        scope: Optional[str] = None,
    ):
        """
        Speichert eine abgeschlossene Konversation.
        scope=None → Scope aus Agentenantwort lesen (Agent benennt ihn explizit),
                     Fallback: persönlicher Scope der Instanz.
        ha-assist und ha-advanced schreiben nie (write_scopes leer).
        """
        if not self.write_scopes:
            return

        if scope is None:
            import re
            # Agent benennt den Scope explizit in seiner Antwort
            # ("→ bnd_memory", "in alice_memory gespeichert", …)
            match = re.search(
                r"\b(alice_memory|bob_memory|bnd_memory)\b",
                assistant_response,
            )
            if match and match.group(1) in self.write_scopes:
                scope = match.group(1)
                logger.debug(
                    f"[{self.instance}] Scope aus Agentenantwort: '{scope}'"
                )
            else:
                # Fallback: persönlicher Scope (kein bnd_memory)
                personal = {s for s in self.write_scopes if s != "bnd_memory"}
                scope = next(iter(personal), next(iter(self.write_scopes)))
                logger.debug(
                    f"[{self.instance}] Scope nicht erkannt, Fallback: '{scope}'"
                )

        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ]
        self.add(messages, scope)
