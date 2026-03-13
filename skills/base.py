"""
HAANA Skill Base — Abstrakte Basisklasse für alle Agent-Skills.

Ein Skill definiert was ein Agent tun kann: Tools (Kalender, Einkaufsliste,
HA-Steuerung, ...) plus den zugehörigen System-Prompt-Kontext.
"""

from __future__ import annotations
from common.types import ConfigField


class BaseSkill:
    """Abstrakte Basisklasse für alle HAANA-Skills.

    Jeder Skill implementiert diese Klasse und macht sich damit
    für die ModuleRegistry und das Admin-Interface selbstbeschreibend.
    """

    skill_id: str = ""          # Eindeutige ID, z.B. "kalender"
    display_name: str = ""      # Anzeigename in der UI

    def get_tools(self) -> list[dict]:
        """Tool-Definitionen für den Claude Agent.
        Format: Anthropic tool_use Schema (name, description, input_schema)."""
        raise NotImplementedError(f"{self.__class__.__name__} muss get_tools() implementieren")

    def get_config_schema(self) -> list[ConfigField]:
        """Globale Konfigurationsfelder für diesen Skill."""
        raise NotImplementedError(f"{self.__class__.__name__} muss get_config_schema() implementieren")

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User-Felder (z.B. CalDAV-URL pro User).
        Erscheinen automatisch in jeder User-Karte im Users-Tab."""
        raise NotImplementedError(f"{self.__class__.__name__} muss get_user_config_schema() implementieren")

    def get_claude_md_snippet(self) -> str:
        """Text-Snippet das automatisch in den Agent-System-Prompt
        eingefügt wird wenn dieser Skill aktiv ist."""
        return ""

    def is_enabled(self, config: dict) -> bool:
        """Ist dieser Skill in der aktuellen Config aktiv?"""
        raise NotImplementedError(f"{self.__class__.__name__} muss is_enabled() implementieren")
