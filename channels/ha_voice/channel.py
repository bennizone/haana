"""
HAANA HA Voice Channel — Home Assistant Sprachintegration.

Exponiert HAANA als Ollama-kompatibler Server, damit HA die eingebaute
Ollama-Integration direkt nutzen kann. Kein HACS-Addon nötig.

Der eigentliche Fake-Ollama-Proxy läuft in core/ollama_compat.py
und wird vom Admin-Interface beim Start eingebunden.
Diese Klasse beschreibt das Konfigurationsschema für die ModuleRegistry.
"""

from __future__ import annotations
from common.types import ConfigField
from channels.base import BaseChannel


class HAVoiceChannel(BaseChannel):
    """Home Assistant Sprach-Integration via Fake-Ollama-API.

    HAANA täuscht einen Ollama-Server vor: HA verbindet sich über
    die eingebaute Ollama-Integration, HAANA routet die Anfragen
    intern an seine LLM-Provider und gibt die Antwort im Ollama-Format zurück.

    3-Tier-Architektur:
      ha-assist (schnell, lokal) → optional: Delegation an ha-advanced (Claude)
      Reguläre User-Agenten können ebenfalls als Ollama-Modelle exponiert werden.
    """

    channel_id = "ha-voice"  # Bindestrich: externe ID-Konvention; Package-Name nutzt Unterstrich (Python)
    display_name = "HA Voice"

    def get_config_schema(self) -> list[ConfigField]:
        """Globale HA Voice / Fake-Ollama Konfiguration."""
        return [
            ConfigField(
                key="ollama_compat_enabled",
                label="Enable HA Voice (Fake-Ollama)",
                label_de="HA Voice aktivieren (Fake-Ollama)",
                field_type="toggle",
                required=False,
                default=False,
                hint="Exposes HAANA as an Ollama server for Home Assistant voice integration.",
                hint_de="Exponiert HAANA als Ollama-Server für die HA-Sprachintegration.",
            ),
            ConfigField(
                key="ha_url",
                label="Home Assistant URL",
                label_de="Home Assistant URL",
                field_type="text",
                required=False,
                hint="e.g. http://homeassistant.local:8123",
                hint_de="z.B. http://homeassistant.local:8123",
            ),
            ConfigField(
                key="ha_token",
                label="HA Long-Lived Access Token",
                label_de="HA Langzeit-Zugriffstoken",
                field_type="password",
                required=False,
                secret=True,
                hint="Create in HA: Profile -> Security -> Long-Lived Access Tokens",
                hint_de="Erstellen in HA: Profil -> Sicherheit -> Langzeit-Zugriffstoken",
            ),
            ConfigField(
                key="stt_entity",
                label="STT Entity (Speech-to-Text)",
                label_de="STT-Entität (Sprache->Text)",
                field_type="text",
                required=False,
                hint="e.g. stt.faster_whisper",
                hint_de="z.B. stt.faster_whisper",
            ),
            ConfigField(
                key="tts_entity",
                label="TTS Entity (Text-to-Speech)",
                label_de="TTS-Entität (Text->Sprache)",
                field_type="text",
                required=False,
                hint="e.g. tts.piper",
                hint_de="z.B. tts.piper",
            ),
        ]

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User HA Voice Konfiguration."""
        return [
            ConfigField(
                key="ha_person_entity",
                label="HA Person Entity",
                label_de="HA Personen-Entität",
                field_type="text",
                required=False,
                hint="e.g. person.firstname -- links this user to an HA person.",
                hint_de="z.B. person.vorname -- verknüpft diesen User mit einer HA-Person.",
            ),
        ]

    def get_docker_service(self) -> None:
        """Kein eigener Docker-Service — HA Voice läuft im admin-interface Container."""
        return None

    def is_enabled(self, config: dict) -> bool:
        """HA Voice ist aktiv wenn ollama_compat aktiviert ist."""
        return bool(config.get("ollama_compat", {}).get("enabled", False))
