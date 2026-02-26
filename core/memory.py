"""
HAANA Memory – Mem0 + Qdrant Wrapper

Drei Scopes mit separaten Qdrant-Collections:
  alice_memory  – Alicees persönliche Erinnerungen
  bob_memory   – Bobs persönliche Erinnerungen
  bnd_memory    – gemeinsamer Haushaltskontext

Schreib- und Leseberechtigungen sind pro Instanz definiert.
Alle Memory-Operationen werden geloggt (Scope, Ergebnis).
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


def _build_mem0_config(collection_name: str) -> tuple[dict, int]:
    """
    Erstellt vollständige Mem0-Konfiguration für einen Scope.
    Gibt (config_dict, embedding_dims) zurück.
    """
    host, port = _get_qdrant_host_port()
    ollama_url = os.environ.get("OLLAMA_URL", "").strip()

    if ollama_url:
        embedding_dims = 1024  # bge-m3
        embedder_cfg = {
            "provider": "ollama",
            "config": {
                "model": "bge-m3",
                "ollama_base_url": ollama_url,
                "embedding_dims": embedding_dims,
            },
        }
        logger.info(f"[{collection_name}] Embedder: Ollama bge-m3 @ {ollama_url}")
    else:
        embedding_dims = 384  # bge-small-en-v1.5
        embedder_cfg = {
            "provider": "huggingface",
            "config": {
                "model": "BAAI/bge-small-en-v1.5",
            },
        }
        logger.warning(
            f"[{collection_name}] OLLAMA_URL nicht gesetzt – "
            "verwende HuggingFace bge-small-en-v1.5 (lokal, langsamer)"
        )

    config = {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": os.environ.get("HAANA_MODEL", "claude-haiku-4-5-20251001"),
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        },
        "embedder": embedder_cfg,
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection_name,
                "host": host,
                "port": port,
                "embedding_model_dims": embedding_dims,
            },
        },
    }

    return config, embedding_dims


class HaanaMemory:
    def __init__(self, instance_name: str):
        self.instance = instance_name
        self.write_scopes = _WRITE_SCOPES.get(instance_name, set())
        self.read_scopes = _READ_SCOPES.get(instance_name, set())

        # Lazy-loaded Memory-Instanzen pro Scope
        self._memories: dict[str, object] = {}

        logger.info(
            f"[{instance_name}] Memory init | "
            f"write={sorted(self.write_scopes)} | "
            f"read={sorted(self.read_scopes)}"
        )

    def _get_memory(self, scope: str):
        """Lazy-load einer Mem0 Memory-Instanz für einen Scope."""
        if scope not in self._memories:
            try:
                from mem0 import Memory
                config, _ = _build_mem0_config(scope)
                self._memories[scope] = Memory.from_config(config)
                logger.info(f"[{self.instance}] Memory-Instanz '{scope}' initialisiert.")
            except Exception as e:
                logger.error(
                    f"[{self.instance}] Memory-Initialisierung '{scope}' fehlgeschlagen: {e}",
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
                # user_id = scope-Name ohne "_memory" Suffix
                user_id = scope.replace("_memory", "")
                results = mem.search(query=query, user_id=user_id, limit=5)
                for r in results.get("results", []):
                    # Mem0 v1.0+: Schlüssel ist "memory"
                    content = r.get("memory") or r.get("content", "")
                    score = float(r.get("score", 0))
                    if content:
                        all_results.append((score, scope, content))
            except Exception as e:
                logger.error(f"[{self.instance}] Memory-Suche in '{scope}' fehlgeschlagen: {e}")

        if not all_results:
            return ""

        # Sortiert nach Score (höchster zuerst), maximal 10 Treffer
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

        messages: Liste von {"role": "user"|"assistant", "content": "..."}
        scope: muss in write_scopes liegen
        Gibt True zurück wenn erfolgreich.
        """
        if scope not in VALID_SCOPES:
            logger.error(f"[{self.instance}] Ungültiger Scope: '{scope}'")
            return False

        if scope not in self.write_scopes:
            logger.error(
                f"[{self.instance}] Schreibzugriff auf '{scope}' verweigert "
                f"(write_scopes={sorted(self.write_scopes)})"
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
                metadata=metadata or {},
            )
            logger.info(
                f"[{self.instance}] Memory gespeichert | scope={scope} | "
                f"user_id={user_id} | result={result}"
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
        Speichert eine abgeschlossene Konversation in Memory.

        scope=None → automatisch den persönlichen Scope der Instanz wählen.
        ha-assist und ha-advanced schreiben nie (write_scopes leer).
        """
        if not self.write_scopes:
            return

        if scope is None:
            # Persönlichen Scope bevorzugen (nicht bnd_memory)
            personal = {s for s in self.write_scopes if s != "bnd_memory"}
            scope = next(iter(personal), next(iter(self.write_scopes)))

        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ]
        self.add(messages, scope)
