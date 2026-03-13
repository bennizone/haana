"""
HAANA Common Types — Gemeinsame Datentypen für Channels und Skills.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigField:
    """Beschreibt ein einzelnes Konfigurationsfeld für die Admin-UI."""
    key: str
    label: str
    label_de: str
    field_type: str  # "text" | "password" | "select" | "toggle" | "number"
    required: bool = False
    default: Any = None
    hint: str = ""
    hint_de: str = ""
    options: list = field(default_factory=list)
    secret: bool = False
