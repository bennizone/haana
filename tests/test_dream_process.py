"""Tests für core/dream.py – DreamProcess Klasse und run()."""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import core.dream as dream
from core.dream_utils import (
    _qdrant_update_payload,
)


# ── DreamReport ──────────────────────────────────────────────────────────────

def test_dream_report_defaults():
    r = dream.DreamReport(instance="test")
    assert r.instance == "test"
    assert r.consolidated == 0
    assert r.summarized is False
    assert r.cleaned == 0
    assert r.duration_s == 0.0
    assert r.summary == ""
    assert r.errors == []


def test_dream_report_with_values():
    r = dream.DreamReport(
        instance="alice", consolidated=3, summarized=True,
        cleaned=1, duration_s=5.5, summary="Test-Zusammenfassung",
        errors=["ein Fehler"],
    )
    assert r.consolidated == 3
    assert r.errors == ["ein Fehler"]


# ── DreamProcess Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def dream_config():
    return {
        "qdrant_url": "http://qdrant:6333",
        "ollama_url": "http://ollama:11434",
        "extract_type": "ollama",
        "extract_url": "",
        "extract_key": "",
        "model": "test-model",
        "similarity_threshold": 0.9,
    }


@pytest.fixture
def dream_process(dream_config, tmp_path):
    return dream.DreamProcess(dream_config, str(tmp_path))


# ── Konsolidierung ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consolidate_empty_collection(dream_process):
    with patch("core.dream_utils._qdrant_get_all_points", return_value=[]):
        result = await dream_process._consolidate_memories("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_consolidate_single_entry(dream_process):
    with patch("core.dream_utils._qdrant_get_all_points", return_value=[
        {"id": "1", "vector": [1.0], "payload": {"memory": "test"}},
    ]):
        result = await dream_process._consolidate_memories("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_consolidate_similar_entries(dream_process):
    points = [
        {"id": "1", "vector": [1.0, 0.0, 0.5], "payload": {"memory": "Katze heißt Mystique"}},
        {"id": "2", "vector": [1.0, 0.0, 0.5], "payload": {"memory": "Die Katze heißt Mystique"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value="Katze heißt Mystique"), \
         patch("core.dream_utils._qdrant_update_payload", return_value=True) as mock_update, \
         patch("core.dream_utils._qdrant_delete_points", return_value=True) as mock_delete:
        result = await dream_process._consolidate_memories("alice", "alice_memory")

    assert result == 1
    mock_update.assert_called_once()
    mock_delete.assert_called_once_with("http://qdrant:6333", "alice_memory", ["2"])


@pytest.mark.asyncio
async def test_consolidate_dissimilar_entries(dream_process):
    points = [
        {"id": "1", "vector": [1.0, 0.0], "payload": {"memory": "Katze heißt Mystique"}},
        {"id": "2", "vector": [0.0, 1.0], "payload": {"memory": "Lieblingsfarbe ist Blau"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points):
        result = await dream_process._consolidate_memories("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_consolidate_llm_failure(dream_process):
    """LLM-Fehler beim Merge: Eintrag wird übersprungen, kein Crash."""
    points = [
        {"id": "1", "vector": [1.0, 0.0], "payload": {"memory": "A"}},
        {"id": "2", "vector": [1.0, 0.0], "payload": {"memory": "B"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value=None):
        result = await dream_process._consolidate_memories("alice", "alice_memory")
    assert result == 0


# ── Tages-Zusammenfassung ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_summary_no_logs(dream_process):
    result = await dream_process._create_daily_summary("alice", "2024-01-01")
    assert result == ""


@pytest.mark.asyncio
async def test_daily_summary_with_logs(dream_process, tmp_path):
    # Log-Datei anlegen
    log_dir = tmp_path / "conversations" / "alice"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "2024-01-15.jsonl"
    log_file.write_text(
        json.dumps({"user": "Wie ist das Wetter?", "assistant": "Es regnet."}) + "\n"
        + json.dumps({"user": "Danke!", "assistant": "Gerne!"}) + "\n",
        encoding="utf-8",
    )

    with patch.object(dream_process, "_llm_call", return_value="Heute wurde das Wetter besprochen."):
        result = await dream_process._create_daily_summary("alice", "2024-01-15")

    assert result == "Heute wurde das Wetter besprochen."


@pytest.mark.asyncio
async def test_daily_summary_empty_log(dream_process, tmp_path):
    log_dir = tmp_path / "conversations" / "alice"
    log_dir.mkdir(parents=True)
    (log_dir / "2024-01-15.jsonl").write_text("", encoding="utf-8")

    result = await dream_process._create_daily_summary("alice", "2024-01-15")
    assert result == ""


@pytest.mark.asyncio
async def test_daily_summary_default_date(dream_process, tmp_path):
    """Ohne explizites Datum wird heute verwendet."""
    today = time.strftime("%Y-%m-%d")
    log_dir = tmp_path / "conversations" / "alice"
    log_dir.mkdir(parents=True)
    (log_dir / f"{today}.jsonl").write_text(
        json.dumps({"user": "Hallo", "assistant": "Hi!"}) + "\n",
        encoding="utf-8",
    )

    with patch.object(dream_process, "_llm_call", return_value="Begrüßung."):
        result = await dream_process._create_daily_summary("alice")
    assert result == "Begrüßung."


# ── Widerspruchsbereinigung ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_contradictions_none(dream_process):
    """Keine Einträge → 0."""
    with patch("core.dream_utils._qdrant_get_all_points", return_value=[]):
        result = await dream_process._cleanup_contradictions("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_contradictions_no_conflicts(dream_process):
    points = [
        {"id": "1", "vector": [1.0], "payload": {"memory": "Lieblingsfarbe Blau"}},
        {"id": "2", "vector": [0.0], "payload": {"memory": "Katze Mystique"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value="[]"):
        result = await dream_process._cleanup_contradictions("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_contradictions_with_conflict(dream_process):
    points = [
        {"id": "id-1", "vector": [1.0], "payload": {"memory": "trinkt gerne Kaffee"}},
        {"id": "id-2", "vector": [0.0], "payload": {"memory": "trinkt keinen Kaffee"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value='["id-1"]'), \
         patch("core.dream_utils._qdrant_delete_points", return_value=True) as mock_del:
        result = await dream_process._cleanup_contradictions("alice", "alice_memory")

    assert result == 1
    mock_del.assert_called_once_with("http://qdrant:6333", "alice_memory", ["id-1"])


@pytest.mark.asyncio
async def test_cleanup_contradictions_llm_garbage(dream_process):
    """LLM gibt unparsbare Antwort → 0 gelöscht, kein Crash."""
    points = [
        {"id": "1", "vector": [1.0], "payload": {"memory": "A"}},
        {"id": "2", "vector": [0.0], "payload": {"memory": "B"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value="Keine Widersprüche gefunden."):
        result = await dream_process._cleanup_contradictions("alice", "alice_memory")
    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_contradictions_markdown_codeblock(dream_process):
    """LLM gibt JSON in Markdown-Codeblock zurück."""
    points = [
        {"id": "id-x", "vector": [1.0], "payload": {"memory": "A"}},
        {"id": "id-y", "vector": [0.0], "payload": {"memory": "B"}},
    ]
    with patch("core.dream_utils._qdrant_get_all_points", return_value=points), \
         patch.object(dream_process, "_llm_call", return_value='```json\n["id-x"]\n```'), \
         patch("core.dream_utils._qdrant_delete_points", return_value=True):
        result = await dream_process._cleanup_contradictions("alice", "alice_memory")
    assert result == 1


# ── Voller Run ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_run(dream_process):
    """Voller Dream-Run: alle drei Phasen laufen durch."""
    with patch.object(dream_process, "_consolidate_memories", return_value=2), \
         patch.object(dream_process, "_create_daily_summary", return_value="Zusammenfassung."), \
         patch.object(dream_process, "_cleanup_contradictions", return_value=1):
        report = await dream_process.run("alice", "alice_memory")

    assert report.instance == "alice"
    assert report.consolidated == 2
    assert report.summarized is True
    assert report.summary == "Zusammenfassung."
    assert report.cleaned == 1
    assert report.duration_s >= 0
    assert report.errors == []


@pytest.mark.asyncio
async def test_full_run_with_errors(dream_process):
    """Fehler in einer Phase stoppen nicht die anderen."""
    with patch.object(dream_process, "_consolidate_memories", side_effect=RuntimeError("boom")), \
         patch.object(dream_process, "_create_daily_summary", return_value="OK"), \
         patch.object(dream_process, "_cleanup_contradictions", return_value=0):
        report = await dream_process.run("alice", "alice_memory")

    assert report.consolidated == 0
    assert report.summarized is True
    assert len(report.errors) == 1
    assert "boom" in report.errors[0]
