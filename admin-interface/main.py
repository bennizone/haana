"""
HAANA Admin-Interface – FastAPI Backend

Routen:
  GET  /                              → index.html (SPA)
  GET  /api/conversations/{instance} → letzte Konversationen
  GET  /api/logs/{category}          → letzte Log-Einträge (memory-ops, tool-calls)
  GET  /api/instances                → verfügbare Instanzen
  GET  /api/config                   → aktuelle Konfiguration
  POST /api/config                   → Konfiguration speichern
  GET  /api/claude-md/{instance}     → CLAUDE.md einer Instanz lesen
  POST /api/claude-md/{instance}     → CLAUDE.md speichern
  GET  /api/status                   → Systemstatus (Qdrant, Ollama, Log-Stats)
  GET  /api/events/{instance}        → SSE-Stream für neue Konversationen
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="HAANA Admin", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

# ── Pfade ────────────────────────────────────────────────────────────────────

DATA_ROOT  = Path(os.environ.get("HAANA_DATA_DIR",  "/data"))
LOG_ROOT   = Path(os.environ.get("HAANA_LOG_DIR",   "/data/logs"))
CONF_FILE  = Path(os.environ.get("HAANA_CONF_FILE", "/data/config/config.json"))
INST_DIR   = Path(os.environ.get("HAANA_INST_DIR",  "/app/instanzen"))

INSTANCES = ["alice", "bob", "ha-assist", "ha-advanced"]

# ── Default-Konfiguration ────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "llm_providers": [
        {"slot": 1, "name": "Anthropic (Primär)", "type": "anthropic",
         "url": "", "key": "", "model": "claude-sonnet-4-6"},
        {"slot": 2, "name": "Fallback Cloud",     "type": "anthropic",
         "url": "", "key": "", "model": "claude-haiku-4-5-20251001"},
        {"slot": 3, "name": "Ollama (Lokal)",      "type": "ollama",
         "url": os.environ.get("OLLAMA_URL", "http://10.83.1.110:11434"),
         "key": "", "model": "ministral-3-32k:3b"},
        {"slot": 4, "name": "Custom",              "type": "custom",
         "url": "", "key": "", "model": ""},
    ],
    "use_cases": {
        "chat":              {"label": "Chat (WhatsApp/Webchat)", "primary": 1, "fallback": 2},
        "voice_tier2":       {"label": "Voice Tier 2",           "primary": 3, "fallback": 3},
        "memory_extraction": {"label": "Memory-Extraktion",      "primary": 3, "fallback": 3},
        "embeddings":        {"label": "Embeddings",             "primary": 3, "fallback": 3},
        "daily_brief":       {"label": "Daily Brief",            "primary": 2, "fallback": 3},
    },
    "memory": {
        "window_size":    int(os.environ.get("HAANA_WINDOW_SIZE",    "20")),
        "window_minutes": int(os.environ.get("HAANA_WINDOW_MINUTES", "60")),
        "min_messages":   5,
    },
    "services": {
        "ha_url":    os.environ.get("HA_URL",    ""),
        "ha_token":  "",
        "ollama_url": os.environ.get("OLLAMA_URL", "http://10.83.1.110:11434"),
        "qdrant_url": os.environ.get("QDRANT_URL", "http://qdrant:6333"),
    },
}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONF_FILE.exists():
        try:
            return json.loads(CONF_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_CONFIG


def save_config(cfg: dict) -> None:
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONF_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def read_recent_logs(category: str, sub: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Liest die letzten N Einträge (neueste zuerst) einer Log-Kategorie."""
    import glob
    pattern = str((LOG_ROOT / category / sub / "*.jsonl") if sub else (LOG_ROOT / category / "*.jsonl"))
    files = sorted(glob.glob(pattern), reverse=True)
    records: list[dict] = []
    for filepath in files:
        try:
            lines = Path(filepath).read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
            if len(records) >= limit:
                return records
    return records


def log_file_for(instance: str) -> Optional[Path]:
    """Gibt den Pfad zur heutigen Konversations-Log-Datei zurück."""
    today = datetime.now().strftime("%Y-%m-%d")
    p = LOG_ROOT / "conversations" / instance / f"{today}.jsonl"
    return p if p.exists() else None


# ── HTML ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "instances": INSTANCES,
    })


# ── API: Konversationen ───────────────────────────────────────────────────────

@app.get("/api/instances")
async def get_instances():
    result = []
    for inst in INSTANCES:
        inst_dir = LOG_ROOT / "conversations" / inst
        count = sum(1 for _ in inst_dir.glob("*.jsonl")) if inst_dir.exists() else 0
        result.append({"name": inst, "log_days": count})
    return result


@app.get("/api/conversations/{instance}")
async def get_conversations(instance: str, limit: int = 50):
    if instance not in INSTANCES:
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")
    records = read_recent_logs("conversations", instance, limit)
    return records


# ── API: Logs ─────────────────────────────────────────────────────────────────

@app.get("/api/logs/{category}")
async def get_logs(category: str, limit: int = 100):
    valid = {"memory-ops", "tool-calls", "llm-calls"}
    if category not in valid:
        raise HTTPException(400, f"Kategorie muss eine von {valid} sein")
    return read_recent_logs(category, limit=limit)


# ── API: Konfiguration ────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    return load_config()


@app.post("/api/config")
async def post_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")
    save_config(body)
    return {"ok": True}


# ── API: CLAUDE.md ────────────────────────────────────────────────────────────

@app.get("/api/claude-md/{instance}")
async def get_claude_md(instance: str):
    if instance not in INSTANCES:
        raise HTTPException(404, "Instanz nicht gefunden")
    path = INST_DIR / instance / "CLAUDE.md"
    if not path.exists():
        raise HTTPException(404, "CLAUDE.md nicht gefunden")
    return {"content": path.read_text(encoding="utf-8")}


@app.post("/api/claude-md/{instance}")
async def post_claude_md(instance: str, request: Request):
    if instance not in INSTANCES:
        raise HTTPException(404, "Instanz nicht gefunden")
    try:
        body = await request.json()
        content = body.get("content", "")
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")
    path = INST_DIR / instance / "CLAUDE.md"
    if not path.parent.exists():
        raise HTTPException(404, "Instanz-Verzeichnis nicht gefunden")
    path.write_text(content, encoding="utf-8")
    return {"ok": True}


# ── API: Status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    ollama_url = cfg.get("services", {}).get("ollama_url", "")

    status: dict = {"qdrant": "unknown", "ollama": "unknown", "logs": {}}

    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{qdrant_url}/collections")
            colls = r.json().get("result", {}).get("collections", [])
            status["qdrant"] = {"ok": True, "collections": [c["name"] for c in colls]}
        except Exception as e:
            status["qdrant"] = {"ok": False, "error": str(e)}

        if ollama_url:
            try:
                r = await client.get(f"{ollama_url}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                status["ollama"] = {"ok": True, "models": models}
            except Exception as e:
                status["ollama"] = {"ok": False, "error": str(e)}

    # Log-Statistiken
    for inst in INSTANCES:
        inst_log = LOG_ROOT / "conversations" / inst
        if inst_log.exists():
            days = sorted(inst_log.glob("*.jsonl"), reverse=True)
            status["logs"][inst] = {
                "days": len(days),
                "latest": days[0].name.replace(".jsonl", "") if days else None,
            }

    return status


# ── SSE: Echtzeit-Konversationen ──────────────────────────────────────────────

@app.get("/api/events/{instance}")
async def sse_events(instance: str, request: Request):
    """
    Server-Sent Events: streamt neue Konversationszeilen sobald sie erscheinen.
    Pollt alle 2 Sekunden die aktuelle Tages-Log-Datei.
    """
    if instance not in INSTANCES:
        raise HTTPException(404, "Instanz nicht gefunden")

    async def event_generator():
        last_pos = 0

        # Bestehende Zeilen beim Connect überspringen (nur neue senden)
        today_path = LOG_ROOT / "conversations" / instance / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        if today_path.exists():
            last_pos = today_path.stat().st_size

        yield f"data: {json.dumps({'type': 'connected', 'instance': instance})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            # Tages-Datei kann sich von Tag zu Tag ändern
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
                last_pos = 0  # Neuer Tag, Position zurücksetzen

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
