"""Log-Endpoints: read, download, delete, export, day operations, check-rebuild."""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .deps import (
    load_config, read_recent_logs, get_all_instances, get_agent_url, LOG_ROOT, logger,
)
from .memory import _is_trivial_entry, _clear_rebuild_progress

router = APIRouter(tags=["logs"])

_SCOPE_RE = re.compile(r"^(all|system|conversations(:[a-zA-Z0-9_-]+)?)$")


@router.get("/api/logs/{category}")
async def get_logs(category: str, limit: int = 100):
    valid = {"memory-ops", "tool-calls", "llm-calls"}
    if category not in valid:
        raise HTTPException(400, f"Kategorie muss eine von {valid} sein")
    return read_recent_logs(category, limit=limit)


@router.get("/api/logs-download")
async def download_logs(scope: str = "all"):
    """Erstellt ein ZIP mit Logs."""
    if not _SCOPE_RE.match(scope):
        raise HTTPException(400, "Ungültiger Scope")
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if scope in ("all", "system"):
            for cat in ("memory-ops", "tool-calls", "llm-calls"):
                cat_dir = LOG_ROOT / cat
                if cat_dir.exists():
                    for f in sorted(cat_dir.glob("*.jsonl")):
                        zf.write(f, f"system-logs/{cat}/{f.name}")

        if scope == "all" or scope.startswith("conversations"):
            conv_dir = LOG_ROOT / "conversations"
            if conv_dir.exists():
                inst_filter = scope.split(":", 1)[1] if ":" in scope else None
                for inst_dir in sorted(conv_dir.iterdir()):
                    if not inst_dir.is_dir():
                        continue
                    if inst_filter and inst_dir.name != inst_filter:
                        continue
                    for f in sorted(inst_dir.glob("*.jsonl")):
                        zf.write(f, f"conversations/{inst_dir.name}/{f.name}")

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"haana-logs-{scope.replace(':', '-')}-{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.delete("/api/logs-delete")
async def delete_logs(request: Request):
    """Löscht Logs."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    scope = body.get("scope", "all")
    if not _SCOPE_RE.match(scope):
        raise HTTPException(400, "Ungültiger Scope")
    deleted = 0

    if scope in ("all", "system"):
        for cat in ("memory-ops", "tool-calls", "llm-calls"):
            cat_dir = LOG_ROOT / cat
            if cat_dir.exists():
                for f in cat_dir.glob("*.jsonl"):
                    f.unlink()
                    deleted += 1

    if scope == "all" or scope.startswith("conversations"):
        conv_dir = LOG_ROOT / "conversations"
        if conv_dir.exists():
            inst_filter = scope.split(":", 1)[1] if ":" in scope else None
            for inst_dir in sorted(conv_dir.iterdir()):
                if not inst_dir.is_dir():
                    continue
                if inst_filter and inst_dir.name != inst_filter:
                    continue
                for f in inst_dir.glob("*.jsonl"):
                    f.unlink()
                    deleted += 1
                if not any(inst_dir.iterdir()):
                    inst_dir.rmdir()

            progress_dir = LOG_ROOT / ".rebuild-progress"
            if progress_dir.exists():
                if inst_filter:
                    pf = progress_dir / f"{inst_filter}.json"
                    if pf.exists():
                        pf.unlink()
                elif scope in ("all", "conversations"):
                    for pf in progress_dir.glob("*.json"):
                        pf.unlink()

    logger.info(f"[LogDelete] {deleted} Datei(en) gelöscht (scope={scope})")
    return {"ok": True, "deleted": deleted}


@router.get("/api/logs/export/{instance}")
async def export_user_logs(instance: str):
    """Erstellt ein ZIP aller Konversations-Logs + Dream-Tagebuch einer Instanz."""
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")
    import io
    import zipfile

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        conv_dir = LOG_ROOT / "conversations" / instance
        if conv_dir.exists():
            for f in sorted(conv_dir.glob("*.jsonl")):
                zf.write(f, f"conversations/{instance}/{f.name}")
                file_count += 1

        dream_dir = LOG_ROOT / "dream" / instance
        if dream_dir.exists():
            for f in sorted(dream_dir.glob("*.jsonl")):
                zf.write(f, f"dream/{instance}/{f.name}")
                file_count += 1

        meta = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "instance": instance,
            "file_count": file_count,
        }
        zf.writestr("metadata.json", json.dumps(meta, indent=2))

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"haana-export-{instance}-{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.delete("/api/logs/user/{instance}")
async def delete_user_data(instance: str, confirm: str = ""):
    """Löscht ALLE Logs und Qdrant-Memories für eine Instanz."""
    if confirm != "true":
        raise HTTPException(
            400,
            "Sicherheitsabfrage: ?confirm=true erforderlich.",
        )
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")

    import shutil
    deleted_files = 0
    deleted_dirs: list[str] = []

    conv_dir = LOG_ROOT / "conversations" / instance
    if conv_dir.exists():
        deleted_files += sum(1 for _ in conv_dir.glob("*.jsonl"))
        shutil.rmtree(conv_dir, ignore_errors=True)
        deleted_dirs.append("conversations")

    dream_dir = LOG_ROOT / "dream" / instance
    if dream_dir.exists():
        deleted_files += sum(1 for _ in dream_dir.glob("*.jsonl"))
        shutil.rmtree(dream_dir, ignore_errors=True)
        deleted_dirs.append("dream")

    for cat in ("llm-calls", "tool-calls", "memory-ops"):
        cat_dir = LOG_ROOT / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob("*.jsonl"):
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
                filtered = []
                removed = 0
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("instance") == instance:
                            removed += 1
                            continue
                    except json.JSONDecodeError:
                        pass
                    filtered.append(line)
                if removed > 0:
                    deleted_files += removed
                    if filtered:
                        f.write_text("\n".join(filtered) + "\n", encoding="utf-8")
                    else:
                        f.unlink()
            except Exception:
                pass
        if cat not in deleted_dirs and deleted_files > 0:
            deleted_dirs.append(cat)

    from core.logger import _extraction_index_dir
    idx_file = _extraction_index_dir() / f"{instance}.json"
    if idx_file.exists():
        idx_file.unlink()

    _clear_rebuild_progress(instance)

    deleted_vectors = 0
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    scopes_to_clean = [f"{instance}_memory"]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for scope in scopes_to_clean:
                try:
                    r = await client.delete(f"{qdrant_url}/collections/{scope}")
                    if r.status_code == 200:
                        deleted_vectors += 1
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[LogDelete] Qdrant-Cleanup für '{instance}' fehlgeschlagen: {e}")

    return {
        "ok": True,
        "instance": instance,
        "deleted_files": deleted_files,
        "deleted_categories": deleted_dirs,
        "deleted_qdrant_collections": scopes_to_clean if deleted_vectors > 0 else [],
    }


@router.delete("/api/logs/day/{instance}/{date}")
async def delete_day_log(instance: str, date: str):
    """Löscht die Log-Datei eines bestimmten Tages."""
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(400, "Ungültiges Datumsformat (erwartet YYYY-MM-DD)")

    path = LOG_ROOT / "conversations" / instance / f"{date}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"Keine Log-Datei für {date} gefunden")

    entries = sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    path.unlink()

    from core.logger import _load_extraction_index, _save_extraction_index
    index = _load_extraction_index(instance)
    if date in index:
        del index[date]
        _save_extraction_index(instance, index)

    return {"ok": True, "instance": instance, "date": date, "deleted_entries": entries}


@router.post("/api/logs/rebuild/{instance}/{date}")
async def rebuild_day_memories(instance: str, date: str):
    """Re-extrahiert Memories aus der Log-Datei eines bestimmten Tages."""
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(400, "Ungültiges Datumsformat (erwartet YYYY-MM-DD)")

    path = LOG_ROOT / "conversations" / instance / f"{date}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"Keine Log-Datei für {date} gefunden")

    agent_url = get_agent_url(instance)
    if not agent_url:
        raise HTTPException(503, f"Keine Agent-URL für '{instance}'")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{agent_url}/health")
            if not r.is_success:
                raise HTTPException(503, f"Agent '{instance}' nicht erreichbar")
    except httpx.ConnectError:
        raise HTTPException(503, f"Agent '{instance}' nicht erreichbar")

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if not _is_trivial_entry(rec):
                entries.append(rec)
        except json.JSONDecodeError:
            pass

    if not entries:
        return {"ok": True, "instance": instance, "date": date,
                "total": 0, "detail": "Keine relevanten Einträge"}

    total = len(entries)

    async def _run():
        async with httpx.AsyncClient(timeout=120.0) as client:
            for rec in entries:
                try:
                    await client.post(
                        f"{agent_url}/rebuild-entry",
                        json={
                            "user": rec.get("user", ""),
                            "assistant": rec.get("assistant", ""),
                        },
                    )
                except Exception:
                    pass

            from core.logger import update_extraction_index
            update_extraction_index(instance, date, str(path))

    asyncio.create_task(_run())
    return {"ok": True, "instance": instance, "date": date,
            "total": total, "status": "started"}


@router.post("/api/logs/check-rebuild/{instance}")
async def check_rebuild_changed(instance: str, auto_rebuild: str = ""):
    """Vergleicht Log-Dateien mit dem Extraction-Index."""
    if instance not in get_all_instances():
        raise HTTPException(404, f"Instanz '{instance}' nicht gefunden")

    from core.logger import get_changed_log_files
    changed = get_changed_log_files(instance)

    if not changed:
        return {"ok": True, "instance": instance, "changed": [],
                "total_changed": 0, "auto_rebuild": False}

    do_rebuild = auto_rebuild == "true"
    rebuild_started = 0

    if do_rebuild:
        agent_url = get_agent_url(instance)
        if not agent_url:
            return {"ok": False, "error": f"Keine Agent-URL für '{instance}'",
                    "changed": changed, "total_changed": len(changed)}

        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{agent_url}/health")
                if not r.is_success:
                    return {"ok": False, "error": f"Agent '{instance}' nicht erreichbar",
                            "changed": changed, "total_changed": len(changed)}
        except Exception as e:
            return {"ok": False, "error": f"Agent nicht erreichbar: {str(e)[:100]}",
                    "changed": changed, "total_changed": len(changed)}

        for item in changed:
            date = item["date"]
            fpath = Path(item["path"])
            if not fpath.exists():
                continue

            entries = []
            for line in fpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if not _is_trivial_entry(rec):
                        entries.append(rec)
                except json.JSONDecodeError:
                    pass

            if not entries:
                continue

            async def _rebuild_file(ents, dt, fp, a_url):
                async with httpx.AsyncClient(timeout=120.0) as client:
                    for rec in ents:
                        try:
                            await client.post(
                                f"{a_url}/rebuild-entry",
                                json={
                                    "user": rec.get("user", ""),
                                    "assistant": rec.get("assistant", ""),
                                },
                            )
                        except Exception:
                            pass
                    from core.logger import update_extraction_index
                    update_extraction_index(instance, dt, str(fp))

            asyncio.create_task(_rebuild_file(entries, date, fpath, agent_url))
            rebuild_started += 1

    return {
        "ok": True,
        "instance": instance,
        "changed": changed,
        "total_changed": len(changed),
        "auto_rebuild": do_rebuild,
        "rebuild_started": rebuild_started,
    }
