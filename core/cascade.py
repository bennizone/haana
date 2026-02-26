"""
HAANA LLM-Kaskade – Stub

Der Agent selbst läuft über claude_agent_sdk (Claude Code CLI).
Diese Datei ist für Komponenten vorgesehen, die direkt eine LLM-API
brauchen (z.B. zukünftige Fallback-Logik, Anonymisierer-Integration).

Phase 1: nur Logging-Stub, noch nicht in Verwendung.

Erweiterung in späteren Phasen:
  - Fallback auf MiniMax oder Custom Provider (OpenAI-kompatibel)
  - Anonymisierer vor Cloud-Calls einhängen
  - Tracking von Provider-Fehlern
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_ollama_base_url() -> str | None:
    """Gibt die Ollama-URL zurück wenn konfiguriert, sonst None."""
    url = os.environ.get("OLLAMA_URL", "").strip()
    return url or None


class LLMCascade:
    """
    Phase 2+: Failover zwischen mehreren LLM-Providern.

    Für Komponenten die kein Claude Code SDK nutzen können
    (z.B. Memory-Extraktion, Embedding, Anonymisierer).

    Reihenfolge:
      1. Lokales Ollama (wenn OLLAMA_URL gesetzt)
      2. Fallback-LLM (wenn FALLBACK_LLM_* gesetzt, OpenAI-kompatibel)

    Aktuell: Stub, noch nicht verwendet.
    """

    def __init__(self):
        self.ollama_url = get_ollama_base_url()
        fallback_url = os.environ.get("FALLBACK_LLM_BASE_URL", "").strip()

        if self.ollama_url:
            logger.info(f"LLMCascade: Ollama @ {self.ollama_url}")
        if fallback_url:
            logger.info(f"LLMCascade: Fallback-LLM @ {fallback_url} (noch nicht aktiv)")
        if not self.ollama_url and not fallback_url:
            logger.warning(
                "LLMCascade: Weder OLLAMA_URL noch FALLBACK_LLM_BASE_URL gesetzt. "
                "Memory-Features benötigen einen lokalen LLM-Provider."
            )
