"""
HAANA WhatsApp Mode-Router

Verwaltet den Admin-Modus pro Telefonnummer:
- /admin → Admin-Modus aktivieren (nur für user.role == "admin")
- /user, /exit → User-Modus zurück
- 30 Min Inaktivität → Auto-Rückschaltung
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ADMIN_TIMEOUT = 1800  # 30 Minuten

_mode: dict[str, str] = {}            # phone → "user" | "admin"
_last_activity: dict[str, float] = {} # phone → timestamp


def _set_mode(phone: str, mode: str) -> None:
    _mode[phone] = mode
    _last_activity[phone] = time.time()
    logger.info(f"[wa-router] {phone} → mode={mode}")


def update_activity(phone: str) -> None:
    """Aktualisiert den Aktivitäts-Timestamp für eine Telefonnummer."""
    _last_activity[phone] = time.time()


def get_mode(phone: str) -> str:
    """Gibt den aktuellen Modus zurück. Prüft Auto-Timeout."""
    if _mode.get(phone) == "admin":
        elapsed = time.time() - _last_activity.get(phone, 0)
        if elapsed > _ADMIN_TIMEOUT:
            _set_mode(phone, "user")
            logger.info(f"[wa-router] {phone} Auto-Timeout nach {elapsed:.0f}s")
            return "admin-timeout"  # Signalisiert dass Timeout gerade eingetreten ist
    return _mode.get(phone, "user")


def handle_slash_command(phone: str, text: str, users: list) -> tuple[bool, Optional[str]]:
    """
    Verarbeitet Slash-Befehle.
    Returns: (handled: bool, response: Optional[str])
    - handled=True → Befehl erkannt, response an WA senden
    - handled=False → kein Slash-Befehl, normal weiterrouten
    """
    cmd = text.strip().lower()

    if cmd == "/admin":
        user = next((u for u in users if
                     _normalize_phone(u.get("whatsapp_phone", "")) == _normalize_phone(phone)), None)
        if not user or user.get("role") != "admin":
            return True, "Nicht berechtigt."
        _set_mode(phone, "admin")
        return True, "Admin-Modus aktiv. /user zum Beenden."

    if cmd in ("/user", "/exit"):
        _set_mode(phone, "user")
        return True, "User-Modus aktiv."

    return False, None


def resolve_instance(phone: str, users: list) -> Optional[str]:
    """Gibt die Ziel-Instanz für eine Telefonnummer zurück."""
    user = _find_user(phone, users)
    if not user:
        return None
    if _mode.get(phone) == "admin":
        return "haana-admin"
    return user["id"]


def build_message(phone: str, text: str, users: list) -> str:
    """Fügt ggf. [Name]: Prefix ein wenn im Admin-Modus."""
    if _mode.get(phone) == "admin":
        user = _find_user(phone, users)
        name = user["display_name"] if user else phone
        return f"[{name}]: {text}"
    return text


def _find_user(phone: str, users: list) -> Optional[dict]:
    norm = _normalize_phone(phone)
    for u in users:
        if _normalize_phone(u.get("whatsapp_phone", "")) == norm:
            return u
    return None


def _normalize_phone(phone: str) -> str:
    """Normalisiert eine Telefonnummer für Vergleiche."""
    if not phone:
        return ""
    # JID-Suffix entfernen
    phone = phone.split("@")[0]
    return phone.strip()
