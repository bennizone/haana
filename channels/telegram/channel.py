"""
HAANA Telegram Channel — Stub-Implementierung.

Status: Stub. Noch nicht produktiv nutzbar.
Fehlende Komponente: telegram-bridge Service (python-telegram-bot oder aiogram).

Dieser Channel definiert bereits alle Konfigurationsfelder
und ist in der ModuleRegistry registrierbar.
"""

from __future__ import annotations
from common.types import ConfigField
from channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """Telegram als Eingangskanal für HAANA-Agenten.

    Ermöglicht es Usern über Telegram-Bots mit ihren Agenten zu kommunizieren.
    Jeder User kann eine eigene Telegram Chat-ID konfigurieren.
    """

    channel_id = "telegram"
    display_name = "Telegram"

    def get_config_schema(self) -> list[ConfigField]:
        """Globale Telegram-Konfiguration: Bot-Token und Zugangsbeschränkung."""
        return [
            ConfigField(
                key="telegram_bot_token",
                label="Bot Token",
                label_de="Bot-Token",
                field_type="password",
                required=True,
                secret=True,
                hint="From @BotFather: /newbot",
                hint_de="Von @BotFather: /newbot → Token kopieren",
            ),
            ConfigField(
                key="telegram_allowed_chat_ids",
                label="Allowed Chat IDs",
                label_de="Erlaubte Chat-IDs",
                field_type="text",
                required=False,
                hint="Comma-separated list of allowed chat IDs. Empty = all users with configured ID.",
                hint_de="Kommagetrennte Chat-IDs. Leer = alle User mit konfigurierter ID erlaubt.",
            ),
        ]

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User: Telegram Chat-ID für diesen User."""
        return [
            ConfigField(
                key="telegram_chat_id",
                label="Telegram Chat ID",
                label_de="Telegram Chat-ID",
                field_type="text",
                required=False,
                hint="Get from @userinfobot — send any message to get your ID.",
                hint_de="Von @userinfobot: Nachricht schicken → ID wird angezeigt.",
            ),
        ]

    def get_docker_service(self) -> dict | None:
        """Noch kein eigener Docker-Service — Bridge noch nicht implementiert."""
        return None

    def is_enabled(self, config: dict) -> bool:
        """Telegram ist aktiv wenn ein Bot-Token in services.telegram konfiguriert ist."""
        token = config.get("services", {}).get("telegram", {}).get("telegram_bot_token", "").strip()
        return bool(token)
