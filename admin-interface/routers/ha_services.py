"""Home Assistant service endpoints: test-ha, test-ha-mcp, pipelines, stt-tts, ha-users."""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from .deps import load_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ha-services"])


@router.post("/api/test-ha")
async def test_ha(request: Request):
    """Testet Home Assistant URL + Long-Lived Token."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    ha_url = (body.get("ha_url") or "").rstrip("/")
    ha_token = (body.get("ha_token") or "").strip()
    if not ha_url:
        return {"ok": False, "detail": "ha_url fehlt"}
    if not ha_token:
        return {"ok": False, "detail": "ha_token fehlt"}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{ha_url}/api/",
                headers={"Authorization": f"Bearer {ha_token}"},
            )
            if r.status_code == 401:
                return {"ok": False, "detail": "Token ungültig (401 Unauthorized)"}
            if r.status_code == 200:
                msg = r.json().get("message", "API erreichbar")
                return {"ok": True, "detail": msg}
            return {"ok": r.status_code < 400, "detail": f"HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "detail": "Verbindung abgelehnt – URL erreichbar?"}
    except httpx.TimeoutException:
        return {"ok": False, "detail": "Timeout (>8s)"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@router.post("/api/test-ha-mcp")
async def test_ha_mcp(request: Request):
    """Testet den HA MCP Server SSE-Endpunkt."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    mcp_url = (body.get("mcp_url") or "").strip()
    token = (body.get("token") or "").strip()

    if not mcp_url:
        return {"ok": False, "detail": "MCP URL fehlt"}
    if not token:
        return {"ok": False, "detail": "Token fehlt"}

    mcp_type = (body.get("mcp_type") or "extended").strip()

    import httpx
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=8.0, read=5.0, write=5.0, pool=5.0)
        ) as client:
            if mcp_type == "builtin":
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
                async with client.stream("GET", mcp_url, headers=headers) as r:
                    ct = r.headers.get("content-type", "")
                    sc = r.status_code
                    if sc == 401:
                        return {"ok": False, "detail": "Token ungültig (401 Unauthorized)"}
                    if sc == 404:
                        return {"ok": False, "detail": "Endpunkt nicht gefunden (404) – MCP Server in HA aktiviert?"}
                    if sc in (200, 206):
                        if "event-stream" in ct:
                            return {"ok": True, "detail": "MCP Server erreichbar (SSE)"}
                        return {"ok": True, "detail": f"Erreichbar · HTTP {sc} · {ct or 'kein Content-Type'}"}
                    return {"ok": sc < 400, "detail": f"HTTP {sc}"}
            else:
                headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-03-26",
                                       "capabilities": {},
                                       "clientInfo": {"name": "haana-test", "version": "1.0"}}}
                r = await client.post(mcp_url, json=init_msg, headers=headers)
                sc = r.status_code
                if sc == 401:
                    return {"ok": False, "detail": "Token ungültig (401)"}
                if sc == 404:
                    return {"ok": False, "detail": "Endpunkt nicht gefunden (404)"}
                if sc in (200, 202):
                    return {"ok": True, "detail": f"MCP Server erreichbar (HTTP, Status {sc})"}
                ct = r.headers.get("content-type", "")
                if "event-stream" in ct:
                    return {"ok": True, "detail": "MCP Server erreichbar (SSE-over-HTTP)"}
                return {"ok": sc < 400, "detail": f"HTTP {sc}"}
    except httpx.ConnectError:
        return {"ok": False, "detail": "Verbindung abgelehnt – HA erreichbar?"}
    except httpx.ReadTimeout:
        return {"ok": True, "detail": "MCP Server erreichbar (Timeout nach Connect – normal bei SSE)"}
    except httpx.TimeoutException:
        return {"ok": False, "detail": "Connect-Timeout – HA erreichbar?"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@router.get("/api/ha-pipelines")
async def ha_pipelines():
    """Listet verfügbare Voice-Pipelines aus Home Assistant auf."""
    cfg = load_config()
    ha_url = cfg.get("services", {}).get("ha_url", "").rstrip("/")
    ha_token = cfg.get("services", {}).get("ha_token", "").strip()
    if not ha_url or not ha_token:
        return {"ok": False, "error": "HA URL oder Token nicht konfiguriert", "pipelines": []}
    import websockets, ssl as _ssl
    try:
        ws_url = ha_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/api/websocket"
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
        async with websockets.connect(ws_url, ssl=ssl_ctx, open_timeout=8) as ws:
            msg = json.loads(await ws.recv())
            await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_ok":
                return {"ok": False, "error": "HA Token ungültig", "pipelines": []}
            await ws.send(json.dumps({"id": 1, "type": "assist_pipeline/pipeline/list"}))
            msg = json.loads(await ws.recv())
            if not msg.get("success"):
                return {"ok": False, "error": "Pipelines nicht verfügbar", "pipelines": []}
            raw_pipelines = msg.get("result", {}).get("pipelines", [])
            pipelines = []
            for p in raw_pipelines:
                pipelines.append({
                    "id": p.get("id", ""),
                    "name": p.get("name", ""),
                    "stt_engine": p.get("stt_engine", ""),
                    "stt_language": p.get("stt_language", ""),
                    "tts_engine": p.get("tts_engine", ""),
                    "tts_language": p.get("tts_language", ""),
                    "tts_voice": p.get("tts_voice", ""),
                })
            return {"ok": True, "pipelines": pipelines}
    except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError):
        return {"ok": False, "error": "HA nicht erreichbar", "pipelines": []}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "pipelines": []}


@router.get("/api/ha-stt-tts")
async def ha_stt_tts():
    """Listet verfügbare STT- und TTS-Entitäten aus Home Assistant auf."""
    cfg = load_config()
    ha_url = cfg.get("services", {}).get("ha_url", "").rstrip("/")
    ha_token = cfg.get("services", {}).get("ha_token", "").strip()
    if not ha_url or not ha_token:
        return {"ok": False, "error": "HA URL oder Token nicht konfiguriert", "stt": [], "tts": []}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{ha_url}/api/states",
                headers={"Authorization": f"Bearer {ha_token}"},
            )
            if r.status_code == 401:
                return {"ok": False, "error": "HA Token ungültig", "stt": [], "tts": []}
            r.raise_for_status()
            stt_entities = []
            tts_entities = []
            for state in r.json():
                eid = state.get("entity_id", "")
                name = state.get("attributes", {}).get("friendly_name", eid)
                if eid.startswith("stt."):
                    stt_entities.append({"id": eid, "name": name})
                elif eid.startswith("tts."):
                    tts_entities.append({"id": eid, "name": name})
            return {"ok": True, "stt": stt_entities, "tts": tts_entities}
    except httpx.ConnectError:
        return {"ok": False, "error": "HA nicht erreichbar", "stt": [], "tts": []}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "stt": [], "tts": []}


@router.get("/api/ha-users")
async def ha_users():
    """Listet Home Assistant Person-Entitäten."""
    cfg = load_config()
    services = cfg.get("services", {})

    cached = services.get("ha_persons", [])
    if cached:
        persons = [
            {
                "id": p.get("id", ""),
                "uid": p.get("uid", p.get("id", "").replace("person.", "")),
                "name": p.get("display_name", p.get("name", p.get("uid", ""))),
                "friendly_name": p.get("display_name", p.get("name", p.get("uid", ""))),
                "display_name": p.get("display_name", p.get("name", p.get("uid", ""))),
            }
            for p in cached
        ]
        return {"ok": True, "users": persons, "source": "companion"}

    ha_url = (services.get("ha_url", "") or os.environ.get("HA_URL", "")).rstrip("/")
    ha_token = services.get("ha_token", "").strip()
    if not ha_url or not ha_token:
        return {"ok": False, "error": "HA URL oder Token nicht konfiguriert", "users": []}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{ha_url}/api/states",
                headers={"Authorization": f"Bearer {ha_token}"},
            )
            if r.status_code == 401:
                return {"ok": False, "error": "HA Token ungültig", "users": []}
            r.raise_for_status()
            persons = []
            for state in r.json():
                eid = state.get("entity_id", "")
                if eid.startswith("person."):
                    uid = eid[len("person."):]
                    name = state.get("attributes", {}).get("friendly_name", uid)
                    persons.append({"id": eid, "uid": uid, "name": name, "friendly_name": name, "display_name": name})
            return {"ok": True, "users": persons, "source": "live"}
    except httpx.ConnectError:
        return {"ok": False, "error": "HA nicht erreichbar", "users": []}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "users": []}
