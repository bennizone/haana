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
import glob as _glob

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

# ── Rebuild-Zustand (pro Instanz) ─────────────────────────────────────────────
# status: "idle" | "running" | "done" | "error" | "cancelled"
_rebuild: dict[str, dict] = {
    inst: {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}
    for inst in ["alice", "bob", "ha-assist", "ha-advanced"]
}


# ── Log-Retention Cleanup ─────────────────────────────────────────────────────

def _cleanup_logs_once():
    """Löscht Log-Dateien die älter als konfigurierte Retention sind."""
    cfg = load_config()
    retention: dict = cfg.get("log_retention", {})

    now = time.time()
    deleted = 0
    for category, days in retention.items():
        if days is None:
            continue  # niemals löschen
        cutoff = now - int(days) * 86400
        pattern = str(LOG_ROOT / category / "**" / "*.jsonl")
        for fpath in _glob.glob(pattern, recursive=True):
            try:
                if Path(fpath).stat().st_mtime < cutoff:
                    Path(fpath).unlink()
                    deleted += 1
            except Exception:
                pass
    if deleted:
        import logging as _log
        _log.getLogger(__name__).info(f"[Cleanup] {deleted} Log-Datei(en) gelöscht")


async def _cleanup_loop():
    """Läuft beim Start und dann täglich."""
    _cleanup_logs_once()
    while True:
        await asyncio.sleep(86400)
        _cleanup_logs_once()


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_cleanup_loop())

# ── Pfade ────────────────────────────────────────────────────────────────────

DATA_ROOT  = Path(os.environ.get("HAANA_DATA_DIR",  "/data"))
LOG_ROOT   = Path(os.environ.get("HAANA_LOG_DIR",   "/data/logs"))
CONF_FILE  = Path(os.environ.get("HAANA_CONF_FILE", "/data/config/config.json"))
INST_DIR   = Path(os.environ.get("HAANA_INST_DIR",  "/app/instanzen"))

INSTANCES = ["alice", "bob", "ha-assist", "ha-advanced"]

# Agent-API URLs (aus Env, Fallback für lokale Entwicklung)
AGENT_URLS: dict[str, str] = {
    "alice":       os.environ.get("AGENT_URL_BENNI",       "http://localhost:8001"),
    "bob":        os.environ.get("AGENT_URL_DOMI",        "http://localhost:8002"),
    "ha-assist":   os.environ.get("AGENT_URL_HA_ASSIST",   "http://localhost:8003"),
    "ha-advanced": os.environ.get("AGENT_URL_HA_ADVANCED", "http://localhost:8004"),
}

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
        "daily_brief":       {"label": "Daily Brief",            "primary": 2, "fallback": 3},
    },
    "memory": {
        "window_size":    int(os.environ.get("HAANA_WINDOW_SIZE",    "20")),
        "window_minutes": int(os.environ.get("HAANA_WINDOW_MINUTES", "60")),
        "min_messages":   5,
    },
    "embedding": {
        "provider": "ollama",
        "model":    os.environ.get("HAANA_EMBEDDING_MODEL", "bge-m3"),
        "dims":     int(os.environ.get("HAANA_EMBEDDING_DIMS", "1024")),
    },
    "log_retention": {
        "conversations": None,   # niemals löschen
        "llm-calls":     30,
        "tool-calls":    30,
        "memory-ops":    30,
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
            cfg = json.loads(CONF_FILE.read_text(encoding="utf-8"))
            # Embeddings-Use-Case entfernen (wurde in separate Sektion ausgelagert)
            cfg.get("use_cases", {}).pop("embeddings", None)
            return cfg
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
            coll_names = [c["name"] for c in colls]
            # Prüfe ob Collections leer sind (für Rebuild-Empfehlung)
            total_vectors = 0
            for cname in coll_names:
                try:
                    cr = await client.get(f"{qdrant_url}/collections/{cname}")
                    total_vectors += cr.json().get("result", {}).get("vectors_count", 0) or 0
                except Exception:
                    pass
            # Konversations-Logs vorhanden?
            conv_files = _glob.glob(str(LOG_ROOT / "conversations" / "**" / "*.jsonl"), recursive=True)
            has_logs = len(conv_files) > 0
            status["qdrant"] = {
                "ok": True,
                "collections": coll_names,
                "rebuild_suggested": has_logs and total_vectors == 0,
            }
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


# ── Chat-Proxy (Webchat → Agent-API) ─────────────────────────────────────────

@app.post("/api/chat/{instance}")
async def chat_proxy(instance: str, request: Request):
    """
    Sendet eine Nachricht an eine Agent-Instanz und gibt die Antwort zurück.
    Proxy zur Agent-API (core/api.py, läuft im Agent-Container).
    """
    if instance not in INSTANCES:
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message darf nicht leer sein")

    agent_url = AGENT_URLS.get(instance)
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


@app.post("/api/test-connection")
async def test_connection(request: Request):
    """
    Testet eine Verbindung zu einem Dienst.
    Body: {"type": "qdrant"|"ollama"|"http", "url": "..."}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    url   = (body.get("url") or "").strip()
    type_ = (body.get("type") or "http").strip()

    if not url:
        raise HTTPException(400, "url fehlt")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if type_ == "qdrant":
                r = await client.get(f"{url}/collections")
                colls = r.json().get("result", {}).get("collections", [])
                return {"ok": True, "detail": f"{len(colls)} Collection(s)"}
            elif type_ == "ollama":
                r = await client.get(f"{url}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return {"ok": True, "detail": f"{len(models)} Modell(e)"}
            else:
                r = await client.get(url)
                return {"ok": r.status_code < 400, "detail": f"HTTP {r.status_code}"}
    except httpx.ConnectError as e:
        return {"ok": False, "detail": f"Verbindung abgelehnt: {str(e)[:100]}"}
    except httpx.TimeoutException:
        return {"ok": False, "detail": "Timeout (>5s)"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@app.post("/api/rebuild-memory/{instance}")
async def start_rebuild(instance: str):
    """Startet den Memory-Rebuild aus Konversations-Logs für eine Instanz."""
    if instance not in INSTANCES:
        raise HTTPException(404)

    state = _rebuild.get(instance)
    if state and state["status"] == "running":
        return {"ok": False, "error": "Rebuild läuft bereits"}

    # Konversations-Logs zählen
    conv_files = sorted(
        _glob.glob(str(LOG_ROOT / "conversations" / instance / "*.jsonl"))
    )
    total = sum(
        sum(1 for line in Path(f).read_text(encoding="utf-8").splitlines() if line.strip())
        for f in conv_files
        if Path(f).exists()
    )

    if total == 0:
        return {"ok": False, "error": "Keine Konversations-Logs gefunden"}

    _rebuild[instance] = {
        "status": "running", "done": 0, "total": total,
        "started": time.time(), "error": "",
    }

    async def _run():
        state = _rebuild[instance]
        agent_url = AGENT_URLS.get(instance, "")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for fpath in conv_files:
                    lines = Path(fpath).read_text(encoding="utf-8").splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if state["status"] == "cancelled":
                            return
                        try:
                            rec = json.loads(line)
                            await client.post(
                                f"{agent_url}/rebuild-entry",
                                json={
                                    "user":      rec.get("user", ""),
                                    "assistant": rec.get("assistant", ""),
                                },
                            )
                        except Exception:
                            pass
                        state["done"] += 1
            state["status"] = "done"
        except Exception as e:
            state["status"] = "error"
            state["error"]  = str(e)[:200]

    asyncio.create_task(_run())
    return {"ok": True, "total": total}


@app.post("/api/rebuild-cancel/{instance}")
async def cancel_rebuild(instance: str):
    """Bricht einen laufenden Rebuild ab."""
    state = _rebuild.get(instance)
    if state and state["status"] == "running":
        state["status"] = "cancelled"
        return {"ok": True}
    return {"ok": False, "error": "Kein laufender Rebuild"}


@app.get("/api/rebuild-progress/{instance}")
async def rebuild_progress(instance: str, request: Request):
    """SSE-Stream mit Rebuild-Fortschritt."""
    if instance not in INSTANCES:
        raise HTTPException(404)

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            state = _rebuild.get(instance, {})
            done    = state.get("done", 0)
            total   = state.get("total", 0)
            status  = state.get("status", "idle")
            elapsed = time.time() - state.get("started", time.time())
            eta_s   = int((total - done) * (elapsed / done)) if done > 0 else None
            yield f"data: {json.dumps({'done': done, 'total': total, 'status': status, 'eta_s': eta_s, 'error': state.get('error','')})}\n\n"
            if status in ("done", "error", "idle", "cancelled"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/fetch-models")
async def fetch_models(request: Request):
    """
    Fragt verfügbare Modelle eines LLM-Providers ab.
    Body: {"type": "anthropic"|"ollama"|"custom", "url": "...", "key": "..."}
    Returns: {"models": ["model-id", ...]}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    type_ = (body.get("type") or "").strip()
    url   = (body.get("url")  or "").strip()
    key   = (body.get("key")  or "").strip()

    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if type_ == "ollama":
                target = url or "http://localhost:11434"
                r = await client.get(f"{target}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return {"models": models}
            elif type_ == "anthropic":
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
                r = await client.get("https://api.anthropic.com/v1/models", headers=headers)
                if r.status_code == 200:
                    models = [m["id"] for m in r.json().get("data", [])]
                    return {"models": models}
                return {"models": [], "error": f"HTTP {r.status_code}"}
            else:
                return {"models": [], "manual": True}
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}


@app.get("/api/agent-health/{instance}")
async def agent_health(instance: str):
    """Prüft ob ein Agent-Container erreichbar ist."""
    if instance not in INSTANCES:
        raise HTTPException(404)
    agent_url = AGENT_URLS.get(instance, "")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{agent_url}/health")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
