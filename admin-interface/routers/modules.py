"""Modules endpoint: listet registrierte Channels und Skills."""

from fastapi import APIRouter
from .deps import load_config, logger

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
            channels.append({
                "id": ch.channel_id,
                "display_name": ch.display_name,
                "enabled": ch.channel_id in active_channel_ids,
                "config_fields": n_config,
                "user_config_fields": n_user,
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
            skills.append({
                "id": sk.skill_id,
                "display_name": sk.display_name,
                "enabled": sk.skill_id in active_skill_ids,
                "config_fields": n_config,
                "user_config_fields": n_user,
            })

        return {"channels": channels, "skills": skills}

    except Exception as e:
        logger.error("[modules] Fehler beim Laden der Module: %s", e)
        return {"channels": [], "skills": [], "error": str(e)[:200]}
