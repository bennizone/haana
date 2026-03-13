"""
HAANA Kalender Skill — CalDAV-Integration (Stub).

Status: Stub. Tool-Definitionen sind vorhanden, aber die eigentliche
CalDAV-Logik (Termine lesen/erstellen/löschen) ist noch nicht implementiert.

Voraussetzung für produktiven Einsatz: caldav Python-Bibliothek,
Implementierung der drei Tool-Handler-Funktionen.
"""

from __future__ import annotations
from common.types import ConfigField
from skills.base import BaseSkill


class KalenderSkill(BaseSkill):
    """CalDAV-Kalender-Integration für HAANA-Agenten.

    Gibt Agenten Zugriff auf Kalendereinträge via CalDAV.
    Jeder User kann seinen eigenen CalDAV-Server konfigurieren.
    """

    skill_id = "kalender"
    display_name = "Kalender (CalDAV)"

    def get_tools(self) -> list[dict]:
        """Drei Tool-Definitionen im Anthropic tool_use Schema."""
        return [
            {
                "name": "get_calendar_events",
                "description": "Liest Kalendereinträge für einen Zeitraum. Gibt Titel, Datum, Uhrzeit und Ort zurück.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Startdatum im Format YYYY-MM-DD",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Enddatum im Format YYYY-MM-DD",
                        },
                        "calendar_name": {
                            "type": "string",
                            "description": "Optionaler Kalenderfilter. Leer = alle Kalender.",
                        },
                    },
                    "required": ["start_date", "end_date"],
                },
            },
            {
                "name": "create_event",
                "description": "Erstellt einen neuen Kalendereintrag.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Titel des Termins",
                        },
                        "start_datetime": {
                            "type": "string",
                            "description": "Startzeit im Format YYYY-MM-DDTHH:MM:SS",
                        },
                        "end_datetime": {
                            "type": "string",
                            "description": "Endzeit im Format YYYY-MM-DDTHH:MM:SS",
                        },
                        "location": {
                            "type": "string",
                            "description": "Optionaler Ort",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optionale Beschreibung / Notizen",
                        },
                        "calendar_name": {
                            "type": "string",
                            "description": "Zielkalender. Leer = Standardkalender.",
                        },
                    },
                    "required": ["title", "start_datetime", "end_datetime"],
                },
            },
            {
                "name": "delete_event",
                "description": "Löscht einen Kalendereintrag anhand seiner ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "ID des zu löschenden Termins (aus get_calendar_events)",
                        },
                    },
                    "required": ["event_id"],
                },
            },
        ]

    def get_config_schema(self) -> list[ConfigField]:
        """Keine globalen Felder — CalDAV wird pro User konfiguriert."""
        return []

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User CalDAV-Zugangsdaten."""
        return [
            ConfigField(
                key="caldav_url",
                label="CalDAV URL",
                label_de="CalDAV-URL",
                field_type="text",
                required=True,
                hint="e.g. https://caldav.example.com/calendars/user/",
                hint_de="z.B. https://caldav.example.com/calendars/user/",
            ),
            ConfigField(
                key="caldav_user",
                label="CalDAV Username",
                label_de="CalDAV-Benutzername",
                field_type="text",
                required=True,
            ),
            ConfigField(
                key="caldav_password",
                label="CalDAV Password",
                label_de="CalDAV-Passwort",
                field_type="password",
                required=True,
                secret=True,
            ),
            ConfigField(
                key="caldav_calendar_name",
                label="Calendar Name (optional)",
                label_de="Kalenderbezeichnung (optional)",
                field_type="text",
                required=False,
                hint="Leave empty to use all calendars.",
                hint_de="Leer lassen um alle Kalender zu nutzen.",
            ),
        ]

    def get_claude_md_snippet(self) -> str:
        """System-Prompt-Ergänzung wenn dieser Skill aktiv ist."""
        return (
            "Du hast Zugriff auf den Kalender des Users via CalDAV. "
            "Nutze get_calendar_events um Termine abzufragen, "
            "create_event um neue Termine anzulegen, "
            "und delete_event um Termine zu löschen. "
            "Frage bei unklaren Zeitangaben immer nach bevor du Termine erstellst."
        )

    def is_enabled(self, config: dict) -> bool:
        """Kalender-Skill ist aktiv wenn mindestens ein User eine caldav_url hat."""
        users = config.get("users", [])
        return any(
            u.get("caldav_url", "").strip()
            for u in users
            if not u.get("system")
        )
