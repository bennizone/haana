"""
HAANA Logger – Strukturiertes JSONL-Logging

Kategorien:
  conversations/{instance}/YYYY-MM-DD.jsonl  – vollständige Konversationen
  llm-calls/YYYY-MM-DD.jsonl                 – jeder LLM-Call mit Metriken
  memory-ops/YYYY-MM-DD.jsonl                – Memory-Reads und -Writes
  tool-calls/YYYY-MM-DD.jsonl                – Tool-Aufrufe mit Parametern

Format: JSONL (eine JSON-Zeile pro Event), täglich rotiert, nie gelöscht.
Qdrant kann jederzeit aus den Logs rekonstruiert werden.

Konfiguration:
  HAANA_LOG_DIR – Log-Verzeichnis (Standard: data/logs)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)


def _log_root() -> Path:
    return Path(os.environ.get("HAANA_LOG_DIR", "data/logs"))


def _write(category: str, sub: Optional[str], record: dict) -> None:
    """Schreibt einen Record als JSONL-Zeile (append, thread-safe genug für JSONL)."""
    today = datetime.now().strftime("%Y-%m-%d")
    root = _log_root()
    path = (root / category / sub / f"{today}.jsonl") if sub else (root / category / f"{today}.jsonl")
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        _logger.error(f"[HaanaLogger] Schreiben nach {path} fehlgeschlagen: {e}")


# ── Öffentliche API ───────────────────────────────────────────────────────────

def log_conversation(
    instance: str,
    channel: str,          # "repl" | "webchat" | "whatsapp" | "ha_app"
    user_message: str,
    assistant_response: str,
    latency_s: float,
    memory_used: bool = False,
    memory_hits: int = 0,
    tool_calls: Optional[list[dict]] = None,
    model: Optional[str] = None,
    memory_results: Optional[list[str]] = None,
    memory_extracted: bool = False,
) -> None:
    """Loggt eine vollständige Konversationsrunde."""
    record = {
        "instance": instance,
        "channel": channel,
        "user": user_message,
        "assistant": assistant_response,
        "latency_s": round(latency_s, 3),
        "memory_used": memory_used,
        "memory_hits": memory_hits,
        "tool_calls": tool_calls or [],
    }
    if model:
        record["model"] = model
    if memory_results:
        record["memory_results"] = memory_results
    if memory_extracted:
        record["memory_extracted"] = True
    _write("conversations", instance, record)


def log_memory_op(
    instance: str,
    op: str,               # "read" | "write"
    scope: str,
    query: Optional[str] = None,
    results_count: Optional[int] = None,
    content_preview: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Loggt eine Memory-Read- oder -Write-Operation."""
    _write("memory-ops", None, {
        "instance": instance,
        "op": op,
        "scope": scope,
        "query": query,
        "results_count": results_count,
        "content_preview": (content_preview or "")[:300] or None,
        "success": success,
        "error": error,
    })


def log_tool_call(
    instance: str,
    tool_name: str,
    tool_input: Any,
    latency_s: Optional[float] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Loggt einen Tool-Aufruf."""
    _write("tool-calls", None, {
        "instance": instance,
        "tool": tool_name,
        "input": str(tool_input)[:500] if tool_input is not None else None,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "success": success,
        "error": error,
    })


def list_instances() -> list[str]:
    """Gibt alle Instanzen zurück für die Konversations-Logs existieren."""
    conv_dir = _log_root() / "conversations"
    if not conv_dir.exists():
        return []
    return sorted(p.name for p in conv_dir.iterdir() if p.is_dir())
