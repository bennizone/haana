"""System endpoints: status, update, git, supervisor, dev provider, ollama-compat."""

import asyncio
import json
import logging
import os
import re
import shutil
import glob as _glob
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

import auth as _auth
import git_integration as _git
from .deps import (
    load_config, save_config, get_all_instances, find_ollama_url,
    agent_manager, SYSTEM_USER_IDS, HOST_BASE, LOG_ROOT, CLAUDE_AUTH_DIR,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get('/health')
async def health_check():
    return {'status': 'ok'}


@router.get('/api/health')
async def api_health_check():
    return {'status': 'ok'}


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def get_status():
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    ollama_url = find_ollama_url(cfg)

    status: dict = {"qdrant": "unknown", "ollama": "unknown", "logs": {}}

    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{qdrant_url}/collections")
            colls = r.json().get("result", {}).get("collections", [])
            coll_names = [c["name"] for c in colls]
            total_vectors = 0
            _emb_id = cfg.get("memory", {}).get("embedding_id", "")
            _emb_obj = next((e for e in cfg.get("embeddings", []) if e.get("id") == _emb_id), None)
            configured_dims = _emb_obj.get("dims", 1024) if _emb_obj else 1024
            dims_mismatch = False
            for cname in coll_names:
                try:
                    cr = await client.get(f"{qdrant_url}/collections/{cname}")
                    res = cr.json().get("result", {})
                    total_vectors += res.get("points_count", 0) or res.get("vectors_count", 0) or 0
                    coll_dim = (res.get("config", {}).get("params", {})
                                .get("vectors", {}).get("size", 0))
                    if coll_dim and coll_dim != configured_dims:
                        dims_mismatch = True
                except Exception:
                    pass
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

    for inst in get_all_instances():
        inst_log = LOG_ROOT / "conversations" / inst
        if inst_log.exists():
            days = sorted(inst_log.glob("*.jsonl"), reverse=True)
            status["logs"][inst] = {
                "days": len(days),
                "latest": days[0].name.replace(".jsonl", "") if days else None,
            }

    hints: list[dict] = []
    providers = cfg.get("providers", [])
    has_provider = any(
        p.get("key") or (p.get("type", "").lower() == "ollama" and p.get("url"))
        for p in providers
    )
    if not providers or not has_provider:
        hints.append({"type": "error", "msg": "no_provider_key", "action": "config_providers"})
    non_system_users = [u for u in cfg.get("users", []) if u.get("id") not in SYSTEM_USER_IDS]
    if not non_system_users:
        hints.append({"type": "warning", "msg": "no_users", "action": "users"})
    if non_system_users and agent_manager:
        all_offline = True
        for u in non_system_users:
            s = agent_manager.agent_status(u["id"])
            if s and s not in ("offline", "stopped", "unknown", "not_found"):
                all_offline = False
                break
        if all_offline:
            hints.append({"type": "info", "msg": "agents_offline", "action": "users"})
    status["hints"] = hints

    return status


@router.get("/api/status/ollama-compat")
async def get_ollama_compat_status(request: Request):
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    cfg = load_config()
    oc = cfg.get("ollama_compat", {})
    enabled = oc.get("enabled", True)
    exposed = oc.get("exposed_models", ["ha-assist", "ha-advanced"])
    users = cfg.get("users", [])
    llms = {l["id"]: l for l in cfg.get("llms", [])}
    providers = {p["id"]: p for p in cfg.get("providers", [])}

    agents = []
    for user in users:
        uid = user.get("id", "")
        primary_llm_id = user.get("primary_llm", "")
        llm = llms.get(primary_llm_id)
        provider = providers.get(llm.get("provider_id", "")) if llm else None

        reason = None
        if not enabled:
            reason = "ollama_compat_disabled"
        elif not primary_llm_id:
            reason = "no_primary_llm"
        elif not llm:
            reason = "llm_not_found"
        elif not provider:
            reason = "provider_not_found"

        is_exposed = uid in exposed
        available = enabled and bool(llm) and bool(provider)

        agents.append({
            "id": uid,
            "name": user.get("name", uid),
            "available": available,
            "is_proxy_model": is_exposed,
            "primary_llm": primary_llm_id or None,
            "llm_model": llm.get("model", "") if llm else None,
            "reason": reason,
        })

    return {
        "enabled": enabled,
        "agents": agents,
    }


@router.get("/api/system-status")
async def system_status():
    """Checkliste aller wichtigen Konfigurationspunkte."""
    cfg = load_config()
    providers = cfg.get("providers", [])
    users = [u for u in cfg.get("users", []) if u.get("id") not in SYSTEM_USER_IDS]
    services = cfg.get("services", {})

    has_llm_provider = any(
        (p.get("key") or (p.get("type", "").lower() == "ollama" and p.get("url")))
        for p in providers if p.get("type", "").lower() != "ollama_embedding"
    )
    has_embedding = any(
        p.get("type", "").lower() in ("ollama_embedding", "openai_embedding")
        or (p.get("type", "").lower() == "ollama" and p.get("url"))
        for p in providers
    )
    ha_url = services.get("ha_url", "")
    ha_token = services.get("ha_token", "")
    ha_configured = bool(ha_url and ha_token)
    user_llm_ok = all(u.get("primary_llm") for u in users) if users else False

    return {
        "checks": [
            {"id": "provider", "label": "LLM-Provider konfiguriert", "ok": has_llm_provider, "link": "#providers"},
            {"id": "users", "label": "Mindestens ein Nutzer angelegt", "ok": bool(users), "link": "#users"},
            {"id": "user_llm", "label": "Alle Nutzer haben ein LLM zugewiesen", "ok": user_llm_ok, "link": "#users"},
            {"id": "embedding", "label": "Embedding-Modell konfiguriert", "ok": has_embedding, "link": "#providers"},
            {"id": "ha", "label": "Home Assistant verbunden", "ok": ha_configured, "link": "#config"},
            {"id": "companion_token", "label": "Companion-Token gesetzt", "ok": bool(cfg.get("companion_token")), "link": "#config"},
        ]
    }


# ── Supervisor ───────────────────────────────────────────────────────────────

@router.get("/api/supervisor/addons")
async def supervisor_addons():
    """Listet installierte Add-ons via HA Supervisor API."""
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        return {"ok": False, "addon_mode": False, "addons": []}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "http://supervisor/addons",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            addons = data.get("addons", [])
            result = [
                {"slug": a.get("slug", ""), "name": a.get("name", ""), "state": a.get("state", "")}
                for a in addons
            ]
            return {"ok": True, "addon_mode": True, "addons": result}
    except Exception as e:
        return {"ok": False, "addon_mode": True, "addons": [], "error": str(e)[:200]}


@router.get("/api/supervisor/self")
async def supervisor_self():
    """Liefert Infos über das eigene Add-on."""
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        return {"ok": False, "error": "Not running as add-on"}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "http://supervisor/addons/self/info",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            return {
                "ok": True,
                "hostname": data.get("hostname", ""),
                "ingress_url": data.get("ingress_url", ""),
                "port": 8080,
            }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── Git Integration ──────────────────────────────────────────────────────────

@router.get("/api/git/status")
async def api_git_status():
    return await _git.git_status()


@router.post("/api/git/pull")
async def api_git_pull(request: Request):
    return await _git.git_pull()


@router.post("/api/git/push")
async def api_git_push(request: Request):
    return await _git.git_push()


@router.post("/api/git/connect")
async def api_git_connect(request: Request):
    body = await request.json()
    url = body.get("url", "")
    token = body.get("token", "")
    if not url.startswith(("https://", "http://")):
        return {"ok": False, "error": "URL muss mit https:// beginnen"}
    return await _git.git_connect(url, token, load_config, save_config)


@router.get("/api/git/log")
async def api_git_log():
    return await _git.git_log()


# ── System Update ────────────────────────────────────────────────────────────

@router.post("/api/system/update")
async def system_update():
    """Git pull + Agent-Image rebuild + Admin-Interface rebuild + Neustart."""
    host_path = HOST_BASE or "/opt/haana"

    async def _do_update():
        import asyncio as _asyncio
        import httpx as _httpx
        loop = _asyncio.get_running_loop()
        _docker_client = getattr(agent_manager, "_client", None)
        admin_port = os.environ.get("HAANA_ADMIN_PORT", "8080")

        try:
            # 1. Git update (als root im Container, kein su nötig)
            p1 = await _asyncio.create_subprocess_exec(
                "git", "-C", host_path, "fetch", "origin",
                stdout=_asyncio.subprocess.DEVNULL, stderr=_asyncio.subprocess.DEVNULL,
            )
            await p1.wait()
            p2 = await _asyncio.create_subprocess_exec(
                "git", "-C", host_path, "reset", "--hard", "origin/main",
                stdout=_asyncio.subprocess.DEVNULL, stderr=_asyncio.subprocess.DEVNULL,
            )
            await p2.wait()

            # 2. Docker-Images bauen via SDK
            if _docker_client:
                await loop.run_in_executor(
                    None,
                    lambda: list(_docker_client.api.build(
                        path=host_path, tag="haana-instanz:latest", rm=True, decode=True
                    )),
                )
                await loop.run_in_executor(
                    None,
                    lambda: list(_docker_client.api.build(
                        path=f"{host_path}/admin-interface",
                        tag="haana-admin-interface:latest", rm=True, decode=True
                    )),
                )

            # 3. docker compose --profile agents up -d --build (startet auch WA-Bridge)
            p3 = await _asyncio.create_subprocess_exec(
                "docker", "compose", "--project-directory", host_path,
                "--profile", "agents", "up", "-d", "--build",
                stdout=_asyncio.subprocess.DEVNULL, stderr=_asyncio.subprocess.DEVNULL,
            )
            await p3.wait()

            # 4. /data/context sicherstellen (Sliding-Window-Persistenz)
            data_context = Path("/data/context")
            data_context.mkdir(parents=True, exist_ok=True)
            try:
                os.chown(data_context, 1000, 1000)
            except Exception:
                pass

            # 5. Agenten neu starten (vor Admin-Interface-Restart, da Container sich sonst selbst beendet)
            await _asyncio.sleep(5)
            for _ in range(30):
                try:
                    async with _httpx.AsyncClient(timeout=2.0) as client:
                        r = await client.get(f"http://localhost:{admin_port}/health")
                        if r.status_code == 200:
                            break
                except Exception:
                    pass
                await _asyncio.sleep(1)

            cfg = load_config()
            token = cfg.get("admin_session", "")
            if token:
                try:
                    async with _httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"http://localhost:{admin_port}/api/instances/restart-all",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                    logger.info("[system/update] Agenten neu gestartet")
                except Exception as e:
                    logger.warning(f"[system/update] Agent-Restart fehlgeschlagen: {e}")

            # 6. Admin-Interface neu starten (letzter Schritt — beendet diesen laufenden Code)
            await _asyncio.sleep(2)
            if _docker_client:
                try:
                    c = _docker_client.containers.get("haana-admin-interface-1")
                    c.restart()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[system/update] Fehler: {e}")

    asyncio.create_task(_do_update())
    return {"ok": True, "message": "Update gestartet — Seite lädt in ~60 Sekunden neu"}


# ── Dev: Claude Code Provider ────────────────────────────────────────────────

def _sanitize_env_value(value: str) -> str:
    """Bereinigt einen Wert fuer die Verwendung in export VAR='...' Shell-Zeilen."""
    return value.replace('"', '\\"').replace('\n', '').replace('\r', '').replace('\x00', '')


def _build_claude_provider_env(provider: dict, model: str, mcp_web_search: bool, mcp_image: bool, cfg: dict) -> list[str]:
    """Baut export/unset-Zeilen fuer /opt/haana/.claude_provider.env."""
    lines = ["# HAANA Claude Code Provider — automatisch generiert"]
    for var in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_MODEL", "CLAUDE_CONFIG_DIR",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                "MINIMAX_API_KEY", "MINIMAX_API_HOST"]:
        lines.append(f"unset {var}")
    lines.append("")
    ptype = provider.get("type", "")
    if ptype == "anthropic":
        if provider.get("auth_method") == "oauth":
            pass  # CLAUDE_CONFIG_DIR nicht setzen — Default ~/.claude ist korrekt
        else:
            key = provider.get("key", "")
            if key:
                lines.append(f'export ANTHROPIC_API_KEY="{_sanitize_env_value(key)}"')
    elif ptype == "minimax":
        url = provider.get("url", "https://api.minimax.io/anthropic")
        key = provider.get("key", "")
        lines.append(f'export ANTHROPIC_BASE_URL="{_sanitize_env_value(url)}"')
        if key:
            lines.append(f'export ANTHROPIC_AUTH_TOKEN="{_sanitize_env_value(key)}"')
        if model:
            lines.append(f'export ANTHROPIC_MODEL="{_sanitize_env_value(model)}"')
        lines.append('export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"')
    elif ptype == "ollama":
        url = provider.get("url", "http://ollama:11434")
        lines.append(f'export ANTHROPIC_BASE_URL="{_sanitize_env_value(url)}"')
        lines.append('export ANTHROPIC_AUTH_TOKEN="ollama"')
        if model:
            lines.append(f'export ANTHROPIC_MODEL="{_sanitize_env_value(model)}"')
    else:
        url = provider.get("url", "")
        key = provider.get("key", "")
        if url:
            lines.append(f'export ANTHROPIC_BASE_URL="{_sanitize_env_value(url)}"')
        if key:
            lines.append(f'export ANTHROPIC_API_KEY="{_sanitize_env_value(key)}"')
        if model:
            lines.append(f'export ANTHROPIC_MODEL="{_sanitize_env_value(model)}"')
    if mcp_web_search or mcp_image:
        mm = next((p for p in cfg.get("providers", []) if p.get("type") == "minimax"), provider if ptype == "minimax" else None)
        if mm:
            mcp_key = mm.get("key", "")
            mcp_host = mm.get("url", "https://api.minimax.io/anthropic").replace("/anthropic", "")
            if mcp_key:
                lines.append(f'export MINIMAX_API_KEY="{_sanitize_env_value(mcp_key)}"')
            lines.append(f'export MINIMAX_API_HOST="{_sanitize_env_value(mcp_host)}"')
    return lines


@router.get("/api/dev/claude-provider")
async def get_dev_claude_provider(request: Request):
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=403, detail="Nicht autorisiert")
    cfg = load_config()
    return cfg.get("dev", {}).get("claude_provider", {})


@router.post("/api/dev/claude-provider")
async def set_dev_claude_provider(request: Request):
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=403, detail="Nicht autorisiert")
    body = await request.json()
    provider_id = body.get("provider_id", "")
    model = body.get("model", "")
    mcp_web_search = bool(body.get("mcp_web_search", False))
    mcp_image = bool(body.get("mcp_image", False))
    cfg = load_config()
    providers = cfg.get("providers", [])
    provider = next((p for p in providers if p.get("id") == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' nicht gefunden")
    if model and not re.match(r'^[\w\-\.\:\/]{1,100}$', model):
        raise HTTPException(status_code=422, detail="Ungültiger Modell-Name")
    if "dev" not in cfg:
        cfg["dev"] = {}
    cfg["dev"]["claude_provider"] = {
        "provider_id": provider_id,
        "model": model,
        "mcp_web_search": mcp_web_search,
        "mcp_image": mcp_image,
    }
    save_config(cfg)
    # OAuth-Credentials fuer su - haana auf Host-Pfad kopieren
    credentials_warning = None
    if provider.get("type") == "anthropic" and provider.get("auth_method") == "oauth":
        provider_id_str = provider.get("id", provider_id)
        oauth_dir = Path(provider.get("oauth_dir", f"/data/claude-auth/{provider_id_str}"))
        src = oauth_dir / ".credentials.json"
        dst = CLAUDE_AUTH_DIR / ".credentials.json"
        # Pfad validieren — nur /data/claude-auth/ erlaubt
        try:
            resolved = src.resolve()
        except Exception:
            resolved = src
        if not str(resolved).startswith("/data/claude-auth/"):
            logger.warning("dev: oauth_dir ausserhalb erlaubtem Pfad, kein Copy: %s", src)
        else:
            try:
                if src.exists():
                    CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    dst.chmod(0o600)
                    logger.info("dev: OAuth-Credentials nach %s kopiert", dst)
                else:
                    logger.warning("dev: OAuth-Credentials nicht gefunden: %s", src)
            except Exception as exc:
                logger.warning("dev: Konnte Credentials nicht kopieren: %s", exc)
                credentials_warning = str(exc)
    env_lines = _build_claude_provider_env(provider, model, mcp_web_search, mcp_image, cfg)
    env_file = Path("/opt/haana/.claude_provider.env")
    try:
        env_file.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        env_file.chmod(0o600)
    except Exception as exc:
        logger.warning("dev: Konnte .claude_provider.env nicht schreiben: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    result: dict = {"ok": True}
    if credentials_warning:
        result["credentials_warning"] = credentials_warning
    return result


@router.post("/api/dev/clear-sessions")
async def clear_dev_sessions(request: Request):
    if not _auth.is_authenticated(request):
        raise HTTPException(status_code=403, detail="Nicht autorisiert")
    pattern = "/claude-auth/projects/-opt-haana/*.jsonl"
    files = _glob.glob(pattern)
    deleted = []
    errors = []
    for f in files:
        try:
            Path(f).unlink()
            deleted.append(Path(f).name)
        except Exception as exc:
            errors.append(f"{Path(f).name}: {exc}")
    logger.info("dev: %d Session(s) gelöscht: %s", len(deleted), deleted)
    return {"ok": True, "deleted": deleted, "errors": errors}
