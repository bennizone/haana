"""Auth-Endpoints: Login, Logout, SSO, Status, Passwort-Ändern."""

import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import auth as _auth
from .deps import load_config, SSO_TOKENS, SSO_LOCK

router = APIRouter(tags=["auth"])


@router.get("/api/auth/status")
async def auth_status(request: Request):
    """Gibt Auth-Status und Modus zurück. Immer erreichbar (kein Auth-Guard)."""
    mode = "ingress" if _auth.IS_INGRESS_MODE else "standalone"
    authenticated = _auth.is_authenticated(request)
    if not authenticated:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            bearer = auth_header[7:].strip()
            cfg = load_config()
            companion_token = cfg.get("companion_token", "")
            if companion_token and bearer and secrets.compare_digest(bearer, companion_token):
                authenticated = True
    return {"authenticated": authenticated, "mode": mode}


@router.post("/api/auth/login")
async def auth_login(request: Request):
    """Standalone-Login mit Passwort."""
    if _auth.IS_INGRESS_MODE:
        return {"ok": True, "mode": "ingress"}

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiger JSON-Body")

    password = body.get("password", "")
    if not password or not _auth.verify_admin_password(password):
        raise HTTPException(401, "Ungültiges Passwort")

    session_token = _auth.generate_session_token()
    response = JSONResponse({"ok": True, "mode": "standalone"})
    response.set_cookie(
        key=_auth.COOKIE_NAME,
        value=session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.get("/api/auth/sso")
async def auth_sso(token: str):
    """Validiert Companion-SSO-Token, erstellt Session, redirect zur UI."""
    now = time.time()
    with SSO_LOCK:
        expiry = SSO_TOKENS.get(token)
        if not expiry or expiry < now:
            raise HTTPException(status_code=401, detail="Ungültiger oder abgelaufener SSO-Token")
        del SSO_TOKENS[token]
    from starlette.responses import RedirectResponse
    session_token = _auth.generate_session_token()
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=_auth.COOKIE_NAME,
        value=session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.post("/api/auth/logout")
async def auth_logout():
    """Löscht den Session-Cookie und widerruft die Server-Session."""
    _auth.revoke_session()
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=_auth.COOKIE_NAME, samesite="lax")
    return response


@router.post("/api/auth/change-password")
async def auth_change_password(request: Request):
    """Ändert das Admin-Passwort. Requires auth (Middleware)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiger JSON-Body")

    current = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    if not current or not new_pw:
        raise HTTPException(400, "current_password und new_password erforderlich")

    if not _auth.verify_admin_password(current):
        raise HTTPException(401, "Aktuelles Passwort falsch")

    if len(new_pw) < 8:
        raise HTTPException(400, "Neues Passwort muss mindestens 8 Zeichen haben")

    _auth.set_admin_password(new_pw)
    _auth.revoke_session()
    new_token = _auth.generate_session_token()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key=_auth.COOKIE_NAME,
        value=new_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response
