"""Conversation endpoints: list, raw read/write, SSE events, chat proxy, instances."""

import asyncio
import json
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .deps import (
    load_config, read_recent_logs, get_all_instances, get_agent_url, LOG_ROOT,
)

router = APIRouter(tags=["conversations"])


@router.get("/api/instances")
async def get_instances():
    result = []
    for inst in get_all_instances():
        inst_dir = LOG_ROOT / "conversations" / inst
        count = sum(1 for _ in inst_dir.glob("*.jsonl")) if inst_dir.exists() else 0
        result.append({"name": inst, "log_days": count})
    return result


@router.get("/api/conversations/{instance}")
async def get_conversations(instance: str, limit: int = 50):
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")
    records = read_recent_logs("conversations", instance, limit)
    return records


@router.get("/api/conversations/{instance}/files")
async def list_conversation_files(instance: str):
    """Listet alle vorhandenen Datumsdateien für eine Instanz."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    inst_log = LOG_ROOT / "conversations" / instance
    if not inst_log.exists():
        return []
    files = sorted(inst_log.glob("*.jsonl"), reverse=True)
    result = []
    for f in files:
        try:
            lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
            result.append({"date": f.stem, "entries": len(lines), "size_kb": round(f.stat().st_size / 1024, 1)})
        except Exception:
            result.append({"date": f.stem, "entries": 0, "size_kb": 0})
    return result


@router.get("/api/conversations/{instance}/raw/{date}")
async def get_conversation_raw(instance: str, date: str):
    """Gibt den rohen JSONL-Inhalt einer Datums-Log-Datei zurück."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(400, "Ungültiges Datumsformat (erwartet YYYY-MM-DD)")
    path = LOG_ROOT / "conversations" / instance / f"{date}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    return {"content": path.read_text(encoding="utf-8"), "entries": sum(1 for ln in path.read_text().splitlines() if ln.strip())}


@router.put("/api/conversations/{instance}/raw/{date}")
async def put_conversation_raw(instance: str, date: str, request: Request):
    """Überschreibt eine Datums-Log-Datei mit neuem Inhalt."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(400, "Ungültiges Datumsformat")
    try:
        body = await request.json()
        content = body.get("content", "")
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")
    path = LOG_ROOT / "conversations" / instance / f"{date}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    entries = sum(1 for ln in content.splitlines() if ln.strip())
    return {"ok": True, "entries": entries}


# ── Chat-Proxy ───────────────────────────────────────────────────────────────

@router.post("/api/chat/{instance}")
async def chat_proxy(instance: str, request: Request):
    """Sendet eine Nachricht an eine Agent-Instanz."""
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message darf nicht leer sein")

    agent_url = get_agent_url(instance)
    if not agent_url:
        raise HTTPException(503, f"Keine Agent-URL für '{instance}' konfiguriert")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{agent_url}/chat",
                json={"message": message, "channel": "webchat"},
            )
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(503, f"Agent '{instance}' nicht erreichbar (läuft der Container?)")
    except httpx.TimeoutException:
        raise HTTPException(504, "Agent hat nicht rechtzeitig geantwortet")
    except Exception as e:
        raise HTTPException(502, f"Agent-Fehler: {str(e)[:200]}")


# ── SSE Events ───────────────────────────────────────────────────────────────

@router.get("/api/events/{instance}")
async def sse_events(instance: str, request: Request):
    """Server-Sent Events: streamt neue Konversationszeilen."""
    if instance not in get_all_instances():
        raise HTTPException(404, "Instanz nicht gefunden")

    async def event_generator():
        last_pos = 0

        today_path = LOG_ROOT / "conversations" / instance / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        if today_path.exists():
            last_pos = today_path.stat().st_size

        yield f"data: {json.dumps({'type': 'connected', 'instance': instance})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            today = datetime.now().strftime("%Y-%m-%d")
            log_path = LOG_ROOT / "conversations" / instance / f"{today}.jsonl"

            if log_path.exists():
                size = log_path.stat().st_size
                if size > last_pos:
                    with log_path.open("r", encoding="utf-8") as f:
                        f.seek(last_pos)
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    record = json.loads(line)
                                    yield f"data: {json.dumps({'type': 'conversation', 'record': record})}\n\n"
                                except json.JSONDecodeError:
                                    pass
                    last_pos = log_path.stat().st_size
            else:
                last_pos = 0

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
