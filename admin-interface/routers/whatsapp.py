"""WhatsApp endpoints: status, QR, logout, bridge start/stop, wa-proxy, config, LID."""

import secrets

from fastapi import APIRouter, HTTPException, Request

import auth as _auth
from .deps import (
    load_config, save_config, get_agent_url,
    WA_BRIDGE_URL, BRIDGE_SECRET, ADMIN_SELF_URL, HAANA_MODE, logger,
)

router = APIRouter(tags=["whatsapp"])


@router.get("/api/whatsapp-status")
async def whatsapp_status():
    """Proxy: Bridge-Verbindungsstatus abfragen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{WA_BRIDGE_URL}/status")
            return r.json()
    except httpx.ConnectError:
        return {"status": "offline", "error": "Bridge nicht erreichbar"}
    except Exception as e:
        return {"status": "offline", "error": str(e)[:200]}


@router.get("/api/whatsapp-qr")
async def whatsapp_qr():
    """Proxy: aktuellen QR-Code als Base64 Data-URL abrufen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{WA_BRIDGE_URL}/qr")
            return r.json()
    except httpx.ConnectError:
        return {"error": "Bridge nicht erreichbar", "status": "offline"}
    except Exception as e:
        return {"error": str(e)[:200], "status": "offline"}


@router.post("/api/whatsapp-logout")
async def whatsapp_logout():
    """Proxy: WhatsApp-Session trennen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{WA_BRIDGE_URL}/logout")
            return r.json()
    except httpx.ConnectError:
        return {"ok": False, "error": "Bridge nicht erreichbar"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/api/users/whatsapp-lid")
async def set_user_whatsapp_lid(request: Request):
    """Auto-LID-Learning: Bridge speichert aufgeloeste LID fuer einen User."""
    cfg = load_config()
    bridge_secret = BRIDGE_SECRET
    token = request.headers.get("X-Bridge-Token", "")
    if not (
        (bridge_secret and secrets.compare_digest(token, bridge_secret))
        or _auth.is_authenticated(request)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    phone = body.get("phone", "").strip()
    lid = body.get("lid", "").strip()
    if not phone or not lid:
        raise HTTPException(status_code=400, detail="phone and lid required")

    users = cfg.get("users", [])
    for user in users:
        if user.get("whatsapp_phone", "").strip() == phone:
            if user.get("whatsapp_lid") == lid:
                return {"ok": True, "updated": False}
            user["whatsapp_lid"] = lid
            save_config(cfg)
            logger.info("whatsapp_lid automatisch gesetzt: user=%s lid=%s", user["id"], lid)
            return {"ok": True, "updated": True, "user_id": user["id"]}

    return {"ok": False, "detail": "No user with this phone number found"}


@router.post("/api/whatsapp/start")
async def whatsapp_start(request: Request):
    """WhatsApp-Bridge Container starten."""
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "compose", "--profile", "agents", "up", "-d", "whatsapp-bridge"],
            cwd="/opt/haana",
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or "Failed to start bridge")
        return {"ok": True}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout starting bridge")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="docker not found")


@router.post("/api/whatsapp/stop")
async def whatsapp_stop(request: Request):
    """WhatsApp-Bridge Container stoppen."""
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "compose", "--profile", "agents", "stop", "whatsapp-bridge"],
            cwd="/opt/haana",
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or "Failed to stop bridge")
        return {"ok": True}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout stopping bridge")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="docker not found")


@router.get("/api/whatsapp-config")
async def whatsapp_config_endpoint(request: Request):
    """Liefert WhatsApp-Routing-Konfiguration für die Bridge."""
    cfg = load_config()
    if BRIDGE_SECRET:
        incoming = request.headers.get("X-Bridge-Token", "")
        if not incoming or not secrets.compare_digest(incoming, BRIDGE_SECRET):
            raise HTTPException(403, "Bridge-Token ungültig")
    wa = cfg.get("whatsapp", {"mode": "separate", "self_prefix": "!h "})
    routes = []
    for user in cfg.get("users", []):
        phone = user.get("whatsapp_phone", "").strip()
        if not phone or user.get("system"):
            continue
        jid = phone if "@" in phone else f"{phone}@s.whatsapp.net"
        uid = user["id"]
        if HAANA_MODE == "addon":
            agent_url = f"http://localhost:8080/api/wa-proxy/{uid}"
        else:
            agent_url = f"{ADMIN_SELF_URL}/api/wa-proxy/{uid}"
        target = {"agent_url": agent_url, "user_id": uid}
        routes.append({"jid": jid, **target})
        lid = user.get("whatsapp_lid", "").strip()
        if lid:
            lid_jid = lid if "@" in lid else f"{lid}@lid"
            routes.append({"jid": lid_jid, **target})

    services = cfg.get("services", {})
    stt = None
    tts = None
    ha_url = services.get("ha_url", "").strip()
    ha_token = services.get("ha_token", "").strip()
    if ha_url and ha_token:
        stt_entity = services.get("stt_entity", "").strip()
        tts_entity = services.get("tts_entity", "").strip()
        if stt_entity:
            stt = {
                "ha_url": ha_url,
                "ha_token": ha_token,
                "stt_entity": stt_entity,
                "stt_language": services.get("stt_language", "de-DE"),
            }
        if tts_entity:
            tts = {
                "ha_url": ha_url,
                "ha_token": ha_token,
                "tts_entity": tts_entity,
                "tts_language": services.get("stt_language", "de-DE"),
                "tts_voice": services.get("tts_voice", ""),
                "tts_also_text": services.get("tts_also_text", False),
            }

    lid_mappings = {}
    for user in cfg.get("users", []):
        phone = user.get("whatsapp_phone", "").strip()
        lid   = user.get("whatsapp_lid", "").strip()
        if phone and lid:
            lid_mappings[lid] = f"{phone}@s.whatsapp.net"

    return {"mode": wa.get("mode", "separate"), "self_prefix": wa.get("self_prefix", "!h "), "routes": routes, "stt": stt, "tts": tts, "lid_mappings": lid_mappings}


# ── WhatsApp Proxy (Admin-Modus-Router) ──────────────────────────────────────

@router.post("/api/wa-proxy/{user_id}/chat")
async def wa_proxy_chat(user_id: str, request: Request):
    """WhatsApp-Proxy: Empfängt Nachrichten von der Bridge und routet sie."""
    import httpx
    from core import whatsapp_router as _wa_router

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    message = (body.get("message") or "").strip()[:4000]
    channel = body.get("channel", "whatsapp")
    if not message:
        raise HTTPException(400, "message darf nicht leer sein")

    cfg = load_config()
    users = cfg.get("users", [])

    user = next((u for u in users if u.get("id") == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")

    phone = user.get("whatsapp_phone", "").strip()
    if not phone:
        raise HTTPException(400, f"User '{user_id}' hat keine whatsapp_phone konfiguriert")

    # Slash-Befehl prüfen
    if message.startswith("/"):
        handled, response = _wa_router.handle_slash_command(phone, message, users)
        if handled:
            return {"response": response, "instance": user_id, "command": True}

    # Auto-Timeout prüfen
    current_mode = _wa_router.get_mode(phone)
    if current_mode == "admin-timeout":
        timeout_note = "Admin-Modus nach 30 Min beendet."
        target_instance = user_id
        msg_to_send = message
        agent_url = get_agent_url(target_instance)
        if not agent_url:
            return {"response": timeout_note, "instance": user_id}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{agent_url}/chat",
                    json={"message": msg_to_send, "channel": channel},
                )
                r.raise_for_status()
                agent_resp = r.json().get("response", "")
            return {"response": f"{timeout_note}\n\n{agent_resp}", "instance": target_instance}
        except Exception:
            return {"response": timeout_note, "instance": user_id}

    # Modus und Ziel bestimmen
    target_instance = _wa_router.resolve_instance(phone, users)
    msg_to_send = _wa_router.build_message(phone, message, users)
    is_admin_mode = current_mode == "admin"
    _wa_router.update_activity(phone)

    if not target_instance:
        raise HTTPException(503, f"Kein Routing für User '{user_id}' möglich")

    agent_url = get_agent_url(target_instance)
    if not agent_url:
        raise HTTPException(503, f"Keine Agent-URL für '{target_instance}' konfiguriert")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{agent_url}/chat",
                json={"message": msg_to_send, "channel": channel},
            )
            r.raise_for_status()
            agent_response = r.json().get("response", "")
    except httpx.ConnectError:
        raise HTTPException(503, f"Agent '{target_instance}' nicht erreichbar")
    except httpx.TimeoutException:
        raise HTTPException(504, "Agent hat nicht rechtzeitig geantwortet")
    except Exception as e:
        raise HTTPException(502, f"Agent-Fehler: {str(e)[:200]}")

    if is_admin_mode and not agent_response.startswith("[Admin]"):
        agent_response = f"[Admin] {agent_response}"

    return {"response": agent_response, "instance": target_instance}
