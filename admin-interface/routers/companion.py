"""Companion API endpoints: ping, SSO, token."""

import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Request

import auth as _auth
from .deps import (
    load_config, save_config,
    verify_companion_token, SSO_TOKENS, SSO_LOCK,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["companion"])


@router.get("/api/companion/ping")
async def companion_ping(request: Request):
    """Token-Validierung fuer den Companion-Addon."""
    cfg = load_config()
    if not verify_companion_token(request, cfg):
        raise HTTPException(status_code=401, detail="Invalid companion token")
    return {"status": "ok", "version": "2.0.0"}


@router.post("/api/companion/sso")
async def companion_sso(request: Request):
    """Einmal-SSO-Token fuer Companion Browser-Redirect (60s TTL)."""
    cfg = load_config()
    if not verify_companion_token(request, cfg):
        raise HTTPException(status_code=401, detail="Invalid companion token")
    now = time.time()
    with SSO_LOCK:
        expired = [t for t, exp in SSO_TOKENS.items() if exp < now]
        for t in expired:
            del SSO_TOKENS[t]
        sso_token = secrets.token_urlsafe(32)
        SSO_TOKENS[sso_token] = now + 60
    return {"sso_token": sso_token}


@router.get("/api/companion/token")
async def companion_token_get(request: Request):
    """Gibt den aktuellen Companion-Token zurueck."""
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin-Authentifizierung erforderlich")
    cfg = load_config()
    token = cfg.get("companion_token", "")
    if not token:
        token = secrets.token_hex(32)
        cfg["companion_token"] = token
        save_config(cfg)
        logger.info("[companion] Companion-Token erstmalig generiert")
    return {"companion_token": token}


@router.post("/api/companion/token/regenerate")
async def companion_token_regenerate(request: Request):
    """Generiert einen neuen Companion-Token."""
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin-Authentifizierung erforderlich")
    cfg = load_config()
    new_token = secrets.token_hex(32)
    cfg["companion_token"] = new_token
    save_config(cfg)
    logger.info("[companion] Companion-Token neu generiert")
    return {"companion_token": new_token}
