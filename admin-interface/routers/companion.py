"""Companion API endpoints: ping, SSO, register, refresh-persons, token, ha-mcp-status."""

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
    return {"status": "ok", "version": "1.0.0"}


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


@router.post("/api/companion/register")
async def companion_register(request: Request):
    """Registriert den Companion."""
    cfg = load_config()
    if not verify_companion_token(request, cfg):
        raise HTTPException(status_code=401, detail="Invalid companion token")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungueltiges JSON")
    ha_url = (body.get("ha_url") or "").strip().rstrip("/")
    services = cfg.setdefault("services", {})
    if ha_url:
        services["ha_url"] = ha_url
    ha_persons = body.get("ha_persons", [])
    if ha_persons:
        cfg["services"]["ha_persons"] = ha_persons
        logger.info(f"[companion] ha_persons gespeichert: {len(ha_persons)}")
    ha_mcp = body.get("ha_mcp")
    if ha_mcp is not None:
        cfg["services"]["ha_mcp"] = ha_mcp
        logger.info(f"[companion] ha_mcp gespeichert: {ha_mcp}")
    save_config(cfg)
    logger.info(f"[companion] Registered: ha_url={ha_url}")
    return {"status": "registered"}


@router.post("/api/companion/refresh-persons")
async def companion_refresh_persons(request: Request):
    """Companion kann HA-Personenliste aktualisieren."""
    cfg = load_config()
    if not verify_companion_token(request, cfg):
        raise HTTPException(status_code=401, detail="Invalid companion token")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungueltiges JSON")
    persons = body.get("ha_persons", [])
    cfg.setdefault("services", {})["ha_persons"] = persons
    save_config(cfg)
    logger.info(f"[companion] ha_persons aktualisiert: {len(persons)}")
    return {"ok": True, "count": len(persons)}


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


@router.post("/api/companion/ha-mcp-status")
async def companion_ha_mcp_status(request: Request):
    """Companion meldet ha-mcp Addon Status."""
    cfg = load_config()
    if not verify_companion_token(request, cfg):
        raise HTTPException(status_code=401, detail="Invalid companion token")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungueltiges JSON")
    ha_mcp = body.get("ha_mcp", {})
    cfg.setdefault("services", {})["ha_mcp"] = ha_mcp
    save_config(cfg)
    logger.info(f"[companion] ha-mcp Status aktualisiert: {ha_mcp}")
    return {"ok": True}


@router.get("/api/ha-mcp-status")
async def ha_mcp_status():
    """Gibt den bekannten ha-mcp Status zurueck."""
    cfg = load_config()
    return cfg.get("services", {}).get("ha_mcp", {"installed": False})
