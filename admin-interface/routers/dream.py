"""Dream process endpoints: run, status, logs, config, scheduler."""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from .deps import (
    load_config, get_all_instances, resolve_llm, find_ollama_url,
    LOG_ROOT, DEFAULT_CONFIG, dream_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dream"])


def _build_dream_config(cfg: dict) -> dict:
    """Baut die memory_config dict für DreamProcess aus der HAANA-Konfiguration."""
    dream_cfg = cfg.get("dream", {})
    llm_id = dream_cfg.get("llm") or cfg.get("memory", {}).get("extraction_llm", "")
    llm, provider = resolve_llm(llm_id, cfg)

    return {
        "qdrant_url": cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333"),
        "ollama_url": find_ollama_url(cfg),
        "extract_type": provider.get("type", "ollama"),
        "extract_url": provider.get("url", ""),
        "extract_key": provider.get("key", ""),
        "model": llm.get("model", ""),
        "similarity_threshold": 0.9,
    }


def _load_last_dream_summary(instance: str, before_date: str) -> str:
    """Letzten Dream-Tagebucheintrag vor before_date laden (für Vortagskontext)."""
    dream_dir = LOG_ROOT / "dream" / instance
    if not dream_dir.exists():
        return ""
    files = sorted(f for f in dream_dir.glob("*.jsonl") if f.stem < before_date)
    for fpath in reversed(files):
        try:
            for line in reversed(fpath.read_text(encoding="utf-8").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    summary = entry.get("summary", "")
                    if summary:
                        return summary
                except json.JSONDecodeError:
                    continue
        except Exception:
            continue
    return ""


async def _run_dream(instance: str, cfg: dict, date: str = ""):
    """Führt den Dream-Prozess für eine Instanz aus."""
    from core.dream import DreamProcess

    dream_state[instance] = {"status": "running", "started": time.time()}
    run_date = date or datetime.now().strftime("%Y-%m-%d")
    previous_summary = _load_last_dream_summary(instance, run_date)

    try:
        memory_cfg = _build_dream_config(cfg)
        dream = DreamProcess(memory_cfg, str(LOG_ROOT))

        scopes = cfg.get("dream", {}).get("scopes") or []
        if not scopes:
            scopes = [f"{instance}_memory", "household_memory"]

        t_start = time.monotonic()

        total_consolidated = 0
        total_cleaned = 0
        last_summary = ""
        for scope in scopes:
            report = await dream.run(instance, scope, date=run_date, previous_summary=previous_summary)
            total_consolidated += report.consolidated
            total_cleaned += report.cleaned
            if report.summary:
                last_summary = report.summary

        duration = time.monotonic() - t_start

        if last_summary or total_consolidated > 0 or total_cleaned > 0:
            from core.logger import log_dream_summary
            log_dream_summary(
                instance=instance,
                date=run_date,
                summary=last_summary,
                consolidated=total_consolidated,
                contradictions=total_cleaned,
                duration_s=duration,
            )

        dream_state[instance] = {
            "status": "done",
            "finished": time.time(),
            "report": {
                "summary": last_summary,
                "consolidated": total_consolidated,
                "contradictions": total_cleaned,
                "duration_s": round(duration, 1),
            },
        }
    except Exception as e:
        logger.error(f"Dream-Prozess Fehler für {instance}: {e}", exc_info=True)
        dream_state[instance] = {"status": "error", "error": str(e)[:200]}


async def _catchup_dream(cfg: dict) -> None:
    """Einmaliger Catch-up beim Start: fehlende Dream-Tage der letzten 7 Tage nachholen."""
    dream_cfg = cfg.get("dream", {})
    if not dream_cfg.get("enabled"):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    for user in cfg.get("users", []):
        instance = user.get("id", "")
        if not instance:
            continue
        if dream_state.get(instance, {}).get("catch_up_done"):
            continue

        conv_dir = LOG_ROOT / "conversations" / instance
        conv_dates: set[str] = set()
        if conv_dir.exists():
            for f in conv_dir.glob("*.jsonl"):
                d = f.stem
                if cutoff <= d < today:
                    conv_dates.add(d)

        dream_dir = LOG_ROOT / "dream" / instance
        dream_dates: set[str] = set()
        if dream_dir.exists():
            for f in dream_dir.glob("*.jsonl"):
                dream_dates.add(f.stem)

        missing = sorted(conv_dates - dream_dates)
        if missing:
            logger.info(f"[Dream] Catch-up für {instance}: {len(missing)} fehlende Tage → {missing}")

        for missing_date in missing:
            try:
                await _run_dream(instance, cfg, date=missing_date)
            except Exception as e:
                logger.warning(f"[Dream] Catch-up fehlgeschlagen für {instance}/{missing_date}: {e}")

        state = dream_state.get(instance, {})
        state["catch_up_done"] = True
        dream_state[instance] = state


async def dream_scheduler():
    """Prüft minütlich ob es Zeit für den Dream-Prozess ist."""
    # Einmaliger Catch-up beim Start
    try:
        startup_cfg = load_config()
        await _catchup_dream(startup_cfg)
    except Exception as e:
        logger.warning(f"[Dream] Catch-up beim Start fehlgeschlagen: {e}")

    while True:
        await asyncio.sleep(60)
        cfg = load_config()
        dream_cfg = cfg.get("dream", {})
        if not dream_cfg.get("enabled"):
            continue

        now = datetime.now()
        schedule = dream_cfg.get("schedule", "02:00")
        try:
            hour, minute = map(int, schedule.split(":"))
        except (ValueError, AttributeError):
            continue

        if now.hour == hour and now.minute == minute:
            for user in cfg.get("users", []):
                instance = user["id"]
                if dream_state.get(instance, {}).get("status") != "running":
                    asyncio.create_task(_run_dream(instance, cfg))
            await asyncio.sleep(61)


@router.post("/api/dream/run/{instance}")
async def dream_run(instance: str, request: Request):
    """Dream-Prozess sofort triggern."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    if dream_state.get(instance, {}).get("status") == "running":
        return {"ok": False, "error": "Dream-Prozess läuft bereits"}

    params = dict(request.query_params)
    date = params.get("date", "")
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(400, "Ungültiges Datumsformat (erwartet: YYYY-MM-DD)")

    cfg = load_config()
    asyncio.create_task(_run_dream(instance, cfg, date=date))
    return {"ok": True, "status": "started"}


@router.get("/api/dream/status/{instance}")
async def dream_status_endpoint(instance: str):
    """Aktuellen Dream-Status abfragen."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    state = dream_state.get(instance, {"status": "idle"})
    result = {"status": state.get("status", "idle")}

    if "finished" in state:
        result["last_run"] = datetime.fromtimestamp(
            state["finished"], tz=timezone.utc
        ).isoformat()
    if "report" in state:
        result["report"] = state["report"]
    if "error" in state:
        result["error"] = state["error"]

    return result


@router.get("/api/dream/logs/{instance}")
async def dream_logs(instance: str, request: Request):
    """Dream-Tagebuch-Einträge lesen."""
    if instance not in get_all_instances():
        raise HTTPException(404)

    params = dict(request.query_params)
    date_filter = params.get("date", "")
    try:
        limit = int(params.get("limit", "30"))
    except (ValueError, TypeError):
        limit = 30

    dream_dir = LOG_ROOT / "dream" / instance

    if not dream_dir.exists():
        return []

    records: list[dict] = []

    if date_filter:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_filter):
            raise HTTPException(400, "Ungültiges Datumsformat")
        fpath = dream_dir / f"{date_filter}.jsonl"
        if fpath.exists():
            for line in fpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    else:
        files = sorted(dream_dir.glob("*.jsonl"), reverse=True)
        for fpath in files:
            try:
                lines = fpath.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break

    return records[:limit]


@router.get("/api/dream/config")
async def dream_config():
    """Dream-Konfiguration lesen."""
    cfg = load_config()
    return cfg.get("dream", DEFAULT_CONFIG["dream"])
