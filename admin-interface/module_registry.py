"""
HAANA Module Registry — Herzstück der Modularität.

Lädt und verwaltet alle verfügbaren Channels und Skills.
Stellt dem Admin-Interface alle Konfigurationsfelder bereit.

Wird beim Start des Admin-Interface einmalig initialisiert.
Module registrieren sich selbst via registry.register_channel()
oder registry.register_skill().
"""

from __future__ import annotations
import logging
import sys
import os

# channels/ und skills/ liegen im Projekt-Root, nicht im admin-interface/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from channels.base import BaseChannel, ConfigField
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Verwaltet alle registrierten Channels und Skills."""

    def __init__(self):
        self._channels: dict[str, BaseChannel] = {}
        self._skills: dict[str, BaseSkill] = {}

    def register_channel(self, channel: BaseChannel) -> None:
        """Registriert einen Channel. Überschreibt bei gleichem channel_id."""
        if not channel.channel_id:
            raise ValueError(f"Channel {channel.__class__.__name__} hat keine channel_id")
        self._channels[channel.channel_id] = channel
        logger.debug("Channel registriert: %s (%s)", channel.channel_id, channel.display_name)

    def register_skill(self, skill: BaseSkill) -> None:
        """Registriert einen Skill. Überschreibt bei gleichem skill_id."""
        if not skill.skill_id:
            raise ValueError(f"Skill {skill.__class__.__name__} hat keine skill_id")
        self._skills[skill.skill_id] = skill
        logger.debug("Skill registriert: %s (%s)", skill.skill_id, skill.display_name)

    def get_active_channels(self, config: dict) -> list[BaseChannel]:
        """Alle Channels die laut config aktiv sind."""
        result = []
        for channel in self._channels.values():
            try:
                if channel.is_enabled(config):
                    result.append(channel)
            except Exception as e:
                logger.warning("Channel %s: is_enabled() fehlgeschlagen: %s", channel.channel_id, e)
        return result

    def get_active_skills(self, config: dict) -> list[BaseSkill]:
        """Alle Skills die laut config aktiv sind."""
        result = []
        for skill in self._skills.values():
            try:
                if skill.is_enabled(config):
                    result.append(skill)
            except Exception as e:
                logger.warning("Skill %s: is_enabled() fehlgeschlagen: %s", skill.skill_id, e)
        return result

    def get_all_config_schemas(self, config: dict) -> dict:
        """Für die Config-UI: alle Felder aller aktiven Module.

        Rückgabe: {
            "channels": {"whatsapp": [ConfigField, ...], ...},
            "skills": {"kalender": [ConfigField, ...], ...}
        }
        """
        result: dict = {"channels": {}, "skills": {}}
        for channel in self.get_active_channels(config):
            try:
                result["channels"][channel.channel_id] = channel.get_config_schema()
            except Exception as e:
                logger.warning("Channel %s: get_config_schema() fehlgeschlagen: %s", channel.channel_id, e)
        for skill in self.get_active_skills(config):
            try:
                result["skills"][skill.skill_id] = skill.get_config_schema()
            except Exception as e:
                logger.warning("Skill %s: get_config_schema() fehlgeschlagen: %s", skill.skill_id, e)
        return result

    def get_user_config_schema(self, config: dict) -> list[ConfigField]:
        """Alle pro-User-Felder aller aktiven Module zusammengeführt.
        Wird in der User-Karte im Admin-Interface angezeigt."""
        fields: list[ConfigField] = []
        for channel in self.get_active_channels(config):
            try:
                fields.extend(channel.get_user_config_schema())
            except Exception as e:
                logger.warning("Channel %s: get_user_config_schema() fehlgeschlagen: %s", channel.channel_id, e)
        for skill in self.get_active_skills(config):
            try:
                fields.extend(skill.get_user_config_schema())
            except Exception as e:
                logger.warning("Skill %s: get_user_config_schema() fehlgeschlagen: %s", skill.skill_id, e)
        return fields

    def get_all_channels(self) -> list[BaseChannel]:
        """Alle registrierten Channels (unabhängig von Config)."""
        return list(self._channels.values())

    def get_all_skills(self) -> list[BaseSkill]:
        """Alle registrierten Skills (unabhängig von Config)."""
        return list(self._skills.values())


# Globale Instanz — wird beim Import initialisiert
registry = ModuleRegistry()
