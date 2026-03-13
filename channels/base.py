"""
HAANA Channel Base — Abstrakte Basisklasse für alle Eingangskanäle.

Ein Channel definiert wie Nachrichten in HAANA reinkommen (WhatsApp, Telegram,
HA Voice, Web-Chat) und welche Konfiguration er global und pro User braucht.
"""

from __future__ import annotations
from common.types import ConfigField  # noqa: F401 — re-export für Rückwärtskompatibilität


class BaseChannel:
    """Abstrakte Basisklasse für alle HAANA-Eingangskanäle.

    Jeder Channel implementiert diese Klasse und macht sich damit
    für die ModuleRegistry und das Admin-Interface selbstbeschreibend.
    """

    channel_id: str = ""        # Eindeutige ID, z.B. "whatsapp"
    display_name: str = ""      # Anzeigename in der UI

    def get_config_schema(self) -> list[ConfigField]:
        """Globale Konfigurationsfelder für diesen Channel.
        Erscheinen als eigener Sub-Tab in Config → Channels."""
        raise NotImplementedError(f"{self.__class__.__name__} muss get_config_schema() implementieren")

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User-Felder.
        Erscheinen automatisch in jeder User-Karte im Users-Tab."""
        raise NotImplementedError(f"{self.__class__.__name__} muss get_user_config_schema() implementieren")

    def get_docker_service(self) -> dict | None:
        """Optional: eigener Docker-Service für diesen Channel.
        Gibt docker-compose Service-Definition zurück, oder None."""
        return None

    def is_enabled(self, config: dict) -> bool:
        """Ist dieser Channel in der aktuellen Config aktiv?"""
        raise NotImplementedError(f"{self.__class__.__name__} muss is_enabled() implementieren")
