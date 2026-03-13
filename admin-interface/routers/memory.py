"""Memory-Endpoints: stats, rebuild, scan, progress."""

import asyncio
import json
import re
import time
import glob as _glob
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .deps import (
    load_config, get_all_instances, get_agent_url,
    LOG_ROOT, rebuild_state,
)

router = APIRouter(tags=["memory"])


@router.get("/api/memory-stats")
async def memory_stats():
    """Liefert pro Instanz: Konversations-Logs (Zeilen), Qdrant-Vektoren pro Scope."""
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")

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

    _READ_ONLY_TEMPLATES = {"ha-assist"}

    result = []
    for inst in get_all_instances():
        user = next((u for u in cfg.get("users", []) if u["id"] == inst), None)
        if user and user.get("claude_md_template", "") in _READ_ONLY_TEMPLATES:
            continue

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

        scopes: dict[str, int] = {}
        if user:
            tpl = user.get("claude_md_template", "")
            if tpl == "ha-advanced":
                scopes["household_memory"] = coll_vectors.get("household_memory", 0)
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


# ── Rebuild helpers ──────────────────────────────────────────────────────────

def _is_trivial_entry(rec: dict) -> bool:
    """Prüft ob ein Konversations-Eintrag trivial ist."""
    user_msg = (rec.get("user") or "").strip()
    asst_msg = (rec.get("assistant") or "").strip()
    if not user_msg and not asst_msg:
        return True
    if len(user_msg) < 15 and not asst_msg:
        return True
    _trivial_patterns = [
        r"^(hallo|hi|hey|moin|guten (morgen|tag|abend)|tschüss|bye|danke|ok|ja|nein|stop|abbrechen)\.?!?$",
        r"^(licht|lampe|rollo|jalousie|heizung|temperatur|status|wetter)\b.{0,30}$",
        r"^(schalte|mach|stell|dreh|öffne|schließe)\b.{0,40}$",
    ]
    lower = user_msg.lower()
    for pat in _trivial_patterns:
        if re.match(pat, lower):
            return True
    return False


def _scan_rebuild_entries(instance: str, skip_trivial: bool = True) -> dict:
    """Scannt Logs und gibt Statistiken + gefilterte Einträge zurück."""
    conv_files = sorted(
        _glob.glob(str(LOG_ROOT / "conversations" / instance / "*.jsonl"))
    )
    total_raw = 0
    total_filtered = 0
    entries = []

    for fpath in conv_files:
        if not Path(fpath).exists():
            continue
        lines = Path(fpath).read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            total_raw += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skip_trivial and _is_trivial_entry(rec):
                total_filtered += 1
                continue
            entries.append((fpath, i, rec))

    return {
        "total_raw": total_raw,
        "total_filtered": total_filtered,
        "total_relevant": len(entries),
        "entries": entries,
        "files": conv_files,
    }


# Persistenter Rebuild-Progress
_REBUILD_PROGRESS_DIR = LOG_ROOT / ".rebuild-progress"


def _load_rebuild_progress(instance: str) -> dict | None:
    pfile = _REBUILD_PROGRESS_DIR / f"{instance}.json"
    if pfile.exists():
        try:
            return json.loads(pfile.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_rebuild_progress(instance: str, progress: dict):
    _REBUILD_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    pfile = _REBUILD_PROGRESS_DIR / f"{instance}.json"
    pfile.write_text(json.dumps(progress), encoding="utf-8")


def _clear_rebuild_progress(instance: str):
    pfile = _REBUILD_PROGRESS_DIR / f"{instance}.json"
    if pfile.exists():
        pfile.unlink()


@router.post("/api/rebuild-scan/{instance}")
async def rebuild_scan(instance: str, request: Request):
    """Scannt Logs und gibt Statistiken zurück."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    try:
        body = await request.json()
    except Exception:
        body = {}
    skip_trivial = body.get("skip_trivial", True)

    scan = _scan_rebuild_entries(instance, skip_trivial=skip_trivial)
    est_tokens = scan["total_relevant"] * 150
    cfg = load_config()
    mem_cfg = cfg.get("memory", {})
    extract_llm_id = mem_cfg.get("extraction_llm", "")
    provider_type = "ollama"
    for llm in cfg.get("llms", []):
        if llm.get("id") == extract_llm_id:
            for prov in cfg.get("providers", []):
                if prov.get("id") == llm.get("provider_id"):
                    provider_type = prov.get("type", "ollama")
            break

    return {
        "total_raw": scan["total_raw"],
        "total_filtered": scan["total_filtered"],
        "total_relevant": scan["total_relevant"],
        "est_tokens": est_tokens,
        "provider_type": provider_type,
        "is_api": provider_type not in ("ollama",),
    }


@router.post("/api/rebuild-memory/{instance}")
async def start_rebuild(instance: str, request: Request):
    """Startet den Memory-Rebuild."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    state = rebuild_state.get(instance)
    if state and state["status"] == "running":
        return {"ok": False, "error": "Rebuild läuft bereits"}

    try:
        body = await request.json()
    except Exception:
        body = {}
    skip_trivial = body.get("skip_trivial", True)
    try:
        delay_ms = max(0, min(5000, int(body.get("delay_ms", 0))))
    except (ValueError, TypeError):
        delay_ms = 0
    resume = body.get("resume", False)

    scan = _scan_rebuild_entries(instance, skip_trivial=skip_trivial)
    entries = scan["entries"]

    if not entries:
        return {"ok": False, "error": "Keine relevanten Konversations-Logs gefunden"}

    resume_from = 0
    if resume:
        progress = _load_rebuild_progress(instance)
        if progress:
            resume_from = progress.get("processed", 0)

    if resume_from >= len(entries):
        _clear_rebuild_progress(instance)
        return {"ok": False, "error": "Rebuild bereits abgeschlossen"}

    agent_url = get_agent_url(instance)
    import httpx as _httpx_pre
    try:
        async with _httpx_pre.AsyncClient(timeout=5.0) as _c:
            _r = await _c.get(f"{agent_url}/health")
            if not _r.is_success:
                return {"ok": False, "error": f"Agent '{instance}' antwortet nicht (Health-Check fehlgeschlagen). Container läuft?"}
    except Exception as _e:
        return {"ok": False, "error": f"Agent '{instance}' nicht erreichbar: {str(_e)[:120]}. Container läuft?"}

    total = len(entries) - resume_from
    rebuild_state[instance] = {
        "status": "running", "done": 0, "total": total, "errors": 0,
        "started": time.time(), "error": "",
        "skipped_trivial": scan["total_filtered"],
        "resumed_from": resume_from,
    }

    async def _run():
        _state = rebuild_state[instance]
        import httpx
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for idx in range(resume_from, len(entries)):
                    if _state["status"] == "cancelled":
                        _save_rebuild_progress(instance, {
                            "processed": resume_from + _state["done"],
                            "total_entries": len(entries),
                            "paused_at": time.time(),
                        })
                        return
                    _fpath, _line_idx, rec = entries[idx]
                    try:
                        r = await client.post(
                            f"{agent_url}/rebuild-entry",
                            json={
                                "user": rec.get("user", ""),
                                "assistant": rec.get("assistant", ""),
                            },
                        )
                        if not r.is_success:
                            _state["errors"] += 1
                    except Exception:
                        _state["errors"] += 1
                    _state["done"] += 1
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000.0)
            _state["status"] = "done"
            _clear_rebuild_progress(instance)
        except Exception as e:
            _state["status"] = "error"
            _state["error"] = str(e)[:200]
            _save_rebuild_progress(instance, {
                "processed": resume_from + _state["done"],
                "total_entries": len(entries),
                "error": str(e)[:200],
                "paused_at": time.time(),
            })

    asyncio.create_task(_run())
    return {"ok": True, "total": total, "skipped_trivial": scan["total_filtered"], "resumed_from": resume_from}


@router.post("/api/rebuild-cancel/{instance}")
async def cancel_rebuild(instance: str):
    """Pausiert/bricht einen laufenden Rebuild ab."""
    state = rebuild_state.get(instance)
    if state and state["status"] == "running":
        state["status"] = "cancelled"
        return {"ok": True}
    return {"ok": False, "error": "Kein laufender Rebuild"}


@router.delete("/api/rebuild-progress/{instance}")
async def discard_rebuild_progress(instance: str):
    """Verwirft gespeicherten Rebuild-Fortschritt."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    _clear_rebuild_progress(instance)
    return {"ok": True}


@router.get("/api/rebuild-resume-info/{instance}")
async def rebuild_resume_info(instance: str):
    """Gibt Info über gespeicherten Rebuild-Fortschritt zurück."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    progress = _load_rebuild_progress(instance)
    if not progress:
        return {"has_progress": False}
    return {
        "has_progress": True,
        "processed": progress.get("processed", 0),
        "total_entries": progress.get("total_entries", 0),
        "paused_at": progress.get("paused_at"),
        "error": progress.get("error", ""),
    }


@router.get("/api/rebuild-progress/{instance}")
async def rebuild_progress(instance: str, request: Request):
    """SSE-Stream mit Rebuild-Fortschritt."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            state = rebuild_state.get(instance, {})
            done = state.get("done", 0)
            total = state.get("total", 0)
            status = state.get("status", "idle")
            elapsed = time.time() - state.get("started", time.time())
            eta_s = int((total - done) * (elapsed / done)) if done > 0 else None
            yield f"data: {json.dumps({'done': done, 'total': total, 'status': status, 'eta_s': eta_s, 'error': state.get('error', ''), 'errors': state.get('errors', 0), 'skipped_trivial': state.get('skipped_trivial', 0)})}\n\n"
            if status in ("done", "error", "idle", "cancelled"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
