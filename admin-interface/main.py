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
  GET  /api/users                    → User-Liste
  POST /api/users                    → User anlegen (inkl. Container-Start)
  PATCH /api/users/{user_id}         → User aktualisieren (Container-Restart)
  DELETE /api/users/{user_id}        → User löschen (Container entfernen)
  POST /api/users/{user_id}/restart  → Container neu starten
"""

import asyncio
import json
import os
import re
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

try:
    import docker as _docker
    _docker_client = _docker.from_env()
except Exception:
    _docker_client = None

app = FastAPI(title="HAANA Admin", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

# ── Rebuild-Zustand (pro Instanz) ─────────────────────────────────────────────
# status: "idle" | "running" | "done" | "error" | "cancelled"
_rebuild: dict[str, dict] = {
    inst: {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}
    for inst in ["alice", "bob", "ha-assist", "ha-advanced"]
}


def _sync_rebuild_state():
    """Rebuild-State mit dynamischen Usern aus config.json synchronisieren."""
    cfg = load_config()
    for u in cfg.get("users", []):
        uid = u.get("id", "")
        if uid and uid not in _rebuild:
            _rebuild[uid] = {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}


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
    # Rebuild-Zustand aus config.json-Users erweitern (dynamische Instanzen)
    _sync_rebuild_state()

# ── Pfade ────────────────────────────────────────────────────────────────────

DATA_ROOT  = Path(os.environ.get("HAANA_DATA_DIR",  "/data"))
LOG_ROOT   = Path(os.environ.get("HAANA_LOG_DIR",   "/data/logs"))
CONF_FILE  = Path(os.environ.get("HAANA_CONF_FILE", "/data/config/config.json"))
INST_DIR   = Path(os.environ.get("HAANA_INST_DIR",  "/app/instanzen"))

INSTANCES = ["alice", "bob", "ha-assist", "ha-advanced"]  # statische Basis-Instanzen

def get_all_instances() -> list[str]:
    """Alle Instanzen: statische + dynamische User aus config.json."""
    cfg = load_config()
    user_ids = [u["id"] for u in cfg.get("users", []) if u.get("id")]
    # Combine: statische zuerst, dann weitere dynamische (de-dup)
    result = list(INSTANCES)
    for uid in user_ids:
        if uid not in result:
            result.append(uid)
    return result

# Agent-API URLs (aus Env, Fallback für lokale Entwicklung)
AGENT_URLS: dict[str, str] = {
    "alice":       os.environ.get("AGENT_URL_BENNI",       "http://localhost:8001"),
    "bob":        os.environ.get("AGENT_URL_DOMI",        "http://localhost:8002"),
    "ha-assist":   os.environ.get("AGENT_URL_HA_ASSIST",   "http://localhost:8003"),
    "ha-advanced": os.environ.get("AGENT_URL_HA_ADVANCED", "http://localhost:8004"),
}

# Docker-Management Konstanten
HOST_BASE       = os.environ.get("HAANA_HOST_BASE",        "/opt/haana")
DATA_VOLUME     = os.environ.get("HAANA_DATA_VOLUME",       "haana_haana-data")
COMPOSE_NETWORK = os.environ.get("HAANA_COMPOSE_NETWORK",  "haana_default")
AGENT_IMAGE     = os.environ.get("HAANA_AGENT_IMAGE",       "haana-instanz-alice")
TEMPLATES_DIR   = INST_DIR / "templates"

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
    "users": [
        {
            "id": "alice", "display_name": "Alice", "role": "admin",
            "primary_llm_slot": 1, "extraction_llm_slot": 3,
            "ha_user": "alice", "whatsapp_jid": "", "whatsapp_mode": "separate",
            "api_port": 8001, "container_name": "haana-instanz-alice-1",
            "claude_md_template": "admin",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "bob", "display_name": "Bob", "role": "user",
            "primary_llm_slot": 1, "extraction_llm_slot": 3,
            "ha_user": "bob", "whatsapp_jid": "", "whatsapp_mode": "separate",
            "api_port": 8002, "container_name": "haana-instanz-bob-1",
            "claude_md_template": "user",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "ha-assist", "display_name": "HAANA Voice", "role": "voice",
            "system": True,
            "primary_llm_slot": 3, "extraction_llm_slot": 3,
            "ha_user": "", "whatsapp_jid": "", "whatsapp_mode": "separate",
            "api_port": 8003, "container_name": "haana-instanz-ha-assist-1",
            "claude_md_template": "ha-assist",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "ha-advanced", "display_name": "HAANA Advanced", "role": "voice-advanced",
            "system": True,
            "primary_llm_slot": 1, "extraction_llm_slot": 3,
            "ha_user": "", "whatsapp_jid": "", "whatsapp_mode": "separate",
            "api_port": 8004, "container_name": "haana-instanz-ha-advanced-1",
            "claude_md_template": "ha-advanced",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
    ],
}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

_SYSTEM_USERS = {
    "ha-assist":   DEFAULT_CONFIG["users"][2],  # HAANA Voice
    "ha-advanced": DEFAULT_CONFIG["users"][3],  # HAANA Advanced
}
_SYSTEM_USER_IDS = set(_SYSTEM_USERS.keys())


def _ensure_system_users(cfg: dict) -> None:
    """Stellt sicher, dass die System-Instanzen immer in users vorhanden sind (max. 1×)."""
    users = cfg.setdefault("users", [])
    # Duplikate/veraltete System-Einträge entfernen, dann wieder einfügen
    cfg["users"] = [u for u in users if u.get("id") not in _SYSTEM_USER_IDS]
    # Am Ende anfügen (nach normalen Usern)
    for sys_user in _SYSTEM_USERS.values():
        cfg["users"].append(sys_user)


def load_config() -> dict:
    if CONF_FILE.exists():
        try:
            cfg = json.loads(CONF_FILE.read_text(encoding="utf-8"))
            # Embeddings-Use-Case entfernen (wurde in separate Sektion ausgelagert)
            cfg.get("use_cases", {}).pop("embeddings", None)
            _ensure_system_users(cfg)
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    _ensure_system_users(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    # System-User nicht in Datei persistieren – werden immer aus Code injiziert
    to_save = {**cfg, "users": [u for u in cfg.get("users", []) if u.get("id") not in _SYSTEM_USER_IDS]}
    CONF_FILE.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "instances": get_all_instances(),
    })


# ── API: Konversationen ───────────────────────────────────────────────────────

@app.get("/api/instances")
async def get_instances():
    result = []
    for inst in get_all_instances():
        inst_dir = LOG_ROOT / "conversations" / inst
        count = sum(1 for _ in inst_dir.glob("*.jsonl")) if inst_dir.exists() else 0
        result.append({"name": inst, "log_days": count})
    return result


@app.get("/api/conversations/{instance}")
async def get_conversations(instance: str, limit: int = 50):
    if instance not in get_all_instances():
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
    if instance not in get_all_instances():
        raise HTTPException(404, "Instanz nicht gefunden")
    path = INST_DIR / instance / "CLAUDE.md"
    if not path.exists():
        raise HTTPException(404, "CLAUDE.md nicht gefunden")
    return {"content": path.read_text(encoding="utf-8")}


@app.post("/api/claude-md/{instance}")
async def post_claude_md(instance: str, request: Request):
    if instance not in get_all_instances():
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
    for inst in get_all_instances():
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
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message darf nicht leer sein")

    agent_url = _get_agent_url(instance)
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


@app.get("/api/memory-stats")
async def memory_stats():
    """
    Liefert pro Instanz: Konversations-Logs (Zeilen), Qdrant-Vektoren pro Scope.
    Wird für Rebuild-Checkboxen verwendet.
    """
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")

    # Qdrant-Vektoren pro Collection laden
    coll_vectors: dict[str, int] = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{qdrant_url}/collections")
            colls = r.json().get("result", {}).get("collections", [])
            for c in colls:
                try:
                    cr = await client.get(f"{qdrant_url}/collections/{c['name']}")
                    coll_vectors[c["name"]] = cr.json().get("result", {}).get("vectors_count", 0) or 0
                except Exception:
                    coll_vectors[c["name"]] = 0
    except Exception:
        pass

    result = []
    for inst in get_all_instances():
        # Log-Zeilen zählen
        log_entries = 0
        log_days = 0
        inst_log = LOG_ROOT / "conversations" / inst
        if inst_log.exists():
            files = list(inst_log.glob("*.jsonl"))
            log_days = len(files)
            for f in files:
                try:
                    log_entries += sum(1 for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())
                except Exception:
                    pass

        # Qdrant-Vektoren: primärer Scope ist {uid}_memory, außer System-Instanzen
        scopes: dict[str, int] = {}
        user = next((u for u in cfg.get("users", []) if u["id"] == inst), None)
        if user:
            tpl = user.get("claude_md_template", "")
            if tpl in ("ha-assist", "ha-advanced"):
                # Nur lesen – household + alle user-scopes
                for scope in ("household_memory",):
                    scopes[scope] = coll_vectors.get(scope, 0)
            else:
                for scope in (f"{inst}_memory", "household_memory"):
                    scopes[scope] = coll_vectors.get(scope, 0)
        else:
            scopes[f"{inst}_memory"] = coll_vectors.get(f"{inst}_memory", 0)
            scopes["household_memory"] = coll_vectors.get("household_memory", 0)

        total_vectors = sum(scopes.values())
        result.append({
            "instance": inst,
            "log_entries": log_entries,
            "log_days": log_days,
            "scopes": scopes,
            "total_vectors": total_vectors,
            "rebuild_suggested": log_entries > 0 and total_vectors == 0,
        })

    return result


# ── Instanz-Steuerung (Container stop/restart) ────────────────────────────────

def _get_instance_container(instance: str) -> Optional[str]:
    """Gibt Container-Name für eine Instanz zurück."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == instance), None)
    if user:
        return user.get("container_name", f"haana-instanz-{instance}-1")
    # Compose-Naming-Konvention
    return f"haana-instanz-{instance}-1"


@app.post("/api/instances/{instance}/restart")
async def restart_instance(instance: str):
    """Container einer Instanz neu starten."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    container_name = _get_instance_container(instance)
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get(container_name)
        c.restart(timeout=10)
        return {"ok": True, "container": container_name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/instances/{instance}/stop")
async def stop_instance(instance: str):
    """Container einer Instanz graceful stoppen (SIGTERM, 10s timeout)."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    container_name = _get_instance_container(instance)
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get(container_name)
        c.stop(timeout=10)
        return {"ok": True, "container": container_name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/instances/{instance}/force-stop")
async def force_stop_instance(instance: str):
    """Container einer Instanz sofort beenden (SIGKILL – laufende Memory-Extraktion geht verloren)."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    container_name = _get_instance_container(instance)
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get(container_name)
        c.kill()
        return {"ok": True, "container": container_name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/instances/qdrant/restart")
async def restart_qdrant():
    """Qdrant-Container neu starten."""
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get("haana-qdrant-1")
        c.restart(timeout=10)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── Konversations-Logs direkt lesen/schreiben (Editieren) ─────────────────────

@app.get("/api/conversations/{instance}/files")
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


@app.get("/api/conversations/{instance}/raw/{date}")
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


@app.put("/api/conversations/{instance}/raw/{date}")
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
    if instance not in get_all_instances():
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
        agent_url = _get_agent_url(instance)
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
    if instance not in get_all_instances():
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

    # Bekannte Anthropic-Modelle als Fallback
    _ANTHROPIC_KNOWN = [
        "claude-opus-4-6", "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-5", "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if type_ == "ollama":
                target = url or "http://localhost:11434"
                r = await client.get(f"{target}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return {"models": models}

            elif type_ == "minimax":
                # MiniMax: Anthropic-kompatible API
                return {"models": ["MiniMax-M2.5", "MiniMax-Text-01"]}

            elif type_ == "anthropic":
                # Wenn custom URL mit minimax → minimax-Modelle zurückgeben
                if url and "minimax" in url.lower():
                    return {"models": ["MiniMax-M2.5", "MiniMax-Text-01"]}
                # Wenn kein API-Key → Fallback-Liste
                if not key:
                    return {"models": _ANTHROPIC_KNOWN, "fallback": True}
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
                try:
                    r = await client.get("https://api.anthropic.com/v1/models", headers=headers)
                    if r.status_code == 200:
                        models = [m["id"] for m in r.json().get("data", [])]
                        return {"models": models}
                except Exception:
                    pass
                return {"models": _ANTHROPIC_KNOWN, "fallback": True}

            else:
                return {"models": [], "manual": True}
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}


# ── User-Management ───────────────────────────────────────────────────────────

def _render_claude_md(template_name: str, display_name: str, user_id: str, ha_user: str = "") -> str:
    """Generiert CLAUDE.md aus Template mit Platzhalter-Ersetzung."""
    tpl_path = TEMPLATES_DIR / f"{template_name}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "user.md"
    content = tpl_path.read_text(encoding="utf-8")
    content = content.replace("{{DISPLAY_NAME}}", display_name)
    content = content.replace("{{USER_ID}}", user_id)
    content = content.replace("{{HA_USER}}", ha_user or user_id)
    return content


def _find_free_port(existing_ports: list[int]) -> int:
    """Nächsten freien Port ab 8001 finden."""
    port = 8001
    while port in existing_ports:
        port += 1
    return port


def _get_agent_image() -> str:
    """Agent-Image auto-detektieren (erstes HAANA-Image das läuft)."""
    if not _docker_client:
        return AGENT_IMAGE
    try:
        containers = _docker_client.containers.list(all=True)
        for c in containers:
            if "instanz-" in c.name or "haana-instanz" in c.name:
                return c.image.tags[0] if c.image.tags else AGENT_IMAGE
    except Exception:
        pass
    return AGENT_IMAGE


def _get_compose_network() -> str:
    """Docker-Netzwerk auto-detektieren."""
    if not _docker_client:
        return COMPOSE_NETWORK
    try:
        for net_name in [COMPOSE_NETWORK, "haana-default", "haana_default", "bridge"]:
            try:
                _docker_client.networks.get(net_name)
                return net_name
            except Exception:
                pass
    except Exception:
        pass
    return COMPOSE_NETWORK


def _container_status(container_name: str) -> str:
    """Container-Status abfragen."""
    if not _docker_client:
        return "unknown"
    try:
        c = _docker_client.containers.get(container_name)
        return c.status  # "running", "exited", "created", etc.
    except Exception:
        return "absent"


def _start_agent_container(user: dict, cfg: dict) -> dict:
    """Startet einen Agent-Container für einen User via Docker SDK."""
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar (kein Socket gemountet?)"}

    uid           = user["id"]
    display_name  = user.get("display_name", uid)
    api_port      = user["api_port"]
    container_name = user.get("container_name", f"haana-instanz-{uid}-1")
    template      = user.get("claude_md_template", "user")
    primary_slot  = user.get("primary_llm_slot", 1)
    extract_slot  = user.get("extraction_llm_slot", 3)
    write_scopes  = f"{uid}_memory,household_memory"
    read_scopes   = f"{uid}_memory,household_memory"

    # LLM-Slot-Infos aus Config
    slots = {s["slot"]: s for s in cfg.get("llm_providers", [])}
    pslot = slots.get(primary_slot, {})
    eslot = slots.get(extract_slot, {})

    env = {
        "HAANA_INSTANCE":         uid,
        "HAANA_API_PORT":         str(api_port),
        "HAANA_LOG_DIR":          "/data/logs",
        "HAANA_WRITE_SCOPES":     write_scopes,
        "HAANA_READ_SCOPES":      read_scopes,
        "HAANA_MODEL":            pslot.get("model", "claude-sonnet-4-6"),
        "HAANA_EXTRACT_MODEL":    eslot.get("model", ""),
        "QDRANT_URL":             cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333"),
        "OLLAMA_URL":             cfg.get("services", {}).get("ollama_url", ""),
        "HA_URL":                 cfg.get("services", {}).get("ha_url", ""),
        "HA_TOKEN":               cfg.get("services", {}).get("ha_token", ""),
    }

    # Anthropic API-Key oder Custom URL
    if pslot.get("key"):
        env["ANTHROPIC_API_KEY"] = pslot["key"]
    if pslot.get("url"):
        env["ANTHROPIC_BASE_URL"] = pslot["url"]
    if pslot.get("type") == "minimax" or (pslot.get("url", "") and "minimax" in pslot.get("url", "").lower()):
        env["ANTHROPIC_BASE_URL"]  = pslot.get("url", "https://api.minimax.io/anthropic")
        env["ANTHROPIC_AUTH_TOKEN"] = pslot.get("key", "")

    image = _get_agent_image()
    network = _get_compose_network()

    # Host-Pfad für CLAUDE.md
    host_claude_md = f"{HOST_BASE}/instanzen/{uid}/CLAUDE.md"
    host_skills    = f"{HOST_BASE}/skills"
    host_claude_config = "/root/.claude"

    volumes = {
        host_claude_md:     {"bind": "/app/CLAUDE.md",        "mode": "ro"},
        host_skills:        {"bind": "/app/skills",            "mode": "ro"},
        host_claude_config: {"bind": "/home/haana/.claude",   "mode": "ro"},
        DATA_VOLUME:        {"bind": "/data",                  "mode": "rw"},
    }

    try:
        # Eventuell alten Container entfernen
        try:
            old = _docker_client.containers.get(container_name)
            old.stop(timeout=5)
            old.remove()
        except Exception:
            pass

        container = _docker_client.containers.run(
            image,
            name=container_name,
            environment=env,
            volumes=volumes,
            ports={f"{api_port}/tcp": api_port},
            network=network,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
        )
        return {"ok": True, "container_id": container.short_id, "container_name": container_name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/users")
async def get_users():
    """User-Liste mit Container-Status."""
    cfg = load_config()
    users = cfg.get("users", [])
    result = []
    for u in users:
        status = _container_status(u.get("container_name", f"haana-instanz-{u['id']}-1"))
        result.append({**u, "container_status": status})
    return result


@app.post("/api/users")
async def create_user(request: Request):
    """
    Legt neuen User an:
    1. ID-Validierung
    2. Port vergeben
    3. CLAUDE.md aus Template generieren
    4. Container starten via Docker SDK
    5. User in config.json speichern
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    uid = (body.get("id") or "").strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,29}$", uid):
        raise HTTPException(400, "ID muss [a-z0-9-], max 30 Zeichen, nicht mit - beginnen")
    if uid in _SYSTEM_USER_IDS:
        raise HTTPException(409, f"'{uid}' ist eine reservierte System-ID")

    cfg = load_config()
    existing = [u["id"] for u in cfg.get("users", [])]
    if uid in existing:
        raise HTTPException(409, f"User '{uid}' existiert bereits")

    # Port vergeben
    used_ports = [u.get("api_port", 0) for u in cfg.get("users", [])]
    port = _find_free_port(used_ports)

    # User-Objekt aufbauen
    user: dict = {
        "id":                  uid,
        "display_name":        body.get("display_name") or uid.capitalize(),
        "role":                body.get("role", "user"),
        "primary_llm_slot":    int(body.get("primary_llm_slot", 1)),
        "extraction_llm_slot": int(body.get("extraction_llm_slot", 3)),
        "ha_user":             body.get("ha_user", uid),
        "whatsapp_jid":        body.get("whatsapp_jid", ""),
        "whatsapp_mode":       body.get("whatsapp_mode", "separate"),
        "api_port":            port,
        "container_name":      f"haana-instanz-{uid}-1",
        "claude_md_template":  body.get("claude_md_template", "admin" if body.get("role") == "admin" else "user"),
        "caldav_url": "", "caldav_user": "", "caldav_pass": "",
        "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }

    # CLAUDE.md generieren
    claude_md_dir = INST_DIR / uid
    claude_md_dir.mkdir(parents=True, exist_ok=True)
    claude_md_content = _render_claude_md(
        user["claude_md_template"], user["display_name"], uid, user["ha_user"]
    )
    (claude_md_dir / "CLAUDE.md").write_text(claude_md_content, encoding="utf-8")

    # Container starten
    result = _start_agent_container(user, cfg)

    # User in config speichern (auch wenn Container-Start fehlschlägt)
    cfg.setdefault("users", []).append(user)
    save_config(cfg)

    # Rebuild-State erweitern
    _rebuild[uid] = {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}

    return {"ok": True, "user": user, "container": result}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: str, request: Request):
    """User-Felder aktualisieren. Container wird neu gestartet wenn relevante Felder geändert."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    cfg = load_config()
    users = cfg.get("users", [])
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")

    restart_fields = {"primary_llm_slot", "extraction_llm_slot", "ha_user", "role", "claude_md_template"}
    needs_restart = any(k in body and body[k] != user.get(k) for k in restart_fields)

    user.update({k: v for k, v in body.items() if k not in ("id", "api_port", "container_name")})
    save_config(cfg)

    # CLAUDE.md neu generieren wenn Template oder Name geändert
    if "display_name" in body or "claude_md_template" in body or "ha_user" in body:
        claude_md_content = _render_claude_md(
            user["claude_md_template"], user["display_name"], user_id, user.get("ha_user", user_id)
        )
        (INST_DIR / user_id / "CLAUDE.md").write_text(claude_md_content, encoding="utf-8")

    container_result = None
    if needs_restart:
        container_result = _start_agent_container(user, cfg)

    return {"ok": True, "user": user, "restarted": needs_restart, "container": container_result}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str):
    """User löschen: Container stoppen + entfernen, CLAUDE.md-Dir löschen, config speichern."""
    cfg = load_config()
    users = cfg.get("users", [])
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    if user.get("system"):
        raise HTTPException(403, "System-Instanzen können nicht gelöscht werden")

    container_name = user.get("container_name", f"haana-instanz-{user_id}-1")

    # Container stoppen + entfernen
    container_removed = False
    if _docker_client:
        try:
            c = _docker_client.containers.get(container_name)
            c.stop(timeout=5)
            c.remove()
            container_removed = True
        except Exception:
            pass

    # CLAUDE.md-Verzeichnis löschen
    import shutil
    inst_path = INST_DIR / user_id
    if inst_path.exists():
        shutil.rmtree(inst_path, ignore_errors=True)

    # User aus config entfernen
    cfg["users"] = [u for u in users if u["id"] != user_id]
    save_config(cfg)

    _rebuild.pop(user_id, None)

    return {"ok": True, "container_removed": container_removed}


@app.post("/api/users/{user_id}/restart")
async def restart_user_container(user_id: str):
    """Container für einen User neu starten."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    result = _start_agent_container(user, cfg)
    return {"ok": result.get("ok", False), "container": result}


@app.post("/api/users/{user_id}/stop")
async def stop_user_container(user_id: str):
    """Container für einen User stoppen."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    container_name = user.get("container_name", f"haana-instanz-{user_id}-1")
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get(container_name)
        c.stop(timeout=5)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _get_agent_url(instance: str) -> str:
    """Agent-URL aus AGENT_URLS oder dynamisch aus config."""
    if instance in AGENT_URLS:
        return AGENT_URLS[instance]
    # Dynamischer User: URL aus api_port
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == instance), None)
    if user:
        return f"http://{user.get('container_name', f'haana-instanz-{instance}-1')}:{user['api_port']}"
    return ""


@app.get("/api/agent-health/{instance}")
async def agent_health(instance: str):
    """Prüft ob ein Agent-Container erreichbar ist."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    agent_url = _get_agent_url(instance)
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
    if instance not in get_all_instances():
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
