"""
Auth-Backend für HAANA Admin-Interface
Zwei Modi:
  - HA-Ingress:   SUPERVISOR_TOKEN Env-Var vorhanden → X-Ingress-Path Header reicht
  - Standalone:   Passwort-Hash aus /data/config/config.json (admin_password_hash),
                  Session-Token in Cookie/Bearer
"""

import json
import logging
import os
import secrets
from pathlib import Path

import bcrypt
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Konfiguration ─────────────────────────────────────────────────────────────

SUPERVISOR_TOKEN: str | None = os.environ.get("SUPERVISOR_TOKEN")
IS_INGRESS_MODE: bool = bool(SUPERVISOR_TOKEN)

CONF_FILE = Path(os.environ.get("HAANA_CONF_FILE", "/data/config/config.json"))

COOKIE_NAME = "haana_session"


# ── Passwort-Verwaltung ───────────────────────────────────────────────────────

def get_admin_password_hash() -> str:
    """
    Liest admin_password_hash aus config.json.
    Gibt "" zurück wenn nicht vorhanden (kein auto-generieren).
    """
    return _load_raw_config().get("admin_password_hash", "")


def verify_admin_password(password: str) -> bool:
    """
    Prüft Passwort gegen den gespeicherten bcrypt-Hash.
    Gibt False zurück wenn kein Hash gesetzt oder bei Fehler.
    """
    hash_val = get_admin_password_hash()
    if not hash_val:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_val.encode("utf-8"))
    except Exception:
        return False


def set_admin_password(password: str) -> None:
    """Setzt ein neues Admin-Passwort (bcrypt-Hash) und entfernt den alten Token-Key."""
    cfg = _load_raw_config()
    hash_val = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cfg["admin_password_hash"] = hash_val
    cfg.pop("admin_token", None)
    _save_raw_config(cfg)


# ── Session-Verwaltung ────────────────────────────────────────────────────────

def generate_session_token() -> str:
    """Erstellt einen neuen Session-Token, speichert ihn in config.json und gibt ihn zurück."""
    token = secrets.token_urlsafe(32)
    cfg = _load_raw_config()
    cfg["admin_session"] = token
    _save_raw_config(cfg)
    return token


def revoke_session() -> None:
    """Entfernt den Session-Token aus config.json."""
    cfg = _load_raw_config()
    cfg.pop("admin_session", None)
    _save_raw_config(cfg)


def _get_session_token() -> str:
    """Liest den aktuellen Session-Token aus config.json."""
    return _load_raw_config().get("admin_session", "")


# ── Token-Prüfung (Standalone) ────────────────────────────────────────────────

def _check_standalone_token(request: Request) -> bool:
    """Prüft Cookie oder Authorization-Header gegen den gespeicherten Session-Token."""
    expected = _get_session_token()
    if not expected:
        return False

    # 1. Cookie prüfen
    cookie_val = request.cookies.get(COOKIE_NAME, "")
    if cookie_val and secrets.compare_digest(cookie_val, expected):
        return True

    # 2. Authorization: Bearer <token> Header prüfen
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:]
        if bearer and secrets.compare_digest(bearer, expected):
            return True

    return False


# ── Auth-Check ────────────────────────────────────────────────────────────────

def is_authenticated(request: Request) -> bool:
    """
    Gibt True zurück wenn der Request authentifiziert ist.
    Im Ingress-Modus: X-Ingress-Path oder X-Supervisor-Token Header vorhanden.
    Im Standalone-Modus: Cookie haana_session oder Authorization: Bearer <token>.
    """
    if IS_INGRESS_MODE:
        supervisor_token_header = request.headers.get("X-Supervisor-Token")
        if supervisor_token_header:
            if SUPERVISOR_TOKEN and secrets.compare_digest(supervisor_token_header, SUPERVISOR_TOKEN):
                return True
            return False
        if request.headers.get("X-Ingress-Path"):
            return True
        return _check_standalone_token(request)
    else:
        return _check_standalone_token(request)


# ── FastAPI Dependency ────────────────────────────────────────────────────────

async def require_auth(request: Request):
    """
    FastAPI-Dependency: Wirft 401 wenn nicht authentifiziert.
    Wird nicht direkt verwendet (Middleware macht den Check),
    aber als Dependency für einzelne Endpoints verfügbar.
    """
    if not is_authenticated(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
        )


# ── Config-Hilfsfunktionen ────────────────────────────────────────────────────

def _load_raw_config() -> dict:
    """Lädt config.json ohne Migration-Logik."""
    if CONF_FILE.exists():
        try:
            return json.loads(CONF_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_raw_config(cfg: dict) -> None:
    """Speichert config.json (Minimal-Schreiber, um Circular-Import zu vermeiden)."""
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONF_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Startup-Log ───────────────────────────────────────────────────────────────

def log_startup_info() -> None:
    """Gibt beim Start Infos zum Auth-Modus aus."""
    if IS_INGRESS_MODE:
        logger.info("[Auth] Modus: HA-Ingress (SUPERVISOR_TOKEN vorhanden)")
    else:
        logger.info("[Auth] Modus: Standalone")
        hash_val = get_admin_password_hash()
        if not hash_val:
            logger.warning("[Auth] Kein Admin-Passwort gesetzt — Setup erforderlich")
