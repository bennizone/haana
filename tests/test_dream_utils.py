"""Tests für core/dream_utils.py – Hilfsfunktionen des Dream Process."""
import pytest
from unittest.mock import patch, MagicMock

from core.dream_utils import (
    _cosine_similarity,
    _find_similar_pairs,
    _get_memory_text,
    _call_llm,
    _qdrant_scroll,
    _qdrant_get_all_points,
    _qdrant_delete_points,
    _qdrant_update_payload,
)


# ── Cosine Similarity ────────────────────────────────────────────────────────

def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.5]
    assert _cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_similarity_zero_vector():
    assert _cosine_similarity([0, 0], [1, 1]) == 0.0


# ── Find Similar Pairs ──────────────────────────────────────────────────────

def test_find_similar_pairs_identical():
    points = [
        {"id": "a", "vector": [1.0, 0.0, 0.5], "payload": {"memory": "Fakt A"}},
        {"id": "b", "vector": [1.0, 0.0, 0.5], "payload": {"memory": "Fakt B"}},
    ]
    pairs = _find_similar_pairs(points, threshold=0.9)
    assert len(pairs) == 1
    assert pairs[0][2] == pytest.approx(1.0, abs=1e-6)


def test_find_similar_pairs_below_threshold():
    points = [
        {"id": "a", "vector": [1.0, 0.0], "payload": {"memory": "A"}},
        {"id": "b", "vector": [0.0, 1.0], "payload": {"memory": "B"}},
    ]
    pairs = _find_similar_pairs(points, threshold=0.9)
    assert len(pairs) == 0


def test_find_similar_pairs_empty():
    assert _find_similar_pairs([], threshold=0.9) == []
    assert _find_similar_pairs([{"id": "a", "vector": [1.0]}], threshold=0.9) == []


def test_find_similar_pairs_no_vector():
    points = [
        {"id": "a", "payload": {"memory": "A"}},
        {"id": "b", "payload": {"memory": "B"}},
    ]
    pairs = _find_similar_pairs(points, threshold=0.5)
    assert len(pairs) == 0


def test_find_similar_pairs_sorted_by_similarity():
    """Paare sind nach Similarity absteigend sortiert."""
    points = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "payload": {}},
        {"id": "b", "vector": [1.0, 0.0, 0.0], "payload": {}},  # identical to a
        {"id": "c", "vector": [0.95, 0.31, 0.0], "payload": {}},  # similar to a
    ]
    pairs = _find_similar_pairs(points, threshold=0.5)
    assert len(pairs) >= 2
    # Höchste Similarity (1.0) zuerst
    assert pairs[0][2] >= pairs[1][2]


# ── _get_memory_text ─────────────────────────────────────────────────────────

def test_get_memory_text_memory_field():
    p = {"payload": {"memory": "Katze heißt Mystique"}}
    assert _get_memory_text(p) == "Katze heißt Mystique"


def test_get_memory_text_data_field():
    p = {"payload": {"data": "Fallback-Text"}}
    assert _get_memory_text(p) == "Fallback-Text"


def test_get_memory_text_empty():
    assert _get_memory_text({"payload": {}}) == ""
    assert _get_memory_text({}) == ""


# ── Qdrant Helpers (gemockt) ────────────────────────────────────────────────

def test_qdrant_scroll_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "points": [
                {"id": "1", "vector": [1.0], "payload": {"memory": "test"}},
            ],
            "next_page_offset": None,
        }
    }
    with patch("core.dream_utils.httpx.post", return_value=mock_response):
        points, next_offset = _qdrant_scroll("http://qdrant:6333", "test_memory")
    assert len(points) == 1
    assert next_offset is None


def test_qdrant_scroll_error():
    mock_response = MagicMock()
    mock_response.status_code = 500
    with patch("core.dream_utils.httpx.post", return_value=mock_response):
        points, next_offset = _qdrant_scroll("http://qdrant:6333", "test_memory")
    assert points == []
    assert next_offset is None


def test_qdrant_scroll_exception():
    with patch("core.dream_utils.httpx.post", side_effect=Exception("conn error")):
        points, next_offset = _qdrant_scroll("http://qdrant:6333", "test_memory")
    assert points == []


def test_qdrant_get_all_points_pagination():
    """Testet paginiertes Scroll über mehrere Seiten."""
    call_count = 0

    def mock_scroll(url, collection, limit=100, offset=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{"id": "1", "vector": [1.0], "payload": {}}], "next_1"
        else:
            return [{"id": "2", "vector": [1.0], "payload": {}}], None

    with patch("core.dream_utils._qdrant_scroll", side_effect=mock_scroll):
        points = _qdrant_get_all_points("http://qdrant:6333", "test_memory")
    assert len(points) == 2
    assert call_count == 2


def test_qdrant_delete_points_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("core.dream_utils.httpx.post", return_value=mock_response):
        assert _qdrant_delete_points("http://qdrant:6333", "test", ["id1"]) is True


def test_qdrant_delete_points_empty():
    assert _qdrant_delete_points("http://qdrant:6333", "test", []) is True


def test_qdrant_update_payload_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("core.dream_utils.httpx.post", return_value=mock_response):
        result = _qdrant_update_payload(
            "http://qdrant:6333", "test", "id1", {"memory": "updated"}
        )
    assert result is True


# ── _call_llm ────────────────────────────────────────────────────────────────

def test_call_llm_ollama():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Merged fact"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = _call_llm(
            "merge these",
            extract_type="ollama",
            extract_url="",
            extract_key="",
            ollama_url="http://ollama:11434",
            model="test-model",
        )
    assert result == "Merged fact"
    mock_post.assert_called_once()


def test_call_llm_no_url():
    result = _call_llm(
        "test",
        extract_type="ollama",
        extract_url="",
        extract_key="",
        ollama_url="",
        model="test",
    )
    assert result is None


def test_call_llm_exception():
    with patch("requests.post", side_effect=Exception("timeout")):
        result = _call_llm(
            "test",
            extract_type="ollama",
            extract_url="",
            extract_key="",
            ollama_url="http://ollama:11434",
            model="test",
        )
    assert result is None
