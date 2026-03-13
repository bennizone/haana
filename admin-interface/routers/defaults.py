"""
Default configuration, system users, and migration logic for HAANA.

Extracted from deps.py to keep that module under 400 lines.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


# ── Default-Konfiguration ────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "providers": [],
    "llms": [],
    "memory": {
        "extraction_llm": "",
        "extraction_llm_fallback": "",
        "context_enrichment": False,
        "context_before": 3,
        "context_after": 2,
        "window_size": int(os.environ.get("HAANA_WINDOW_SIZE", "20")),
        "window_minutes": int(os.environ.get("HAANA_WINDOW_MINUTES", "60")),
        "min_messages": 5,
        "embedding_id": "",
        "fallback_embedding_id": "",
    },
    "embeddings": [],
    "log_retention": {
        "conversations": None,  # niemals löschen
        "llm-calls": 30,
        "tool-calls": 30,
        "memory-ops": 30,
    },
    "services": {
        "ha_url": os.environ.get("HA_URL", ""),
        "ha_token": "",
        "ha_mcp_enabled": False,
        "ha_mcp_type": "extended",
        "ha_mcp_url": "",
        "ha_mcp_token": "",
        "ha_auto_backup": False,
        "qdrant_url": os.environ.get("QDRANT_URL", "http://qdrant:6333"),
        "timezone": "Europe/Berlin",
    },
    "companion_token": "",
    "users": [
        {
            "id": "ha-assist", "display_name": "HAANA Voice", "role": "voice",
            "system": True,
            "language": "de",
            "primary_llm": "", "fallback_llm": "",
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
            "language": "de",
            "primary_llm": "", "fallback_llm": "",
            "ha_user": "", "whatsapp_phone": "",
            "api_port": 8004, "container_name": "haana-instanz-ha-advanced-1",
            "claude_md_template": "ha-advanced",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
        {
            "id": "haana-admin", "display_name": "HAANA Admin", "role": "admin",
            "system": True,
            "language": "de",
            "primary_llm": "", "fallback_llm": "",
            "ha_user": "", "whatsapp_phone": "",
            "api_port": 8005, "container_name": "haana-instanz-haana-admin-1",
            "claude_md_template": "haana-admin",
            "caldav_url": "", "caldav_user": "", "caldav_pass": "",
            "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
        },
    ],
    "ollama_compat": {
        "enabled": True,
        "exposed_models": ["ha-assist", "ha-advanced"],
    },
    "dream": {
        "enabled": False,
        "schedule": "02:00",
        "llm": "",
        "scopes": [],
    },
    "whatsapp": {
        "mode": "separate",
        "self_prefix": "!h ",
    },
}


# ── System-User ──────────────────────────────────────────────────────────────

_SYSTEM_USERS = {
    "ha-assist": DEFAULT_CONFIG["users"][0],
    "ha-advanced": DEFAULT_CONFIG["users"][1],
    "haana-admin": DEFAULT_CONFIG["users"][2],
}
SYSTEM_USER_IDS = set(_SYSTEM_USERS.keys())


def _ensure_system_users(cfg: dict) -> None:
    """Stellt sicher, dass die System-Instanzen immer in users vorhanden sind."""
    users = cfg.setdefault("users", [])
    existing = {u["id"]: u for u in users if u.get("id") in SYSTEM_USER_IDS}
    cfg["users"] = [u for u in users if u.get("id") not in SYSTEM_USER_IDS]
    for sys_id, default_user in _SYSTEM_USERS.items():
        if sys_id in existing:
            merged = {**default_user, **existing[sys_id]}
            merged["system"] = True
            cfg["users"].append(merged)
        else:
            cfg["users"].append(dict(default_user))


def _ensure_user_defaults(cfg: dict) -> None:
    """Stellt sicher, dass alle User neu hinzugefügte Felder mit Defaults haben."""
    for user in cfg.get("users", []):
        user.setdefault("language", "de")
    cfg.setdefault("embeddings", [])
    mem = cfg.setdefault("memory", {})
    mem.setdefault("embedding_id", "")
    mem.setdefault("fallback_embedding_id", "")


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Einfacher Slug: Kleinbuchstaben, Umlaute ersetzen, nur [a-z0-9-]."""
    text = text.lower().strip()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


# ── Config-Migration ─────────────────────────────────────────────────────────

def _migrate_config(cfg: dict) -> bool:
    """Migriert alte llm_providers[]-Struktur zu providers[] + llms[]."""
    if "providers" in cfg or "llm_providers" not in cfg:
        return False

    old_slots = cfg.pop("llm_providers", [])
    cfg.pop("use_cases", None)

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

    for user in cfg.get("users", []):
        if "primary_llm_slot" in user:
            old_slot = user.pop("primary_llm_slot")
            user["primary_llm"] = slot_to_llm_id.get(old_slot, llms[0]["id"] if llms else "")
        if "extraction_llm_slot" in user:
            user.pop("extraction_llm_slot")
        user.pop("extraction_llm", None)
        user.setdefault("fallback_llm", "")

    emb = cfg.get("embedding", {})
    if "provider" in emb and "provider_id" not in emb:
        old_prov_type = emb.pop("provider")
        matching = next((p for p in providers if p["type"] == old_prov_type), None)
        emb["provider_id"] = matching["id"] if matching else ""
        emb.setdefault("fallback_provider_id", "")

    mem = cfg.setdefault("memory", {})
    if "extraction_llm" not in mem:
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
    """Migriert Provider v2: auth_method für Anthropic, ollama_url entfernen."""
    changed = False

    for p in cfg.get("providers", []):
        if p.get("type") == "anthropic" and "auth_method" not in p:
            p["auth_method"] = "oauth" if not p.get("key") else "api_key"
            changed = True

    services = cfg.get("services", {})
    old_ollama_url = services.pop("ollama_url", None)
    if old_ollama_url is not None:
        changed = True
        for p in cfg.get("providers", []):
            if p.get("type") == "ollama" and not p.get("url"):
                p["url"] = old_ollama_url

    for p in cfg.get("providers", []):
        if p.get("type") == "anthropic" and p.get("auth_method") == "oauth" and "oauth_dir" not in p:
            p["oauth_dir"] = f"/data/claude-auth/{p['id']}"
            changed = True

    return changed
