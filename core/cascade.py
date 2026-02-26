"""
HAANA LLM-Kaskade – Phase 1 Stub

Verwaltet LLM-Provider und Failover-Logik.
Phase 1: nur Anthropic als Primary. Fallback-Logik ist vorbereitet aber inaktiv.

Erweiterung in späteren Phasen:
  - Fallback auf MiniMax oder Custom Provider
  - Anonymisierer vor Cloud-Calls
  - Tracking von Provider-Fehlern
"""

import os
import logging

from anthropic import Anthropic

logger = logging.getLogger(__name__)


def get_anthropic_client() -> Anthropic:
    """
    Gibt einen konfigurierten Anthropic-Client zurück.
    Phase 1: direkt, kein Failover.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. "
            "Bitte .env befüllen oder Umgebungsvariable setzen."
        )

    # Fallback-Provider geloggt wenn konfiguriert (aber noch nicht aktiv)
    fallback_url = os.environ.get("FALLBACK_LLM_BASE_URL", "").strip()
    if fallback_url:
        logger.info(
            f"Fallback-LLM konfiguriert: {fallback_url} "
            "(Phase 1: noch nicht aktiv)"
        )

    return Anthropic(api_key=api_key)


# ── Für spätere Phasen vorbereitet ───────────────────────────────────────────

class LLMCascade:
    """
    Phase 2+: Failover zwischen mehreren Providern.

    Reihenfolge:
      1. Lokales Ollama (wenn OLLAMA_URL gesetzt)
      2. Anthropic API (Primary)
      3. Fallback-LLM (wenn FALLBACK_LLM_* gesetzt)

    Aktuell: Stub, noch nicht verwendet.
    """

    def __init__(self):
        self.primary = get_anthropic_client()
        logger.debug("LLMCascade initialisiert (Phase 1: nur Primary aktiv)")

    def create_message(self, **kwargs):
        """Wrapper um client.messages.create() mit Failover-Hook."""
        return self.primary.messages.create(**kwargs)
