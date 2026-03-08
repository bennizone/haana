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
  GET  /api/whatsapp-status          → Bridge-Verbindungsstatus (Proxy)
  GET  /api/whatsapp-qr              → QR-Code als Base64 Data-URL (Proxy)
  POST /api/whatsapp-logout          → WhatsApp-Session trennen (Proxy)
"""

import asyncio
import http.client
import json
import os
import pty
import re
import select
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs
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

from core.process_manager import (
    detect_mode, create_agent_manager, AgentManager,
)

app = FastAPI(title="HAANA Admin", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
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


# ── Betriebsmodus ────────────────────────────────────────────────────────────
HAANA_MODE = detect_mode()
_agent_manager: Optional[AgentManager] = None

@app.on_event("startup")
async def startup_event():
    global _agent_manager
    asyncio.create_task(_cleanup_loop())
    _sync_rebuild_state()
    # AgentManager initialisieren (nach Config-Laden, damit _resolve_llm verfügbar ist)
    _agent_manager = create_agent_manager(
        HAANA_MODE,
        main_app=app,
        docker_client=_docker_client,
        resolve_llm_fn=_resolve_llm,
        find_ollama_url_fn=_find_ollama_url,
    )
    # Add-on Modus: Agents beim Start automatisch starten (kein Docker-SDK)
    if HAANA_MODE == "addon":
        asyncio.create_task(_autostart_agents())

async def _autostart_agents():
    """Startet alle konfigurierten User-Agents im Add-on-Modus."""
    import logging as _log
    _logger = _log.getLogger(__name__)
    cfg = load_config()
    for user in cfg.get("users", []):
        uid = user.get("id", "")
        if not uid:
            continue
        try:
            result = await _agent_manager.start_agent(user, cfg)
            if result.get("ok"):
                _logger.info(f"[Autostart] Agent '{uid}' gestartet")
            else:
                _logger.warning(f"[Autostart] Agent '{uid}': {result.get('error', 'unbekannt')}")
        except Exception as e:
            _logger.error(f"[Autostart] Agent '{uid}' fehlgeschlagen: {e}")

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
    "providers": [
        {"id": "anthropic-1", "name": "Anthropic (Primär)", "type": "anthropic", "auth_method": "api_key", "url": "", "key": ""},
        {"id": "ollama-home",  "name": "Ollama (Lokal)",     "type": "ollama",
         "url": os.environ.get("OLLAMA_URL", "http://10.83.1.110:11434"), "key": ""},
    ],
    "llms": [
        {"id": "claude-primary",  "name": "Claude Sonnet",   "provider_id": "anthropic-1", "model": "claude-sonnet-4-6"},
        {"id": "claude-fallback", "name": "Claude Haiku",    "provider_id": "anthropic-1", "model": "claude-haiku-4-5-20251001"},
        {"id": "ollama-extract",  "name": "Ministral Lokal", "provider_id": "ollama-home", "model": "ministral-3-32k:3b"},
    ],
    "memory": {
        "extraction_llm":          "ollama-extract",
        "extraction_llm_fallback": "",
        "context_enrichment":      False,
        "window_size":    int(os.environ.get("HAANA_WINDOW_SIZE",    "20")),
        "window_minutes": int(os.environ.get("HAANA_WINDOW_MINUTES", "60")),
        "min_messages":   5,
    },
    "embedding": {
        "provider_id":          "ollama-home",
        "model":                os.environ.get("HAANA_EMBEDDING_MODEL", "bge-m3"),
        "dims":                 int(os.environ.get("HAANA_EMBEDDING_DIMS", "1024")),
        "fallback_provider_id": "",
    },
    "log_retention": {
        "conversations": None,   # niemals löschen
        "llm-calls":     30,
        "tool-calls":    30,
        "memory-ops":    30,
    },
    "services": {
        "ha_url":        os.environ.get("HA_URL", ""),
        "ha_token":      "",
        "ha_mcp_enabled": False,
        "ha_mcp_type":   "extended",  # "builtin" = HA built-in (SSE), "extended" = ha-mcp add-on (HTTP)
        "ha_mcp_url":    "",   # leer = auto-detect je nach Typ
        "ha_mcp_token":  "",   # leer = ha_token verwenden
        "ha_auto_backup": False,  # HA-Backup vor Agent-Änderungen
        "qdrant_url":    os.environ.get("QDRANT_URL", "http://qdrant:6333"),
    },
    "users": [
        {
            "id": "alice", "display_name": "Alice", "role": "admin",
            "primary_llm": "claude-primary", "fallback_llm": "claude-fallback",
            "extraction_llm": "",
            "ha_user": "alice", "whatsapp_phone": "",
            "api_port": 8001, "container_name": "haana-instanz-alice-1",
            "claude_md_template": "admin",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "bob", "display_name": "Bob", "role": "user",
            "primary_llm": "claude-primary", "fallback_llm": "claude-fallback",
            "extraction_llm": "",
            "ha_user": "bob", "whatsapp_phone": "",
            "api_port": 8002, "container_name": "haana-instanz-bob-1",
            "claude_md_template": "user",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "ha-assist", "display_name": "HAANA Voice", "role": "voice",
            "system": True,
            "primary_llm": "ollama-extract", "fallback_llm": "",
            "extraction_llm": "",
            "ha_user": "", "whatsapp_phone": "",
            "api_port": 8003, "container_name": "haana-instanz-ha-assist-1",
            "claude_md_template": "ha-assist",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "ha-advanced", "display_name": "HAANA Advanced", "role": "voice-advanced",
            "system": True,
            "primary_llm": "claude-primary", "fallback_llm": "",
            "extraction_llm": "",
            "ha_user": "", "whatsapp_phone": "",
            "api_port": 8004, "container_name": "haana-instanz-ha-advanced-1",
            "claude_md_template": "ha-advanced",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
    ],
    "whatsapp": {
        "mode": "separate",
        "self_prefix": "!h ",
    },
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


def _slugify(text: str) -> str:
    """Einfacher Slug: Kleinbuchstaben, Umlaute ersetzen, nur [a-z0-9-]."""
    text = text.lower().strip()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


def _migrate_config(cfg: dict) -> bool:
    """Migriert alte llm_providers[]-Struktur zu providers[] + llms[].

    Returns True wenn Migration durchgeführt wurde.
    """
    if "providers" in cfg or "llm_providers" not in cfg:
        return False

    old_slots = cfg.pop("llm_providers", [])
    cfg.pop("use_cases", None)

    # Provider deduplizieren nach (type, url, key)
    seen_providers: dict[tuple, str] = {}
    providers: list[dict] = []
    llms: list[dict] = []
    slot_to_llm_id: dict[int, str] = {}

    for slot in old_slots:
        pkey = (slot.get("type", "custom"), slot.get("url", ""), slot.get("key", ""))
        if pkey not in seen_providers:
            ptype = slot.get("type", "custom")
            pid = f"{ptype}-{len(providers) + 1}"
            providers.append({
                "id": pid,
                "name": slot.get("name", pid),
                "type": ptype,
                "url": slot.get("url", ""),
                "key": slot.get("key", ""),
            })
            seen_providers[pkey] = pid

        provider_id = seen_providers[pkey]
        lid = _slugify(slot.get("name", f"llm-{slot.get('slot', len(llms) + 1)}"))
        # Eindeutigkeit sicherstellen
        base_lid = lid
        counter = 2
        existing_ids = {l["id"] for l in llms}
        while lid in existing_ids:
            lid = f"{base_lid}-{counter}"
            counter += 1

        llms.append({
            "id": lid,
            "name": slot.get("name", f"LLM {slot.get('slot', '')}"),
            "provider_id": provider_id,
            "model": slot.get("model", ""),
        })
        slot_to_llm_id[slot.get("slot", len(llms))] = lid

    cfg["providers"] = providers
    cfg["llms"] = llms

    # User-Felder migrieren
    for user in cfg.get("users", []):
        if "primary_llm_slot" in user:
            old_slot = user.pop("primary_llm_slot")
            user["primary_llm"] = slot_to_llm_id.get(old_slot, llms[0]["id"] if llms else "")
        if "extraction_llm_slot" in user:
            old_slot = user.pop("extraction_llm_slot")
            user["extraction_llm"] = slot_to_llm_id.get(old_slot, "")
        user.setdefault("fallback_llm", "")

    # Embedding migrieren: provider → provider_id
    emb = cfg.get("embedding", {})
    if "provider" in emb and "provider_id" not in emb:
        old_prov_type = emb.pop("provider")
        matching = next((p for p in providers if p["type"] == old_prov_type), None)
        emb["provider_id"] = matching["id"] if matching else ""
        emb.setdefault("fallback_provider_id", "")

    # Memory: extraction_llm global setzen
    mem = cfg.setdefault("memory", {})
    if "extraction_llm" not in mem:
        # Ollama-basiertes LLM als Default-Extraction
        ollama_llm = next(
            (l for l in llms if any(
                p["type"] == "ollama" and p["id"] == l["provider_id"] for p in providers
            )),
            None,
        )
        mem["extraction_llm"] = ollama_llm["id"] if ollama_llm else ""
        mem["extraction_llm_fallback"] = ""

    return True


def _migrate_providers_v2(cfg: dict) -> bool:
    """Migriert Provider v2: auth_method für Anthropic, ollama_url entfernen.

    Returns True wenn Migration durchgeführt wurde.
    """
    changed = False

    # Anthropic-Provider: auth_method hinzufügen
    for p in cfg.get("providers", []):
        if p.get("type") == "anthropic" and "auth_method" not in p:
            p["auth_method"] = "oauth" if not p.get("key") else "api_key"
            changed = True

    # services.ollama_url entfernen, Wert in Ollama-Providern sicherstellen
    services = cfg.get("services", {})
    old_ollama_url = services.pop("ollama_url", None)
    if old_ollama_url is not None:
        changed = True
        # Sicherstellen dass mindestens ein Ollama-Provider die URL hat
        for p in cfg.get("providers", []):
            if p.get("type") == "ollama" and not p.get("url"):
                p["url"] = old_ollama_url

    # OAuth credentials migration: bestehende /claude-auth/.credentials.json
    # in den passenden Provider-Ordner verschieben
    for p in cfg.get("providers", []):
        if p.get("type") == "anthropic" and p.get("auth_method") == "oauth" and "oauth_dir" not in p:
            p["oauth_dir"] = f"/data/claude-auth/{p['id']}"
            changed = True

    return changed


def _resolve_llm(llm_id: str, cfg: dict) -> tuple[dict, dict]:
    """Löst eine LLM-ID zu (llm_dict, provider_dict) auf. Gibt ({}, {}) zurück wenn nicht gefunden."""
    llm = next((l for l in cfg.get("llms", []) if l["id"] == llm_id), {})
    if not llm:
        return {}, {}
    provider = next((p for p in cfg.get("providers", []) if p["id"] == llm.get("provider_id")), {})
    return llm, provider


def _find_ollama_url(cfg: dict) -> str:
    """Findet die Ollama-URL aus Providern: Embedding → Extraction → erster Ollama."""
    emb = cfg.get("embedding", {})
    emb_prov = next((p for p in cfg.get("providers", []) if p["id"] == emb.get("provider_id")), {})
    if emb_prov.get("type") == "ollama" and emb_prov.get("url"):
        return emb_prov["url"]

    # Extraction-Provider
    mem = cfg.get("memory", {})
    e_llm_id = mem.get("extraction_llm", "")
    if e_llm_id:
        e_llm, e_prov = _resolve_llm(e_llm_id, cfg)
        if e_prov.get("type") == "ollama" and e_prov.get("url"):
            return e_prov["url"]

    # Erster Ollama-Provider
    for p in cfg.get("providers", []):
        if p.get("type") == "ollama" and p.get("url"):
            return p["url"]

    return ""


def _find_references(entity_type: str, entity_id: str, cfg: dict) -> list[str]:
    """Findet alle Referenzen auf eine Entity (provider oder llm).

    Returns Liste von Strings wie "User alice (Primary)", "LLM claude-primary", etc.
    """
    refs: list[str] = []

    if entity_type == "provider":
        # Welche LLMs referenzieren diesen Provider?
        for llm in cfg.get("llms", []):
            if llm.get("provider_id") == entity_id:
                refs.append(f"LLM: {llm.get('name', llm['id'])}")
        # Embedding
        emb = cfg.get("embedding", {})
        if emb.get("provider_id") == entity_id:
            refs.append("Embedding (Primary)")
        if emb.get("fallback_provider_id") == entity_id:
            refs.append("Embedding (Fallback)")

    elif entity_type == "llm":
        # Welche User referenzieren dieses LLM?
        for user in cfg.get("users", []):
            uid = user.get("id", "?")
            if user.get("primary_llm") == entity_id:
                refs.append(f"User {uid} (Primary)")
            if user.get("fallback_llm") == entity_id:
                refs.append(f"User {uid} (Fallback)")
            if user.get("extraction_llm") == entity_id:
                refs.append(f"User {uid} (Extraction)")
        # Memory global
        mem = cfg.get("memory", {})
        if mem.get("extraction_llm") == entity_id:
            refs.append("Memory Extraction (Global)")
        if mem.get("extraction_llm_fallback") == entity_id:
            refs.append("Memory Extraction Fallback (Global)")

    return refs


def load_config() -> dict:
    if CONF_FILE.exists():
        try:
            cfg = json.loads(CONF_FILE.read_text(encoding="utf-8"))
            # Embeddings-Use-Case entfernen (wurde in separate Sektion ausgelagert)
            cfg.get("use_cases", {}).pop("embeddings", None)
            # Migration von alter Struktur
            if _migrate_config(cfg):
                save_config(cfg)
            if _migrate_providers_v2(cfg):
                save_config(cfg)
            _ensure_system_users(cfg)
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    cfg["providers"] = list(DEFAULT_CONFIG["providers"])
    cfg["llms"] = list(DEFAULT_CONFIG["llms"])
    cfg["users"] = list(DEFAULT_CONFIG["users"])
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


@app.get("/api/references/{entity_type}/{entity_id}")
async def get_references(entity_type: str, entity_id: str):
    """Gibt alle Referenzen auf eine Entity (provider/llm) zurück."""
    if entity_type not in ("provider", "llm"):
        raise HTTPException(400, "entity_type muss 'provider' oder 'llm' sein")
    cfg = load_config()
    refs = _find_references(entity_type, entity_id, cfg)
    return {"refs": refs, "count": len(refs)}


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


@app.get("/api/claude-md-template/{template_name}")
async def get_claude_md_template(template_name: str):
    """Liefert den Rohinhalt eines CLAUDE.md-Templates (ohne Platzhalter-Ersatz)."""
    safe = re.sub(r"[^a-z0-9\-]", "", template_name.lower())
    tpl_path = TEMPLATES_DIR / f"{safe}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "user.md"
    if not tpl_path.exists():
        raise HTTPException(404, "Template nicht gefunden")
    return {"content": tpl_path.read_text(encoding="utf-8"), "template": safe}


# ── API: Status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    ollama_url = _find_ollama_url(cfg)

    status: dict = {"qdrant": "unknown", "ollama": "unknown", "logs": {}}

    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{qdrant_url}/collections")
            colls = r.json().get("result", {}).get("collections", [])
            coll_names = [c["name"] for c in colls]
            # Prüfe ob Collections leer sind (für Rebuild-Empfehlung)
            total_vectors = 0
            configured_dims = cfg.get("embedding", {}).get("dims", 1024)
            dims_mismatch = False
            for cname in coll_names:
                try:
                    cr = await client.get(f"{qdrant_url}/collections/{cname}")
                    res = cr.json().get("result", {})
                    total_vectors += res.get("points_count", 0) or res.get("vectors_count", 0) or 0
                    # Dimensions-Check: Collection-Dimension vs. konfigurierte
                    coll_dim = (res.get("config", {}).get("params", {})
                                .get("vectors", {}).get("size", 0))
                    if coll_dim and coll_dim != configured_dims:
                        dims_mismatch = True
                except Exception:
                    pass
            # Konversations-Logs vorhanden?
            conv_files = _glob.glob(str(LOG_ROOT / "conversations" / "**" / "*.jsonl"), recursive=True)
            has_logs = len(conv_files) > 0
            status["qdrant"] = {
                "ok": True,
                "collections": coll_names,
                "rebuild_suggested": has_logs and total_vectors == 0,
                "dims_mismatch": dims_mismatch,
                "configured_dims": configured_dims,
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
                    _cr = cr.json().get("result", {})
                    coll_vectors[c["name"]] = _cr.get("points_count", 0) or _cr.get("vectors_count", 0) or 0
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

@app.post("/api/instances/{instance}/restart")
async def restart_instance(instance: str):
    """Agent-Instanz neu starten."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    return await _agent_manager.restart_agent(instance)


@app.post("/api/instances/{instance}/stop")
async def stop_instance(instance: str):
    """Agent-Instanz graceful stoppen."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    return await _agent_manager.stop_agent(instance)


@app.post("/api/instances/{instance}/force-stop")
async def force_stop_instance(instance: str):
    """Agent-Instanz sofort beenden (laufende Memory-Extraktion geht verloren)."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    return await _agent_manager.stop_agent(instance, force=True)


@app.post("/api/instances/restart-all")
async def restart_all_instances():
    """Alle Agent-Instanzen mit aktueller Config neu starten."""
    cfg = load_config()
    results = {}

    # Dynamische User-Agents
    for user in cfg.get("users", []):
        uid = user["id"]
        result = await _agent_manager.start_agent(user, cfg)
        results[uid] = result

    # Statische Instanzen (ohne User-Config)
    for inst in INSTANCES:
        if inst not in results:
            result = await _agent_manager.restart_agent(inst)
            results[inst] = result

    all_ok = all(r.get("ok", False) for r in results.values())
    return {"ok": all_ok, "results": results}


@app.post("/api/qdrant/restart")
async def restart_qdrant():
    """Qdrant-Container neu starten (nur im Standalone-Modus)."""
    if not _docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = _docker_client.containers.get("haana-qdrant-1")
        c.restart(timeout=10)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.delete("/api/qdrant/collections/{name}")
async def delete_qdrant_collection(name: str):
    """Löscht eine Qdrant-Collection."""
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{qdrant_url}/collections/{name}")
            return r.json()
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


@app.post("/api/test-ha")
async def test_ha(request: Request):
    """Testet Home Assistant URL + Long-Lived Token."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    ha_url   = (body.get("ha_url")   or "").rstrip("/")
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


@app.post("/api/test-ha-mcp")
async def test_ha_mcp(request: Request):
    """Testet den HA MCP Server SSE-Endpunkt."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    mcp_url = (body.get("mcp_url") or "").strip()
    token   = (body.get("token")   or "").strip()

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
                # Built-in HA MCP: SSE (GET), Bearer auth
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
                            return {"ok": True, "detail": "MCP Server erreichbar ✓ (SSE)"}
                        return {"ok": True, "detail": f"Erreichbar · HTTP {sc} · {ct or 'kein Content-Type'}"}
                    return {"ok": sc < 400, "detail": f"HTTP {sc}"}
            else:
                # Extended ha-mcp: Streamable HTTP (POST), MCP initialize
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
                    return {"ok": True, "detail": f"MCP Server erreichbar ✓ (HTTP, Status {sc})"}
                # SSE-formatted response (ha-mcp returns SSE even over POST)
                ct = r.headers.get("content-type", "")
                if "event-stream" in ct:
                    return {"ok": True, "detail": "MCP Server erreichbar ✓ (SSE-over-HTTP)"}
                return {"ok": sc < 400, "detail": f"HTTP {sc}"}
    except httpx.ConnectError:
        return {"ok": False, "detail": "Verbindung abgelehnt – HA erreichbar?"}
    except httpx.ReadTimeout:
        return {"ok": True, "detail": "MCP Server erreichbar ✓ (Timeout nach Connect – normal bei SSE)"}
    except httpx.TimeoutException:
        return {"ok": False, "detail": "Connect-Timeout – HA erreichbar?"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@app.get("/api/ha-stt-tts")
async def ha_stt_tts():
    """Listet verfügbare STT- und TTS-Entitäten aus Home Assistant auf."""
    cfg = load_config()
    ha_url   = cfg.get("services", {}).get("ha_url",   "").rstrip("/")
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


@app.get("/api/ha-users")
async def ha_users():
    """Listet Home Assistant Person-Entitäten für User-Mapping auf."""
    cfg = load_config()
    ha_url   = cfg.get("services", {}).get("ha_url",   "").rstrip("/")
    ha_token = cfg.get("services", {}).get("ha_token", "").strip()
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
                    uid  = eid[len("person."):]
                    name = state.get("attributes", {}).get("friendly_name", uid)
                    persons.append({"id": uid, "display_name": name})
            return {"ok": True, "users": persons}
    except httpx.ConnectError:
        return {"ok": False, "error": "HA nicht erreichbar", "users": []}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "users": []}


@app.get("/api/whatsapp-config")
async def whatsapp_config_endpoint():
    """Liefert WhatsApp-Routing-Konfiguration für die Bridge.
    Pro User wird sowohl die Phone-JID als auch eine optionale LID als Route geliefert,
    da neuere WhatsApp-Versionen LID statt Phone-JID senden."""
    cfg = load_config()
    wa  = cfg.get("whatsapp", {"mode": "separate", "self_prefix": "!h "})
    routes = []
    for user in cfg.get("users", []):
        phone = user.get("whatsapp_phone", "").strip()
        if not phone or user.get("system"):
            continue
        jid = phone if "@" in phone else f"{phone}@s.whatsapp.net"
        uid = user["id"]
        if HAANA_MODE == "addon":
            # Add-on: Agents laufen als Sub-App im selben Prozess
            agent_url = f"http://localhost:8080/agent/{uid}"
        else:
            container = user.get("container_name", f"haana-instanz-{uid}-1")
            port      = user.get("api_port", 8001)
            agent_url = f"http://{container}:{port}"
        target = {"agent_url": agent_url, "user_id": uid}
        routes.append({"jid": jid, **target})
        # Optionale LID als zweite Route registrieren
        lid = user.get("whatsapp_lid", "").strip()
        if lid:
            lid_jid = lid if "@" in lid else f"{lid}@lid"
            routes.append({"jid": lid_jid, **target})
    # STT/TTS-Konfiguration aus services-Sektion für die Bridge bereitstellen
    services = cfg.get("services", {})
    stt = None
    tts = None
    ha_url   = services.get("ha_url", "").strip()
    ha_token = services.get("ha_token", "").strip()
    if ha_url and ha_token:
        stt_entity = services.get("stt_entity", "").strip()
        tts_entity = services.get("tts_entity", "").strip()
        if stt_entity:
            stt = {
                "ha_url":       ha_url,
                "ha_token":     ha_token,
                "stt_entity":   stt_entity,
                "stt_language": services.get("stt_language", "de-DE"),
            }
        if tts_entity:
            tts = {
                "ha_url":       ha_url,
                "ha_token":     ha_token,
                "tts_entity":   tts_entity,
                "tts_language": services.get("stt_language", "de-DE"),
                "tts_voice":    services.get("tts_voice", ""),
                "tts_also_text": services.get("tts_also_text", False),
            }

    return {"mode": wa.get("mode", "separate"), "self_prefix": wa.get("self_prefix", "!h "), "routes": routes, "stt": stt, "tts": tts}


# ── WhatsApp Bridge Proxy (Status / QR / Logout) ──────────────────────────────

_WA_BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://whatsapp-bridge:3001")


@app.get("/api/whatsapp-status")
async def whatsapp_status():
    """Proxy: Bridge-Verbindungsstatus abfragen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{_WA_BRIDGE_URL}/status")
            return r.json()
    except httpx.ConnectError:
        return {"status": "offline", "error": "Bridge nicht erreichbar"}
    except Exception as e:
        return {"status": "offline", "error": str(e)[:200]}


@app.get("/api/whatsapp-qr")
async def whatsapp_qr():
    """Proxy: aktuellen QR-Code als Base64 Data-URL abrufen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{_WA_BRIDGE_URL}/qr")
            return r.json()
    except httpx.ConnectError:
        return {"error": "Bridge nicht erreichbar", "status": "offline"}
    except Exception as e:
        return {"error": str(e)[:200], "status": "offline"}


@app.post("/api/whatsapp-logout")
async def whatsapp_logout():
    """Proxy: WhatsApp-Session trennen."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{_WA_BRIDGE_URL}/logout")
            return r.json()
    except httpx.ConnectError:
        return {"ok": False, "error": "Bridge nicht erreichbar"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


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

    # Agent-Erreichbarkeit prüfen vor Start
    agent_url = _get_agent_url(instance)
    import httpx as _httpx_pre
    try:
        async with _httpx_pre.AsyncClient(timeout=5.0) as _c:
            _r = await _c.get(f"{agent_url}/health")
            if not _r.is_success:
                return {"ok": False, "error": f"Agent '{instance}' antwortet nicht (Health-Check fehlgeschlagen). Container läuft?"}
    except Exception as _e:
        return {"ok": False, "error": f"Agent '{instance}' nicht erreichbar: {str(_e)[:120]}. Container läuft?"}

    _rebuild[instance] = {
        "status": "running", "done": 0, "total": total, "errors": 0,
        "started": time.time(), "error": "",
    }

    async def _run():
        state = _rebuild[instance]
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
                            r = await client.post(
                                f"{agent_url}/rebuild-entry",
                                json={
                                    "user":      rec.get("user", ""),
                                    "assistant": rec.get("assistant", ""),
                                },
                            )
                            if not r.is_success:
                                state["errors"] += 1
                        except Exception:
                            state["errors"] += 1
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
            yield f"data: {json.dumps({'done': done, 'total': total, 'status': status, 'eta_s': eta_s, 'error': state.get('error',''), 'errors': state.get('errors', 0)})}\n\n"
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

            elif type_ == "openai":
                target = url or "https://api.openai.com"
                headers = {"Authorization": f"Bearer {key}"}
                r = await client.get(f"{target}/v1/models", headers=headers)
                if r.status_code == 200:
                    models = sorted([m["id"] for m in r.json().get("data", [])])
                    return {"models": models}
                return {"models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"], "fallback": True}

            elif type_ == "gemini":
                return {"models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash"], "fallback": True}

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


@app.get("/api/users")
async def get_users():
    """User-Liste mit Agent-Status."""
    cfg = load_config()
    users = cfg.get("users", [])
    result = []
    for u in users:
        status = _agent_manager.agent_status(u["id"])
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

    # Default-LLMs aus Config
    default_primary = cfg.get("llms", [{}])[0].get("id", "") if cfg.get("llms") else ""

    # User-Objekt aufbauen
    user: dict = {
        "id":                  uid,
        "display_name":        body.get("display_name") or uid.capitalize(),
        "role":                body.get("role", "user"),
        "primary_llm":         body.get("primary_llm", default_primary),
        "fallback_llm":        body.get("fallback_llm", ""),
        "extraction_llm":      body.get("extraction_llm", ""),
        "ha_user":             body.get("ha_user", uid),
        "whatsapp_phone":      body.get("whatsapp_phone", ""),
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

    # Agent starten
    result = await _agent_manager.start_agent(user, cfg)

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

    restart_fields = {"primary_llm", "fallback_llm", "extraction_llm", "ha_user", "role", "claude_md_template"}
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
        container_result = await _agent_manager.start_agent(user, cfg)

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

    # Agent stoppen + entfernen
    remove_result = await _agent_manager.remove_agent(user_id)
    container_removed = remove_result.get("ok", False)

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
    """Agent für einen User neu starten."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    result = await _agent_manager.start_agent(user, cfg)
    return {"ok": result.get("ok", False), "container": result}


@app.post("/api/users/{user_id}/stop")
async def stop_user_container(user_id: str):
    """Agent für einen User stoppen."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    return await _agent_manager.stop_agent(user_id)


def _get_agent_url(instance: str) -> str:
    """Agent-URL: AgentManager oder Fallback aus AGENT_URLS/Config."""
    if _agent_manager:
        url = _agent_manager.agent_url(instance)
        if url:
            return url
    # Fallback für statische Instanzen
    if instance in AGENT_URLS:
        return AGENT_URLS[instance]
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


# ── Claude Auth Management ────────────────────────────────────────────────────

CLAUDE_AUTH_DIR = Path("/claude-auth")       # gemountet via docker-compose
CLAUDE_AUTH_HOST = Path("/root/.claude")     # Host-Pfad (für Referenz)

@app.get("/api/claude-auth/status")
async def claude_auth_status():
    """Prüft ob gültige Claude OAuth-Credentials vorliegen."""
    creds_file = CLAUDE_AUTH_DIR / ".credentials.json"
    if not creds_file.exists():
        return {"ok": False, "status": "no_credentials", "detail": "Keine Credentials gefunden"}
    try:
        creds = json.loads(creds_file.read_text(encoding="utf-8"))
        oauth = creds.get("claudeAiOauth", {})
        if not oauth.get("accessToken"):
            return {"ok": False, "status": "no_token", "detail": "Kein Access-Token"}
        expires_at = oauth.get("expiresAt", 0) / 1000
        now = time.time()
        if now > expires_at:
            hours_ago = (now - expires_at) / 3600
            return {"ok": False, "status": "expired", "detail": f"Token abgelaufen (vor {hours_ago:.1f}h)"}
        hours_left = (expires_at - now) / 3600
        return {"ok": True, "status": "valid", "detail": f"Token gültig (noch {hours_left:.1f}h)",
                "expires_in_hours": round(hours_left, 1)}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)[:200]}


@app.post("/api/claude-auth/refresh")
async def claude_auth_refresh():
    """Versucht den OAuth-Token per Refresh-Token zu erneuern.
    Nutzt einen laufenden Agent-Container um den CLI-Befehl auszuführen."""
    if not _docker_client:
        return {"ok": False, "detail": "Docker nicht verfügbar"}

    # Finde einen laufenden Agent-Container
    try:
        containers = _docker_client.containers.list(
            filters={"status": "running", "name": "haana-instanz"})
        if not containers:
            return {"ok": False, "detail": "Kein laufender Agent-Container gefunden"}
        container = containers[0]

        # auth status prüfen
        result = container.exec_run(
            cmd=["/usr/local/lib/python3.13/site-packages/claude_agent_sdk/_bundled/claude",
                 "auth", "status"],
            user="haana", environment={"HOME": "/home/haana"})
        status_out = result.output.decode("utf-8", errors="replace").strip()

        try:
            status_data = json.loads(status_out.split("\n")[0])
        except Exception:
            status_data = {}

        if status_data.get("loggedIn"):
            return {"ok": True, "detail": "Bereits eingeloggt", "status": status_data}

        # Token ist abgelaufen - Credentials-Datei neu von laufender Session kopieren
        # Falls eine Claude Code Session auf dem Host läuft, hat sie den Token refreshed
        return {"ok": False, "detail": "Token abgelaufen. Bitte manuell erneuern (siehe Anleitung).",
                "status": status_data}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@app.post("/api/claude-auth/upload")
async def claude_auth_upload(request: Request):
    """Credentials-Datei hochladen (JSON mit claudeAiOauth)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    creds = body.get("credentials")
    if not creds or not isinstance(creds, dict):
        raise HTTPException(400, "Feld 'credentials' fehlt oder ungültig")

    # Validierung: muss claudeAiOauth mit accessToken enthalten
    oauth = creds.get("claudeAiOauth", {})
    if not oauth.get("accessToken") or not oauth.get("refreshToken"):
        raise HTTPException(400, "Credentials müssen claudeAiOauth mit accessToken und refreshToken enthalten")

    creds_file = CLAUDE_AUTH_DIR / ".credentials.json"
    try:
        CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
        creds_file.write_text(json.dumps(creds, indent=2), encoding="utf-8")
        # Permissions für Container-User
        os.chmod(creds_file, 0o600)
        import subprocess
        subprocess.run(["chown", "1000:1000", str(creds_file)], check=False)
        return {"ok": True, "detail": "Credentials gespeichert. Container müssen neu gestartet werden."}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


# ── Claude OAuth Login Flow ──────────────────────────────────────────────────

# Stores active login session: {pid, fd, port, state, url}
_oauth_login_session: dict | None = None


def _cleanup_oauth_session():
    """Kill any running oauth login process."""
    global _oauth_login_session
    if _oauth_login_session:
        try:
            os.kill(_oauth_login_session["pid"], signal.SIGKILL)
            os.waitpid(_oauth_login_session["pid"], os.WNOHANG)
        except (ProcessLookupError, ChildProcessError):
            pass
        try:
            os.close(_oauth_login_session["fd"])
        except OSError:
            pass
        _oauth_login_session = None


def _start_oauth_login_sync():
    """Blocking: spawn claude auth login, extract URL and callback port."""
    global _oauth_login_session

    _cleanup_oauth_session()

    tmp_home = "/tmp/claude-oauth-login"
    os.makedirs(f"{tmp_home}/.claude", exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = tmp_home

    pid, fd = pty.fork()
    if pid == 0:
        for k, v in env.items():
            os.environ[k] = v
        os.execvp("claude", ["claude", "auth", "login"])
        os._exit(1)

    # Read output until we get the URL
    output = b""
    end_time = time.time() + 10
    while time.time() < end_time:
        r, _, _ = select.select([fd], [], [], 1)
        if r:
            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                output += data
            except OSError:
                break

    text = output.decode("utf-8", errors="replace")

    url_match = re.search(r"(https://claude\.ai/oauth/authorize\S+)", text)
    if not url_match:
        _cleanup_oauth_session()
        return {"ok": False, "detail": "Could not extract OAuth URL from claude auth login"}

    auth_url = url_match.group(1)
    parsed = urlparse(auth_url)
    qs = parse_qs(parsed.query)
    state_val = qs.get("state", [""])[0]

    # Find the local callback port via /proc/net/tcp{,6}
    port = None
    time.sleep(1)  # give claude time to open the port
    try:
        child_inodes = set()
        for fd_entry in Path(f"/proc/{pid}/fd").iterdir():
            try:
                target = os.readlink(str(fd_entry))
                if target.startswith("socket:["):
                    child_inodes.add(target.split("[")[1].rstrip("]"))
            except (OSError, IndexError):
                continue

        localhost_v4 = {"0100007F", "0B00007F"}
        localhost_v6 = {"00000000000000000000000001000000"}
        is_ipv6 = False
        for tcp_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
            try:
                with open(tcp_file) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) < 10 or parts[3] != "0A":
                            continue
                        addr_hex, port_hex = parts[1].rsplit(":", 1)
                        if parts[9] in child_inodes and (
                            addr_hex in localhost_v4 or addr_hex in localhost_v6
                        ):
                            port = int(port_hex, 16)
                            is_ipv6 = addr_hex in localhost_v6
                            break
            except FileNotFoundError:
                continue
            if port:
                break
    except Exception:
        pass

    if not port:
        _cleanup_oauth_session()
        return {"ok": False, "detail": "Could not find local callback port"}

    callback_host = "::1" if is_ipv6 else "127.0.0.1"
    _oauth_login_session = {
        "pid": pid, "fd": fd, "port": port, "host": callback_host,
        "state": state_val, "url": auth_url, "tmp_home": tmp_home,
    }
    return {"ok": True, "url": auth_url, "state": state_val}


@app.post("/api/claude-auth/login/start")
async def claude_auth_login_start():
    """Start OAuth login: spawns 'claude auth login', returns the auth URL."""
    return await asyncio.to_thread(_start_oauth_login_sync)


def _complete_oauth_login_sync(code: str):
    """Blocking: send authorization code to the local callback server."""
    global _oauth_login_session

    if not _oauth_login_session:
        return {"ok": False, "detail": "No active login session. Start login first."}

    port = _oauth_login_session["port"]
    state_val = _oauth_login_session["state"]
    fd = _oauth_login_session["fd"]
    tmp_home = _oauth_login_session["tmp_home"]
    callback_host = _oauth_login_session["host"]

    # Send code to the local callback server
    try:
        conn = http.client.HTTPConnection(callback_host, port, timeout=10)
        from urllib.parse import quote
        conn.request("GET", f"/callback?code={quote(code, safe='')}&state={quote(state_val, safe='')}")
        resp = conn.getresponse()
        resp.read()
        conn.close()
    except Exception as e:
        _cleanup_oauth_session()
        return {"ok": False, "detail": f"Callback failed: {e}"}

    # Wait for process to finish and read remaining output
    time.sleep(2)
    pty_text = ""
    try:
        r, _, _ = select.select([fd], [], [], 3)
        if r:
            pty_text = os.read(fd, 8192).decode("utf-8", errors="replace")
    except OSError:
        pass

    success = "Login failed" not in pty_text and resp.status < 400

    if success:
        tmp_creds = Path(tmp_home) / ".claude" / ".credentials.json"
        if tmp_creds.is_file():
            try:
                creds_data = tmp_creds.read_text(encoding="utf-8")
                CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
                dest = CLAUDE_AUTH_DIR / ".credentials.json"
                dest.write_text(creds_data, encoding="utf-8")
                os.chmod(dest, 0o600)
                import subprocess
                subprocess.run(["chown", "1000:1000", str(dest)], check=False)
            except Exception as e:
                _cleanup_oauth_session()
                return {"ok": False, "detail": f"Login succeeded but credential copy failed: {e}"}

    _cleanup_oauth_session()

    if success:
        return {"ok": True, "detail": "Login successful. Credentials saved."}
    # Strip ANSI escape codes from error output
    clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", pty_text).strip()
    return {"ok": False, "detail": f"Login failed. {clean[:200]}"}


@app.post("/api/claude-auth/login/complete")
async def claude_auth_login_complete(request: Request):
    """Complete OAuth login: send the authorization code to the local callback."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return {"ok": False, "detail": "Authorization code missing"}
    return await asyncio.to_thread(_complete_oauth_login_sync, code)


# ── Provider-scoped OAuth Endpoints ──────────────────────────────────────────

@app.get("/api/claude-auth/status/{provider_id}")
async def claude_auth_status_provider(provider_id: str):
    """Prüft ob gültige Claude OAuth-Credentials für einen Provider vorliegen."""
    cfg = load_config()
    prov = next((p for p in cfg.get("providers", []) if p["id"] == provider_id), None)
    if not prov:
        raise HTTPException(404, "Provider nicht gefunden")
    oauth_dir = Path(prov.get("oauth_dir", f"/data/claude-auth/{provider_id}"))
    creds_file = oauth_dir / ".credentials.json"
    if not creds_file.exists():
        return {"ok": False, "status": "no_credentials", "detail": "Keine Credentials gefunden"}
    try:
        creds = json.loads(creds_file.read_text(encoding="utf-8"))
        oauth = creds.get("claudeAiOauth", {})
        if not oauth.get("accessToken"):
            return {"ok": False, "status": "no_token", "detail": "Kein Access-Token"}
        expires_at = oauth.get("expiresAt", 0) / 1000
        now = time.time()
        if now > expires_at:
            hours_ago = (now - expires_at) / 3600
            return {"ok": False, "status": "expired", "detail": f"Token abgelaufen (vor {hours_ago:.1f}h)"}
        hours_left = (expires_at - now) / 3600
        return {"ok": True, "status": "valid", "detail": f"Token gültig (noch {hours_left:.1f}h)",
                "expires_in_hours": round(hours_left, 1)}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)[:200]}


@app.post("/api/claude-auth/login/start/{provider_id}")
async def claude_auth_login_start_provider(provider_id: str):
    """Start OAuth login for a specific provider."""
    return await asyncio.to_thread(_start_oauth_login_sync)


@app.post("/api/claude-auth/login/complete/{provider_id}")
async def claude_auth_login_complete_provider(provider_id: str, request: Request):
    """Complete OAuth login for a specific provider: send the authorization code."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return {"ok": False, "detail": "Authorization code missing"}

    result = await asyncio.to_thread(_complete_oauth_login_sync, code)

    # Copy credentials to provider-specific directory (auch bei Fehler versuchen,
    # da der erste complete-Aufruf funktioniert haben könnte)
    cfg = load_config()
    prov = next((p for p in cfg.get("providers", []) if p["id"] == provider_id), None)
    if prov:
        oauth_dir = Path(prov.get("oauth_dir", f"/data/claude-auth/{provider_id}"))
        global_creds = CLAUDE_AUTH_DIR / ".credentials.json"
        if global_creds.exists():
            try:
                import shutil
                oauth_dir.mkdir(parents=True, exist_ok=True)
                dest = oauth_dir / ".credentials.json"
                shutil.copy2(str(global_creds), str(dest))
                os.chmod(dest, 0o600)
                import subprocess
                subprocess.run(["chown", "1000:1000", str(dest)], check=False)
                logger.info(f"OAuth credentials kopiert: {global_creds} → {dest}")
                # Wenn Kopie geklappt hat aber Login fehlschlug (Doppelklick),
                # trotzdem als Erfolg melden wenn Credentials gültig sind
                if not result.get("ok"):
                    creds = json.loads(dest.read_text(encoding="utf-8"))
                    if creds.get("claudeAiOauth", {}).get("accessToken"):
                        result = {"ok": True, "detail": "Login successful. Credentials saved."}
            except Exception as e:
                logger.error(f"OAuth credential copy failed: {e}")

    return result


@app.post("/api/claude-auth/upload/{provider_id}")
async def claude_auth_upload_provider(provider_id: str, request: Request):
    """Upload credentials for a specific provider."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    creds = body.get("credentials")
    if not creds or not isinstance(creds, dict):
        raise HTTPException(400, "Feld 'credentials' fehlt oder ungültig")

    oauth = creds.get("claudeAiOauth", {})
    if not oauth.get("accessToken") or not oauth.get("refreshToken"):
        raise HTTPException(400, "Credentials müssen claudeAiOauth mit accessToken und refreshToken enthalten")

    cfg = load_config()
    prov = next((p for p in cfg.get("providers", []) if p["id"] == provider_id), None)
    if not prov:
        raise HTTPException(404, "Provider nicht gefunden")

    oauth_dir = Path(prov.get("oauth_dir", f"/data/claude-auth/{provider_id}"))
    try:
        oauth_dir.mkdir(parents=True, exist_ok=True)
        creds_file = oauth_dir / ".credentials.json"
        creds_file.write_text(json.dumps(creds, indent=2), encoding="utf-8")
        os.chmod(creds_file, 0o600)
        import subprocess
        subprocess.run(["chown", "1000:1000", str(creds_file)], check=False)
        return {"ok": True, "detail": "Credentials gespeichert. Container müssen neu gestartet werden."}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


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
