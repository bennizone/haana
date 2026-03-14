"""Modules endpoint: listet registrierte Channels und Skills."""

import dataclasses

from fastapi import APIRouter, Request
from .deps import load_config, save_config, logger

router = APIRouter(tags=["modules"])


@router.get("/api/modules")
async def get_modules():
    """Gibt alle registrierten Channels und Skills zurück.

    Wird in Phase 3 vom Admin-Interface genutzt um die UI dynamisch aufzubauen.
    """
    try:
        from module_registry import registry
        cfg = load_config()
        all_channels = registry.get_all_channels()
        active_channel_ids = {c.channel_id for c in registry.get_active_channels(cfg)}
        all_skills = registry.get_all_skills()
        active_skill_ids = {s.skill_id for s in registry.get_active_skills(cfg)}

        channels = []
        for ch in all_channels:
            try:
                n_config = len(ch.get_config_schema())
            except Exception:
                n_config = 0
            try:
                n_user = len(ch.get_user_config_schema())
            except Exception:
                n_user = 0
            try:
                config_schema = [dataclasses.asdict(f) for f in ch.get_config_schema()]
            except Exception:
                config_schema = []
            try:
                user_config_schema = [dataclasses.asdict(f) for f in ch.get_user_config_schema()]
            except Exception:
                user_config_schema = []
            try:
                conn_status = ch.get_connection_status(cfg) if hasattr(ch, 'get_connection_status') else None
            except Exception:
                conn_status = None
            channels.append({
                "id": ch.channel_id,
                "display_name": ch.display_name,
                "enabled": ch.channel_id in active_channel_ids,
                "config_fields": n_config,
                "user_config_fields": n_user,
                "config_schema": config_schema,
                "user_config_schema": user_config_schema,
                "custom_tab_html": ch.get_custom_tab_html() if hasattr(ch, 'get_custom_tab_html') else "",
                "connection_status": conn_status,
            })

        skills = []
        for sk in all_skills:
            try:
                n_config = len(sk.get_config_schema())
            except Exception:
                n_config = 0
            try:
                n_user = len(sk.get_user_config_schema())
            except Exception:
                n_user = 0
            try:
                config_schema = [dataclasses.asdict(f) for f in sk.get_config_schema()]
            except Exception:
                config_schema = []
            try:
                user_config_schema = [dataclasses.asdict(f) for f in sk.get_user_config_schema()]
            except Exception:
                user_config_schema = []
            skills.append({
                "id": sk.skill_id,
                "display_name": sk.display_name,
                "enabled": sk.skill_id in active_skill_ids,
                "config_fields": n_config,
                "user_config_fields": n_user,
                "config_schema": config_schema,
                "user_config_schema": user_config_schema,
            })

        return {"channels": channels, "skills": skills}

    except Exception as e:
        logger.error("[modules] Fehler beim Laden der Module: %s", e)
        return {"channels": [], "skills": [], "error": str(e)[:200]}


@router.get("/api/modules/config")
async def get_modules_config():
    """Gibt aktuelle Config-Werte aller registrierten Module zurück."""
    try:
        from module_registry import registry
        cfg = load_config()
        result = {}
        for ch in registry.get_all_channels():
            root = getattr(ch, 'config_root', None)
            if root:
                result[ch.channel_id] = cfg.get(root, {})
            else:
                result[ch.channel_id] = cfg.get("services", {}).get(ch.channel_id, {})
        for sk in registry.get_all_skills():
            root = getattr(sk, 'config_root', None)
            if root:
                result[sk.skill_id] = cfg.get(root, {})
            else:
                result[sk.skill_id] = cfg.get("services", {}).get(sk.skill_id, {})
        return result
    except Exception as e:
        logger.error("[modules] Fehler beim Laden der Modul-Config: %s", e)
        return {}


@router.post("/api/modules/config")
async def save_modules_config(request: Request):
    """Speichert Config-Werte für Module in config.services.{id}.*"""
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return {"ok": False, "error": "Invalid body"}
        cfg = load_config()
        services = cfg.setdefault("services", {})
        from module_registry import registry
        all_modules = {
            **{ch.channel_id: ch for ch in registry.get_all_channels()},
            **{sk.skill_id: sk for sk in registry.get_all_skills()},
        }
        for mod_id, fields in body.items():
            if not isinstance(fields, dict):
                continue
            mod_obj = all_modules.get(mod_id)
            root = getattr(mod_obj, 'config_root', None) if mod_obj else None
            if root:
                target = cfg.setdefault(root, {})
            else:
                target = cfg.setdefault("services", {}).setdefault(mod_id, {})
            for key, val in fields.items():
                target[key] = val
        save_config(cfg)
        return {"ok": True}
    except Exception as e:
        logger.error("[modules] Fehler beim Speichern der Modul-Config: %s", e)
        return {"ok": False, "error": str(e)[:200]}


@router.get("/api/modules/status")
async def get_modules_status():
    """Status-Info aller registrierten Channels und Skills für den Status-Tab."""
    try:
        from module_registry import registry
        cfg = load_config()
        channels = []
        for ch in registry.get_all_channels():
            try:
                info = ch.get_status_info(cfg)
            except Exception as e:
                logger.warning("Channel %s: get_status_info() fehlgeschlagen: %s", ch.channel_id, e)
                info = {"status": "error", "label": "Fehler"}
            channels.append({
                "id": ch.channel_id,
                "display_name": ch.display_name,
                **info,
            })
        skills = []
        for sk in registry.get_all_skills():
            try:
                info = sk.get_status_info(cfg)
            except Exception as e:
                logger.warning("Skill %s: get_status_info() fehlgeschlagen: %s", sk.skill_id, e)
                info = {"status": "error", "label": "Fehler"}
            skills.append({
                "id": sk.skill_id,
                "display_name": sk.display_name,
                **info,
            })
        return {"channels": channels, "skills": skills}
    except Exception as e:
        logger.error("[modules] Fehler in get_modules_status: %s", e)
        return {"channels": [], "skills": [], "error": str(e)[:200]}
