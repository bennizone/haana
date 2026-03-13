"""Setup-Wizard endpoints: status, skip, current-config, reset, complete."""

from fastapi import APIRouter, HTTPException, Request

from .deps import (
    load_config, save_config,
    SYSTEM_USER_IDS, INST_DIR,
    render_claude_md, find_free_port, _ensure_system_users, _ensure_user_defaults,
    agent_manager, rebuild_state,
)

router = APIRouter(tags=["setup"])


@router.get("/api/setup-status")
async def setup_status():
    """Erkennt ob die Ersteinrichtung noetig ist."""
    cfg = load_config()
    providers = cfg.get("providers", [])
    has_provider = any(
        p.get("key") or (p.get("type", "").lower() == "ollama" and p.get("url"))
        for p in providers
    )
    setup_done = cfg.get("setup_done", False)
    users = [u for u in cfg.get("users", []) if u.get("id") not in SYSTEM_USER_IDS]

    if setup_done:
        return {"needs_setup": False}
    if not providers or not has_provider:
        return {"needs_setup": True, "step": 1}
    if not users:
        return {"needs_setup": True, "step": 2}
    return {"needs_setup": False}


@router.post("/api/setup/skip")
async def setup_skip(request: Request):
    """Ueberspringt den Wizard."""
    cfg = load_config()
    cfg["setup_done"] = True
    save_config(cfg)
    return {"ok": True}


@router.get("/api/setup/current-config")
async def setup_current_config():
    """Gibt bestehende Config fuer Vorausfuellung im Extend-Modus zurueck."""
    cfg = load_config()

    def _mask_key(key: str) -> str:
        if not key or len(key) < 9:
            return "***"
        return key[:4] + "..." + key[-4:]

    providers_out = []
    for p in cfg.get("providers", []):
        providers_out.append({
            "id": p.get("id", ""),
            "type": p.get("type", ""),
            "name": p.get("name", ""),
            "url": p.get("url", ""),
            "key_masked": _mask_key(p.get("key", "")),
        })

    llms_out = []
    for llm in cfg.get("llms", []):
        llms_out.append({
            "name": llm.get("name", ""),
            "type": llm.get("type", ""),
            "provider": llm.get("provider", ""),
            "model": llm.get("model", ""),
        })

    users_out = []
    for u in cfg.get("users", []):
        if u.get("id") in SYSTEM_USER_IDS:
            continue
        users_out.append({
            "id": u.get("id", ""),
            "display_name": u.get("display_name", ""),
            "primary_llm": u.get("primary_llm", ""),
            "fallback_llm": u.get("fallback_llm", ""),
            "language": u.get("language", "de"),
        })

    ha_assist_llm = ""
    ha_advanced_llm = ""
    for u in cfg.get("users", []):
        if u.get("id") == "ha-assist":
            ha_assist_llm = u.get("primary_llm", "")
        if u.get("id") == "ha-advanced":
            ha_advanced_llm = u.get("primary_llm", "")

    return {
        "providers": providers_out,
        "llms": llms_out,
        "users": users_out,
        "ha_assist_llm": ha_assist_llm,
        "ha_advanced_llm": ha_advanced_llm,
        "extraction_llm": cfg.get("memory", {}).get("extraction_llm", ""),
        "dream_enabled": cfg.get("dream", {}).get("enabled", False),
    }


@router.post("/api/setup/reset")
async def setup_reset(request: Request):
    """Setzt setup_done = false; bei mode='fresh' wird die Config geleert."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungueltiges JSON")

    mode = body.get("mode", "extend")
    cfg = load_config()

    if mode == "fresh":
        cfg["providers"] = []
        cfg["llms"] = []
        cfg["users"] = [u for u in cfg.get("users", []) if u.get("id") in SYSTEM_USER_IDS]

    cfg["setup_done"] = False
    save_config(cfg)
    return {"ok": True, "mode": mode}


@router.post("/api/setup/complete")
async def setup_complete(request: Request):
    """Schliesst den Setup-Wizard ab."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungueltiges JSON")

    cfg = load_config()
    mode = body.get("mode", "fresh")

    # 1. Providers setzen / mergen
    if "providers" in body:
        if mode == "extend":
            def _prov_merge_key(p: dict) -> tuple:
                return (p.get("type", ""), p.get("url", "") or p.get("name", ""))
            existing = cfg.get("providers", [])
            existing_map = {_prov_merge_key(p): p for p in existing}
            for bp in body["providers"]:
                mk = _prov_merge_key(bp)
                if mk in existing_map:
                    ep = existing_map[mk]
                    new_key = bp.get("key", "")
                    if new_key:
                        ep["key"] = new_key
                    if bp.get("url"):
                        ep["url"] = bp["url"]
                    if bp.get("name"):
                        ep["name"] = bp["name"]
                else:
                    existing.append(bp)
                    existing_map[mk] = bp
            cfg["providers"] = list(existing_map.values())
        else:
            cfg["providers"] = body["providers"]

    # 2. LLMs setzen
    if "llms" in body:
        cfg["llms"] = body["llms"]

    # 3. User anlegen
    if "users" in body:
        existing_ports = [u.get("api_port", 0) for u in cfg.get("users", [])]
        for wu in body["users"]:
            uid = wu.get("id", "").strip().lower()
            if not uid or uid in SYSTEM_USER_IDS:
                continue
            if any(u["id"] == uid for u in cfg.get("users", [])):
                continue
            port = find_free_port(existing_ports)
            existing_ports.append(port)
            user = {
                "id": uid,
                "display_name": wu.get("display_name", uid.capitalize()),
                "role": wu.get("role", "admin"),
                "language": wu.get("language", "de"),
                "primary_llm": wu.get("primary_llm", ""),
                "fallback_llm": wu.get("fallback_llm", ""),
                "ha_user": wu.get("ha_user", uid),
                "whatsapp_phone": wu.get("whatsapp_phone", ""),
                "api_port": port,
                "container_name": f"haana-instanz-{uid}-1",
                "claude_md_template": wu.get("claude_md_template", "admin" if wu.get("role") == "admin" else "user"),
                "caldav_url": "", "caldav_user": "", "caldav_pass": "",
                "imap_host": "", "imap_port": 993, "imap_user": "", "imap_pass": "",
                "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
            }
            cfg.setdefault("users", []).append(user)

    # 4. System-User LLMs zuweisen
    ha_assist_llm = body.get("ha_assist_llm", "")
    ha_advanced_llm = body.get("ha_advanced_llm", "")
    for u in cfg.get("users", []):
        if u["id"] == "ha-assist" and ha_assist_llm:
            u["primary_llm"] = ha_assist_llm
        if u["id"] == "ha-advanced" and ha_advanced_llm:
            u["primary_llm"] = ha_advanced_llm

    # 5. Memory extraction LLM
    extraction_llm = body.get("extraction_llm", "")
    if extraction_llm:
        cfg.setdefault("memory", {})["extraction_llm"] = extraction_llm

    # 6. Dream-Einstellungen
    if "dream_enabled" in body:
        cfg.setdefault("dream", {})["enabled"] = bool(body["dream_enabled"])

    # 7. Services
    if "services" in body:
        svc = cfg.setdefault("services", {})
        for k, v in body["services"].items():
            svc[k] = v

    _ensure_system_users(cfg)
    _ensure_user_defaults(cfg)

    # 8. CLAUDE.md fuer jeden neuen User generieren
    for u in cfg.get("users", []):
        uid = u.get("id", "")
        if not uid:
            continue
        claude_md_dir = INST_DIR / uid
        claude_md_dir.mkdir(parents=True, exist_ok=True)
        claude_md_path = claude_md_dir / "CLAUDE.md"
        if not claude_md_path.exists():
            content = render_claude_md(
                u.get("claude_md_template", "user"),
                u.get("display_name", uid.capitalize()),
                uid,
                u.get("ha_user", uid),
                u.get("language", "de"),
            )
            claude_md_path.write_text(content, encoding="utf-8")

    # 9. Setup als abgeschlossen markieren
    cfg["setup_done"] = True
    save_config(cfg)

    # 10. Agents starten
    started = []
    errors = []
    for u in cfg.get("users", []):
        uid = u.get("id", "")
        if not uid:
            continue
        try:
            result = await agent_manager.start_agent(u, cfg)
            if result.get("ok"):
                started.append(uid)
            else:
                errors.append({"id": uid, "error": result.get("error", "unbekannt")})
        except Exception as e:
            errors.append({"id": uid, "error": str(e)[:200]})

    # Rebuild-State erweitern
    for u in cfg.get("users", []):
        uid = u.get("id", "")
        if uid and uid not in rebuild_state:
            rebuild_state[uid] = {"status": "idle", "done": 0, "total": 0, "started": 0.0, "error": ""}

    return {"ok": True, "started": started, "errors": errors}
