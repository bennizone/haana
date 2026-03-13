"""
Shared dependencies for HAANA Admin-Interface routers.

Contains: config management, path constants, global state, helper functions.
"""

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

import auth as _auth

from .defaults import (
    DEFAULT_CONFIG,
    SYSTEM_USER_IDS,
    _SYSTEM_USERS,
    _ensure_system_users,
    _ensure_user_defaults,
    _slugify,
    _migrate_config,
    _migrate_providers_v2,
)

logger = logging.getLogger(__name__)

# ── Pfade ────────────────────────────────────────────────────────────────────

DATA_ROOT = Path(os.environ.get("HAANA_DATA_DIR", "/data"))
CONF_FILE = Path(os.environ.get("HAANA_CONF_FILE", "/data/config/config.json"))
INST_DIR = Path(os.environ.get("HAANA_INST_DIR", "/app/instanzen"))


# Media-Verzeichnis: HAANA_MEDIA_DIR > /media/haana (falls existent) > /data
def _get_media_dir() -> Path:
    env = os.environ.get("HAANA_MEDIA_DIR", "").strip()
    if env:
        return Path(env)
    default = Path("/media/haana")
    if default.exists():
        return default
    return Path("/data")


MEDIA_ROOT = _get_media_dir()


# Log-Verzeichnis: HAANA_LOG_DIR > {MEDIA_DIR}/logs
def _get_log_root() -> Path:
    env = os.environ.get("HAANA_LOG_DIR", "").strip()
    if env:
        return Path(env)
    return MEDIA_ROOT / "logs"


LOG_ROOT = _get_log_root()

INSTANCES = ["ha-assist", "ha-advanced", "haana-admin"]  # nur System-Instanzen

# Agent-API URLs (aus Env, Fallback für lokale Entwicklung)
AGENT_URLS: dict[str, str] = {
    "ha-assist": os.environ.get("AGENT_URL_HA_ASSIST", "http://localhost:8003"),
    "ha-advanced": os.environ.get("AGENT_URL_HA_ADVANCED", "http://localhost:8004"),
    "haana-admin": os.environ.get("AGENT_URL_HAANA_ADMIN", "http://localhost:8005"),
}

# URL dieser Admin-Interface-Instanz (für WA-Proxy-Routing)
ADMIN_SELF_URL = os.environ.get("HAANA_ADMIN_SELF_URL", "http://haana-admin-interface-1:8080")

# Bridge-Secret: Wenn gesetzt, müssen Requests an /api/whatsapp-config diesen Header senden
BRIDGE_SECRET = os.environ.get("HAANA_BRIDGE_SECRET", "").strip()

# Docker-Management Konstanten
HOST_BASE = os.environ.get("HAANA_HOST_BASE", "/opt/haana")
DATA_VOLUME = os.environ.get("HAANA_DATA_VOLUME", "haana_haana-data")
COMPOSE_NETWORK = os.environ.get("HAANA_COMPOSE_NETWORK", "haana_default")
AGENT_IMAGE = os.environ.get("HAANA_AGENT_IMAGE", "")
TEMPLATES_DIR = INST_DIR / "templates"

# Claude Auth
CLAUDE_AUTH_DIR = Path("/claude-auth")
CLAUDE_AUTH_HOST = Path("/home/haana/.claude")

# WhatsApp Bridge URL
WA_BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://whatsapp-bridge:3001")



# ── Hilfsfunktionen ──────────────────────────────────────────────────────────


def resolve_llm(llm_id: str, cfg: dict) -> tuple[dict, dict]:
    """Löst eine LLM-ID zu (llm_dict, provider_dict) auf."""
    llm = next((l for l in cfg.get("llms", []) if l["id"] == llm_id), {})
    if not llm:
        return {}, {}
    provider = next((p for p in cfg.get("providers", []) if p["id"] == llm.get("provider_id")), {})
    return llm, provider


def find_ollama_url(cfg: dict) -> str:
    """Findet die Ollama-URL aus Providern."""
    mem_cfg = cfg.get("memory", {})
    embedding_id = mem_cfg.get("embedding_id", "")
    emb = next((e for e in cfg.get("embeddings", []) if e.get("id") == embedding_id), None)
    if emb:
        emb_prov = next((p for p in cfg.get("providers", []) if p.get("id") == emb.get("provider_id")), {})
        if emb_prov.get("type") == "ollama" and emb_prov.get("url"):
            return emb_prov["url"]

    mem = cfg.get("memory", {})
    e_llm_id = mem.get("extraction_llm", "")
    if e_llm_id:
        e_llm, e_prov = resolve_llm(e_llm_id, cfg)
        if e_prov.get("type") == "ollama" and e_prov.get("url"):
            return e_prov["url"]

    for p in cfg.get("providers", []):
        if p.get("type") == "ollama" and p.get("url"):
            return p["url"]

    return ""


def find_references(entity_type: str, entity_id: str, cfg: dict) -> list[str]:
    """Findet alle Referenzen auf eine Entity (provider oder llm)."""
    refs: list[str] = []

    if entity_type == "provider":
        for llm in cfg.get("llms", []):
            if llm.get("provider_id") == entity_id:
                refs.append(f"LLM: {llm.get('name', llm['id'])}")
        for emb in cfg.get("embeddings", []):
            if emb.get("provider_id") == entity_id:
                refs.append(f"Embedding: {emb.get('name', emb.get('id', ''))}")

    elif entity_type == "llm":
        for user in cfg.get("users", []):
            uid = user.get("id", "?")
            if user.get("primary_llm") == entity_id:
                refs.append(f"User {uid} (Primary)")
            if user.get("fallback_llm") == entity_id:
                refs.append(f"User {uid} (Fallback)")
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
            cfg.get("use_cases", {}).pop("embeddings", None)
            if _migrate_config(cfg):
                save_config(cfg)
            if _migrate_providers_v2(cfg):
                save_config(cfg)
            if "embedding" in cfg and "embeddings" not in cfg:
                old_emb = cfg.pop("embedding")
                cfg["embeddings"] = [{
                    "id": "emb-1",
                    "name": "Embedding 1",
                    "provider_id": old_emb.get("provider_id", "__local__"),
                    "model": old_emb.get("model", ""),
                    "dims": old_emb.get("dims", 1024),
                }]
                fp = old_emb.get("fallback_provider_id", "")
                if fp:
                    cfg.setdefault("memory", {})["fallback_embedding_id"] = fp
                save_config(cfg)
            dream_defaults = DEFAULT_CONFIG["dream"]
            if "dream" not in cfg:
                cfg["dream"] = dict(dream_defaults)
            else:
                for k, v in dream_defaults.items():
                    cfg["dream"].setdefault(k, v)
            cfg.setdefault("companion_token", "")
            services = cfg.setdefault("services", {})
            if not services.get("qdrant_url"):
                services["qdrant_url"] = os.environ.get("QDRANT_URL", "http://qdrant:6333")
                save_config(cfg)
            _ensure_system_users(cfg)
            _ensure_user_defaults(cfg)
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    cfg["providers"] = list(DEFAULT_CONFIG["providers"])
    cfg["llms"] = list(DEFAULT_CONFIG["llms"])
    cfg["users"] = list(DEFAULT_CONFIG["users"])
    _ensure_system_users(cfg)
    _ensure_user_defaults(cfg)
    return cfg


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


def get_all_instances() -> list[str]:
    """Alle Instanzen: statische + dynamische User aus config.json."""
    cfg = load_config()
    user_ids = [u["id"] for u in cfg.get("users", []) if u.get("id")]
    result = list(INSTANCES)
    for uid in user_ids:
        if uid not in result:
            result.append(uid)
    return result


def get_agent_url(instance: str) -> str:
    """Agent-URL: AgentManager oder Fallback aus AGENT_URLS/Config."""
    if agent_manager:
        url = agent_manager.agent_url(instance)
        if url:
            return url
    if instance in AGENT_URLS:
        return AGENT_URLS[instance]
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == instance), None)
    if user:
        return f"http://{user.get('container_name', f'haana-instanz-{instance}-1')}:{user['api_port']}"
    return ""


def verify_companion_token(request, config: dict) -> bool:
    """Prueft den Bearer-Token aus dem Authorization-Header gegen den Config-Token."""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    expected = config.get("companion_token", "")
    return bool(token and expected and secrets.compare_digest(token, expected))


# ── Language-Namen ───────────────────────────────────────────────────────────

LANGUAGE_NAMES: dict[str, str] = {
    "de": "German",
    "en": "English",
    "tr": "Turkish",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
}


def render_claude_md(template_name: str, display_name: str, user_id: str, ha_user: str = "", language: str = "de") -> str:
    """Generiert CLAUDE.md aus Template mit Platzhalter-Ersetzung."""
    tpl_path = TEMPLATES_DIR / f"{template_name}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "user.md"
    content = tpl_path.read_text(encoding="utf-8")
    content = content.replace("{{DISPLAY_NAME}}", display_name)
    content = content.replace("{{USER_ID}}", user_id)
    content = content.replace("{{HA_USER}}", ha_user or user_id)
    response_language = LANGUAGE_NAMES.get(language, language)
    content = content.replace("{{RESPONSE_LANGUAGE}}", response_language)
    cfg = load_config()
    timezone = cfg.get("services", {}).get("timezone", "Europe/Berlin")
    content = content.replace("{{TIMEZONE}}", timezone)
    return content


def find_free_port(existing_ports: list[int]) -> int:
    """Nächsten freien Port ab 8001 finden."""
    port = 8001
    while port in existing_ports:
        port += 1
    return port


# ── Globaler State (gesetzt von main.py bei Startup) ─────────────────────────

agent_manager: Optional[object] = None  # AgentManager-Instanz
docker_client: Optional[object] = None  # Docker-Client-Instanz
HAANA_MODE: str = ""  # "docker" | "addon"

# Rebuild-Zustand (pro Instanz)
rebuild_state: dict[str, dict] = {
    inst: {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}
    for inst in ["ha-assist", "ha-advanced", "haana-admin"]
}

# Dream-Zustand (pro Instanz)
dream_state: dict[str, dict] = {}

# In-Memory SSO Token Store
import threading as _threading
SSO_TOKENS: dict[str, float] = {}
SSO_LOCK = _threading.Lock()

# OAuth login session
oauth_login_session: dict | None = None


def sync_rebuild_state():
    """Rebuild-State mit dynamischen Usern aus config.json synchronisieren."""
    cfg = load_config()
    for u in cfg.get("users", []):
        uid = u.get("id", "")
        if uid and uid not in rebuild_state:
            rebuild_state[uid] = {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}
