"""User-Management: CRUD, restart, stop."""

import re

from fastapi import APIRouter, HTTPException, Request

from .deps import (
    load_config, save_config, INST_DIR, SYSTEM_USER_IDS,
    render_claude_md, find_free_port,
    agent_manager, rebuild_state,
)

router = APIRouter(tags=["users"])


@router.get("/api/users")
async def get_users():
    """User-Liste mit Agent-Status."""
    cfg = load_config()
    users = cfg.get("users", [])
    result = []
    for u in users:
        status = agent_manager.agent_status(u["id"])
        result.append({**u, "container_status": status})
    return result


@router.post("/api/users")
async def create_user(request: Request):
    """Legt neuen User an."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    uid = (body.get("id") or "").strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,29}$", uid):
        raise HTTPException(400, "ID muss [a-z0-9-], max 30 Zeichen, nicht mit - beginnen")
    if uid in SYSTEM_USER_IDS:
        raise HTTPException(409, f"'{uid}' ist eine reservierte System-ID")

    cfg = load_config()
    existing = [u["id"] for u in cfg.get("users", [])]
    if uid in existing:
        raise HTTPException(409, f"User '{uid}' existiert bereits")

    used_ports = [u.get("api_port", 0) for u in cfg.get("users", [])]
    port = find_free_port(used_ports)

    default_primary = cfg.get("llms", [{}])[0].get("id", "") if cfg.get("llms") else ""

    user: dict = {
        "id": uid,
        "display_name": body.get("display_name") or uid.capitalize(),
        "role": body.get("role", "user"),
        "language": body.get("language", "de"),
        "primary_llm": body.get("primary_llm", default_primary),
        "fallback_llm": body.get("fallback_llm", ""),
        "ha_user": body.get("ha_user", uid),
        "whatsapp_phone": body.get("whatsapp_phone", ""),
        "api_port": port,
        "container_name": f"haana-instanz-{uid}-1",
        "claude_md_template": body.get("claude_md_template", "admin" if body.get("role") == "admin" else "user"),
        "caldav_url": "", "caldav_user": "", "caldav_pass": "",
        "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }

    # CLAUDE.md generieren
    claude_md_dir = INST_DIR / uid
    claude_md_dir.mkdir(parents=True, exist_ok=True)
    claude_md_content = render_claude_md(
        user["claude_md_template"], user["display_name"], uid, user["ha_user"],
        user.get("language", "de")
    )
    (claude_md_dir / "CLAUDE.md").write_text(claude_md_content, encoding="utf-8")

    # Agent starten
    result = await agent_manager.start_agent(user, cfg)

    # User in config speichern
    cfg.setdefault("users", []).append(user)
    save_config(cfg)

    # Rebuild-State erweitern
    rebuild_state[uid] = {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}

    return {"ok": True, "user": user, "container": result}


@router.patch("/api/users/{user_id}")
async def update_user(user_id: str, request: Request):
    """User-Felder aktualisieren."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    cfg = load_config()
    users = cfg.get("users", [])
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")

    restart_fields = {"primary_llm", "fallback_llm", "ha_user", "role", "claude_md_template", "language"}
    needs_restart = any(k in body and body[k] != user.get(k) for k in restart_fields)

    user.update({k: v for k, v in body.items() if k not in ("id", "api_port", "container_name")})
    save_config(cfg)

    if "display_name" in body or "claude_md_template" in body or "ha_user" in body or "language" in body:
        claude_md_content = render_claude_md(
            user["claude_md_template"], user["display_name"], user_id,
            user.get("ha_user", user_id), user.get("language", "de")
        )
        claude_md_dir = INST_DIR / user_id
        claude_md_dir.mkdir(parents=True, exist_ok=True)
        (claude_md_dir / "CLAUDE.md").write_text(claude_md_content, encoding="utf-8")

    container_result = None
    if needs_restart:
        container_result = await agent_manager.start_agent(user, cfg)

    return {"ok": True, "user": user, "restarted": needs_restart, "container": container_result}


@router.delete("/api/users/{user_id}")
async def delete_user(user_id: str):
    """User löschen."""
    cfg = load_config()
    users = cfg.get("users", [])
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    if user.get("system"):
        raise HTTPException(403, "System-Instanzen können nicht gelöscht werden")

    remove_result = await agent_manager.remove_agent(user_id)
    container_removed = remove_result.get("ok", False)

    import shutil
    inst_path = INST_DIR / user_id
    if inst_path.exists():
        shutil.rmtree(inst_path, ignore_errors=True)

    cfg["users"] = [u for u in users if u["id"] != user_id]
    save_config(cfg)

    rebuild_state.pop(user_id, None)

    return {"ok": True, "container_removed": container_removed}


@router.post("/api/users/{user_id}/restart")
async def restart_user_container(user_id: str):
    """Agent für einen User neu starten."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    result = await agent_manager.start_agent(user, cfg)
    return {"ok": result.get("ok", False), "container": result}


@router.post("/api/users/{user_id}/stop")
async def stop_user_container(user_id: str):
    """Agent für einen User stoppen."""
    cfg = load_config()
    user = next((u for u in cfg.get("users", []) if u["id"] == user_id), None)
    if not user:
        raise HTTPException(404, f"User '{user_id}' nicht gefunden")
    return await agent_manager.stop_agent(user_id)
