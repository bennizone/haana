"""
HAANA Admin-Interface – FastAPI Backend

Thin application shell: creates the FastAPI app, configures middleware,
includes all routers, and manages startup/shutdown lifecycle.

All endpoint logic lives in routers/*.py.
"""

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth as _auth

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(__file__))

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

from core.process_manager import detect_mode, create_agent_manager
from core.ollama_compat import create_ollama_router

# Import shared deps and all routers
import routers.deps as _deps
from routers.auth_routes import router as auth_router
from routers.config import router as config_router
from routers.users import router as users_router
from routers.agents import router as agents_router
from routers.memory import router as memory_router
from routers.logs import router as logs_router
from routers.conversations import router as conversations_router
from routers.whatsapp import router as whatsapp_router
from routers.dream import router as dream_router, dream_scheduler
from routers.system import router as system_router
from routers.claude_auth import router as claude_auth_router
from routers.companion import router as companion_router
from routers.ha_services import router as ha_services_router
from routers.setup import router as setup_router

logger = logging.getLogger(__name__)

# ── Betriebsmodus ────────────────────────────────────────────────────────────
_deps.HAANA_MODE = detect_mode()
_deps.docker_client = _docker_client


# ── Log-Retention Cleanup ────────────────────────────────────────────────────

def _cleanup_logs_once():
    """Löscht Log-Dateien die älter als konfigurierte Retention sind."""
    import glob as _glob
    import time
    cfg = _deps.load_config()
    retention: dict = cfg.get("log_retention", {})
    now = time.time()
    deleted = 0
    for category, days in retention.items():
        if days is None:
            continue
        cutoff = now - int(days) * 86400
        pattern = str(_deps.LOG_ROOT / category / "**" / "*.jsonl")
        for fpath in _glob.glob(pattern, recursive=True):
            try:
                if Path(fpath).stat().st_mtime < cutoff:
                    Path(fpath).unlink()
                    deleted += 1
            except Exception:
                pass
    if deleted:
        logger.info(f"[Cleanup] {deleted} Log-Datei(en) gelöscht")


async def _cleanup_loop():
    """Läuft beim Start und dann täglich."""
    _cleanup_logs_once()
    while True:
        await asyncio.sleep(86400)
        _cleanup_logs_once()


async def _autostart_agents():
    """Startet alle konfigurierten User-Agents im Add-on-Modus."""
    cfg = _deps.load_config()
    for user in cfg.get("users", []):
        uid = user.get("id", "")
        if not uid:
            continue
        try:
            result = await _deps.agent_manager.start_agent(user, cfg)
            if result.get("ok"):
                logger.info(f"[Autostart] Agent '{uid}' gestartet")
            else:
                logger.warning(f"[Autostart] Agent '{uid}': {result.get('error', 'unbekannt')}")
        except Exception as e:
            logger.error(f"[Autostart] Agent '{uid}' fehlgeschlagen: {e}")


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    media_dir = Path(os.environ.get("HAANA_MEDIA_DIR", "/media/haana"))
    haana_uid = int(os.environ.get("HAANA_UID", "1000"))
    for subdir in ["logs/conversations", "logs/memory-ops", "logs/dream", "logs/errors"]:
        log_path = media_dir / subdir
        try:
            log_path.mkdir(parents=True, exist_ok=True)
            os.chown(str(log_path), haana_uid, haana_uid)
        except Exception as e:
            logger.warning("[Startup] Log-Verzeichnis konnte nicht erstellt/chown werden: %s — %s", log_path, e)
    logger.info("[Startup] Log-Verzeichnisse in %s initialisiert.", media_dir)

    asyncio.create_task(_cleanup_loop())
    asyncio.create_task(dream_scheduler())
    _deps.sync_rebuild_state()
    _auth.log_startup_info()

    # Skills-Verzeichnis sicherstellen
    _data_skills = Path("/data/skills")
    if not _data_skills.exists():
        _data_skills.mkdir(parents=True, exist_ok=True)
        logger.info("[Startup] /data/skills/ erstellt.")
    else:
        logger.debug("[Startup] /data/skills/ vorhanden (update-resistent)")

    # AgentManager initialisieren
    _deps.agent_manager = create_agent_manager(
        _deps.HAANA_MODE,
        main_app=app,
        docker_client=_docker_client,
        resolve_llm_fn=_deps.resolve_llm,
        find_ollama_url_fn=_deps.find_ollama_url,
    )

    # Ollama-kompatibler Router
    ollama_router = create_ollama_router(
        get_config=_deps.load_config,
        resolve_llm=_deps.resolve_llm,
        find_ollama_url=_deps.find_ollama_url,
        get_agent_url=lambda inst: _deps.agent_manager.agent_url(inst),
    )
    app.include_router(ollama_router)

    # Add-on Modus: Agents automatisch starten
    if _deps.HAANA_MODE == "addon":
        asyncio.create_task(_autostart_agents())

    # System-User INST_DIRs sicherstellen
    _startup_cfg = _deps.load_config()
    for _sys_id in _deps.SYSTEM_USER_IDS:
        _sys_dir = _deps.INST_DIR / _sys_id
        _sys_dir.mkdir(parents=True, exist_ok=True)
        _sys_md = _sys_dir / "CLAUDE.md"
        if not _sys_md.exists():
            _sys_user = next((u for u in _startup_cfg.get("users", []) if u.get("id") == _sys_id), None)
            if _sys_user:
                _content = _deps.render_claude_md(
                    _sys_user.get("claude_md_template", "user"),
                    _sys_user.get("display_name", _sys_id.capitalize()),
                    _sys_id,
                    _sys_user.get("ha_user", _sys_id),
                    _sys_user.get("language", "de"),
                )
                _sys_md.write_text(_content, encoding="utf-8")
                logger.info(f"[Startup] CLAUDE.md für System-User '{_sys_id}' erstellt")
    yield
    # shutdown (nichts nötig)


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="HAANA Admin", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Auth-Middleware ──────────────────────────────────────────────────────────

_AUTH_EXEMPT_PREFIXES = ("/static/", "/ws/", "/api/wa-proxy/", "/api/companion/")
_AUTH_EXEMPT_EXACT = {"/", "/api/auth/login", "/api/auth/logout", "/api/auth/status",
                      "/api/health", "/api/setup-status", "/api/whatsapp-config", "/api/auth/sso",
                      "/api/tags", "/api/chat", "/api/version", "/api/ps", "/api/show"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _AUTH_EXEMPT_EXACT:
            return await call_next(request)

        if any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        # Companion-Token als Auth akzeptieren
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            bearer = auth_header[7:].strip()
            cfg = _deps.load_config()
            companion_token = cfg.get("companion_token", "")
            if companion_token and bearer and secrets.compare_digest(bearer, companion_token):
                return await call_next(request)

        if not _auth.is_authenticated(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "mode": "ingress" if _auth.IS_INGRESS_MODE else "standalone"},
            )

        return await call_next(request)


app.add_middleware(AuthMiddleware)


# ── Include Routers ──────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(config_router)
app.include_router(users_router)
app.include_router(agents_router)
app.include_router(memory_router)
app.include_router(logs_router)
app.include_router(conversations_router)
app.include_router(whatsapp_router)
app.include_router(dream_router)
app.include_router(system_router)
app.include_router(claude_auth_router)
app.include_router(companion_router)
app.include_router(ha_services_router)
app.include_router(setup_router)


# ── HTML ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "instances": _deps.get_all_instances(),
    })
