"""Claude Auth Management: OAuth login flow, provider-scoped credentials."""

import asyncio
import json
import logging
import os
import pty
import re
import select
import signal
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .deps import (
    load_config, CLAUDE_AUTH_DIR, docker_client, logger,
)
import routers.deps as _deps

router = APIRouter(tags=["claude-auth"])


def _cleanup_oauth_session():
    """Kill any running oauth login process."""
    if _deps.oauth_login_session:
        try:
            os.kill(_deps.oauth_login_session["pid"], signal.SIGKILL)
            os.waitpid(_deps.oauth_login_session["pid"], os.WNOHANG)
        except (ProcessLookupError, ChildProcessError):
            pass
        try:
            os.close(_deps.oauth_login_session["fd"])
        except OSError:
            pass
        _deps.oauth_login_session = None


def _start_oauth_login_sync():
    """Blocking: spawn `claude setup-token`, extract OAuth URL."""
    _cleanup_oauth_session()

    tmp_home = "/tmp/claude-oauth-login"
    import shutil
    if os.path.exists(tmp_home):
        shutil.rmtree(tmp_home)
    os.makedirs(f"{tmp_home}/.claude", exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = tmp_home
    env["CLAUDE_CONFIG_DIR"] = f"{tmp_home}/.claude"
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"

    pid, fd = pty.fork()
    if pid == 0:
        import struct, fcntl, termios
        try:
            winsize = struct.pack("HHHH", 50, 500, 0, 0)
            fcntl.ioctl(1, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass
        for k, v in env.items():
            os.environ[k] = v
        os.execvp("claude", ["claude", "setup-token"])
        os._exit(1)

    import struct, fcntl, termios
    try:
        winsize = struct.pack("HHHH", 50, 500, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass

    output = b""
    end_time = time.time() + 25
    while time.time() < end_time:
        r, _, _ = select.select([fd], [], [], 1)
        if r:
            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                output += data
                if b"prompted" in output or b"Paste" in output:
                    break
            except OSError:
                break

    text = output.decode("utf-8", errors="replace")
    clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
    flat = re.sub(r"[\r\n]+", "", clean)

    url_match = re.search(r"(https://claude\.ai/oauth/authorize[^\s]*)", flat)
    if not url_match:
        _cleanup_oauth_session()
        return {"ok": False, "detail": "Could not extract OAuth URL."}

    auth_url = url_match.group(1)
    state_match = re.search(r"state=([A-Za-z0-9\-_]{43})", auth_url)
    if state_match:
        auth_url = auth_url[:state_match.end()]

    _deps.oauth_login_session = {
        "pid": pid, "fd": fd, "tmp_home": tmp_home,
        "url": auth_url,
    }
    return {"ok": True, "url": auth_url}


def _complete_oauth_login_sync(code: str):
    """Blocking: send authorization code to claude setup-token via PTY stdin."""
    if not _deps.oauth_login_session:
        return {"ok": False, "detail": "No active login session. Start login first."}

    fd = _deps.oauth_login_session["fd"]
    tmp_home = _deps.oauth_login_session["tmp_home"]

    import tty
    try:
        tty.setraw(fd)
    except Exception:
        pass

    try:
        os.write(fd, code.encode("utf-8"))
        time.sleep(0.3)
        os.write(fd, b"\r")
    except OSError as e:
        _cleanup_oauth_session()
        return {"ok": False, "detail": f"Could not send code to CLI: {e}"}

    pty_text = ""
    end_time = time.time() + 30
    while time.time() < end_time:
        try:
            r, _, _ = select.select([fd], [], [], 2)
            if r:
                data = os.read(fd, 8192)
                if not data:
                    break
                pty_text += data.decode("utf-8", errors="replace")
                logger.info(f"setup-token output chunk: {repr(data[:200])}")
                lower = pty_text.lower()
                if "error" in lower or "invalid" in lower or "retry" in lower:
                    time.sleep(1)
                    break
                if "success" in lower or "authenticated" in lower or "logged in" in lower or "token saved" in lower:
                    time.sleep(2)
                    break
        except OSError:
            break

    try:
        r, _, _ = select.select([fd], [], [], 3)
        if r:
            remaining = os.read(fd, 8192)
            if remaining:
                pty_text += remaining.decode("utf-8", errors="replace")
                logger.info(f"setup-token remaining output: {repr(remaining[:200])}")
    except OSError:
        pass

    clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", pty_text)
    clean = re.sub(r"[\r\n]+", " ", clean).strip()

    clean_log = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", pty_text)
    logger.info(f"setup-token full output: {repr(clean_log[:500])}")

    creds_saved = False
    tmp_creds = Path(tmp_home) / ".claude" / ".credentials.json"
    alt_creds_paths = [
        Path(tmp_home) / ".claude" / ".credentials.json",
        Path(tmp_home) / ".claude" / "credentials.json",
        Path(tmp_home) / ".credentials.json",
        CLAUDE_AUTH_DIR / ".credentials.json",
    ]
    for p in alt_creds_paths:
        if p.is_file():
            logger.info(f"setup-token: Found credentials at {p}")
            tmp_creds = p
            break
    else:
        try:
            import subprocess as _sp2
            ls_result = _sp2.run(["find", tmp_home, "-type", "f"], capture_output=True, text=True, timeout=5)
            logger.info(f"setup-token: Files in {tmp_home}: {ls_result.stdout.strip()}")
        except Exception:
            pass

    if tmp_creds.is_file():
        try:
            creds_data = tmp_creds.read_text(encoding="utf-8")
            creds = json.loads(creds_data)
            if creds.get("claudeAiOauth", {}).get("accessToken"):
                CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
                dest = CLAUDE_AUTH_DIR / ".credentials.json"
                dest.write_text(creds_data, encoding="utf-8")
                os.chmod(dest, 0o600)
                import subprocess as _sp
                _sp.run(["chown", "1000:1000", str(dest)], check=False)
                creds_saved = True
                logger.info("setup-token: Credentials in CLAUDE_AUTH_DIR gespeichert")
        except Exception as e:
            logger.error(f"setup-token: Credential copy failed: {e}")

    if creds_saved:
        _cleanup_oauth_session()
        return {"ok": True, "detail": "Login successful. Long-lived token saved."}

    token_match = re.search(r"(sk-ant-[a-zA-Z0-9_-]{20,})", pty_text)
    if token_match:
        token_str = token_match.group(1)
        logger.info(f"setup-token: Found token in stdout output (len={len(token_str)})")
        creds_data = json.dumps({
            "claudeAiOauth": {
                "accessToken": token_str,
                "refreshToken": "",
                "expiresAt": 0,
                "scopes": ["user:inference", "user:profile"],
            }
        })
        try:
            CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
            dest = CLAUDE_AUTH_DIR / ".credentials.json"
            dest.write_text(creds_data, encoding="utf-8")
            os.chmod(dest, 0o600)
            import subprocess as _sp
            _sp.run(["chown", "1000:1000", str(dest)], check=False)
            _cleanup_oauth_session()
            logger.info("setup-token: Token aus stdout in CLAUDE_AUTH_DIR gespeichert")
            return {"ok": True, "detail": "Login successful. Long-lived token saved."}
        except Exception as e:
            logger.error(f"setup-token: Token save failed: {e}")

    _cleanup_oauth_session()

    clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", pty_text)
    clean = re.sub(r"[\r\n]+", " ", clean).strip()
    if "error" in clean.lower() or "invalid" in clean.lower():
        detail = re.sub(r"[^\x20-\x7e]", "", clean).strip()
        detail = re.sub(r" {2,}", " ", detail)[:200]
        return {"ok": False, "detail": f"Login fehlgeschlagen: {detail}"}

    return {"ok": False, "detail": "Credentials nicht gefunden. Bitte Login erneut starten."}


# ── Global Auth Endpoints ────────────────────────────────────────────────────

@router.get("/api/claude-auth/status")
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


@router.post("/api/claude-auth/refresh")
async def claude_auth_refresh():
    """Versucht den OAuth-Token per Refresh-Token zu erneuern."""
    if not docker_client:
        return {"ok": False, "detail": "Docker nicht verfügbar"}
    try:
        containers = docker_client.containers.list(
            filters={"status": "running", "name": "haana-instanz"})
        if not containers:
            return {"ok": False, "detail": "Kein laufender Agent-Container gefunden"}
        container = containers[0]
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
        return {"ok": False, "detail": "Token abgelaufen. Bitte manuell erneuern (siehe Anleitung).",
                "status": status_data}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@router.post("/api/claude-auth/upload")
async def claude_auth_upload(request: Request):
    """Credentials-Datei hochladen."""
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
    creds_file = CLAUDE_AUTH_DIR / ".credentials.json"
    try:
        CLAUDE_AUTH_DIR.mkdir(parents=True, exist_ok=True)
        creds_file.write_text(json.dumps(creds, indent=2), encoding="utf-8")
        os.chmod(creds_file, 0o600)
        import subprocess
        subprocess.run(["chown", "1000:1000", str(creds_file)], check=False)
        return {"ok": True, "detail": "Credentials gespeichert. Container müssen neu gestartet werden."}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}


@router.post("/api/claude-auth/login/start")
async def claude_auth_login_start():
    """Start OAuth login."""
    return await asyncio.to_thread(_start_oauth_login_sync)


@router.post("/api/claude-auth/login/complete")
async def claude_auth_login_complete(request: Request):
    """Complete OAuth login."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return {"ok": False, "detail": "Authorization code missing"}
    return await asyncio.to_thread(_complete_oauth_login_sync, code)


# ── Provider-scoped OAuth Endpoints ──────────────────────────────────────────

@router.get("/api/claude-auth/status/{provider_id}")
async def claude_auth_status_provider(provider_id: str):
    """Prüft OAuth-Credentials für einen Provider."""
    if not re.match(r'^[a-z0-9][a-z0-9-]*$', provider_id):
        raise HTTPException(400, "Ungültige Provider-ID")
    cfg = load_config()
    prov = next((p for p in cfg.get("providers", []) if p["id"] == provider_id), None)
    if prov:
        oauth_dir = Path(prov.get("oauth_dir", f"/data/claude-auth/{provider_id}"))
    else:
        oauth_dir = Path(f"/data/claude-auth/{provider_id}")
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
        if expires_at > 0 and now > expires_at:
            hours_ago = (now - expires_at) / 3600
            return {"ok": False, "status": "expired", "detail": f"Token abgelaufen (vor {hours_ago:.1f}h)"}
        if expires_at > 0:
            hours_left = (expires_at - now) / 3600
            days_left = hours_left / 24
            if days_left > 30:
                return {"ok": True, "status": "valid",
                        "detail": f"Token gültig (noch {days_left:.0f} Tage)",
                        "expires_in_hours": round(hours_left, 1)}
            return {"ok": True, "status": "valid", "detail": f"Token gültig (noch {hours_left:.1f}h)",
                    "expires_in_hours": round(hours_left, 1)}
        return {"ok": True, "status": "valid", "detail": "Token gültig (langlebig)"}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)[:200]}


@router.post("/api/claude-auth/login/start/{provider_id}")
async def claude_auth_login_start_provider(provider_id: str):
    """Start OAuth login for a specific provider."""
    return await asyncio.to_thread(_start_oauth_login_sync)


@router.post("/api/claude-auth/login/complete/{provider_id}")
async def claude_auth_login_complete_provider(provider_id: str, request: Request):
    """Complete OAuth login for a specific provider."""
    if not re.match(r'^[a-z0-9][a-z0-9-]*$', provider_id):
        raise HTTPException(400, "Ungültige Provider-ID")
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return {"ok": False, "detail": "Authorization code missing"}

    result = await asyncio.to_thread(_complete_oauth_login_sync, code)

    cfg = load_config()
    prov = next((p for p in cfg.get("providers", []) if p["id"] == provider_id), None)
    if prov:
        oauth_dir = Path(prov.get("oauth_dir", f"/data/claude-auth/{provider_id}"))
    else:
        oauth_dir = Path(f"/data/claude-auth/{provider_id}")
        logger.warning(f"Provider {provider_id!r} nicht in Config — Credentials in Standard-Pfad: {oauth_dir}")
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
            logger.info(f"OAuth credentials kopiert: {global_creds} -> {dest}")
            return {"ok": True, "detail": "Login erfolgreich. Token gespeichert."}
        except Exception as e:
            logger.error(f"OAuth credential copy failed: {e}")

    return result


@router.post("/api/claude-auth/upload/{provider_id}")
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
