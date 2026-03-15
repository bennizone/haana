"""HAANA Dream Process – LLM-, Qdrant- und Vektor-Hilfsfunktionen."""

import logging
from typing import Optional

import httpx
import numpy as np

logger = logging.getLogger(__name__)


# ── LLM-Call Helper ──────────────────────────────────────────────────────────

def _call_llm(
    prompt: str,
    *,
    extract_type: str,
    extract_url: str,
    extract_key: str,
    ollama_url: str,
    model: str,
    timeout: int = 90,
) -> Optional[str]:
    """
    Ruft das konfigurierte Extraction-LLM auf (gleicher Pattern wie HaanaMemory).
    Gibt Antwort als String zurück oder None bei Fehler.
    """
    import requests as req

    try:
        r = None
        if extract_type == "ollama":
            url = extract_url or ollama_url
            if not url:
                return None
            r = req.post(
                f"{url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        elif extract_type in ("anthropic", "minimax"):
            url = extract_url or "https://api.anthropic.com"
            if not extract_key:
                return None
            r = req.post(
                f"{url}/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                    "x-api-key": extract_key,
                },
                json={
                    "model": model,
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            if r.status_code == 200:
                for block in r.json().get("content", []):
                    if block.get("type") == "text":
                        return block.get("text", "").strip()
        elif extract_type == "openai":
            url = extract_url or "https://api.openai.com/v1"
            if not extract_key:
                return None
            r = req.post(
                f"{url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {extract_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        elif extract_type == "gemini":
            if not extract_key:
                return None
            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent?key={extract_key}"
            )
            r = req.post(
                api_url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1},
                },
                timeout=timeout,
            )
            if r.status_code == 200:
                candidates = r.json().get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()

        if r is not None and r.status_code != 200:
            logger.warning(f"Dream LLM HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Dream LLM Fehler: {e}")

    return None


# ── Qdrant Helpers ───────────────────────────────────────────────────────────

def _qdrant_scroll(
    qdrant_url: str,
    collection: str,
    limit: int = 100,
    offset: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    """
    Liest Punkte aus einer Qdrant-Collection via Scroll-API.
    Gibt (points, next_offset) zurück.
    """
    body: dict = {"limit": limit, "with_payload": True, "with_vector": True}
    if offset is not None:
        body["offset"] = offset

    try:
        r = httpx.post(
            f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll",
            json=body,
            timeout=30.0,
        )
        if r.status_code != 200:
            return [], None
        data = r.json().get("result", {})
        points = data.get("points", [])
        next_offset = data.get("next_page_offset")
        return points, next_offset
    except Exception as e:
        logger.warning(f"Qdrant scroll Fehler ({collection}): {e}")
        return [], None


def _qdrant_get_all_points(qdrant_url: str, collection: str) -> list[dict]:
    """Liest alle Punkte einer Collection via paginiertem Scroll."""
    all_points = []
    offset = None
    while True:
        points, next_offset = _qdrant_scroll(qdrant_url, collection, limit=100, offset=offset)
        all_points.extend(points)
        if not next_offset or not points:
            break
        offset = next_offset
    return all_points


def _qdrant_delete_points(qdrant_url: str, collection: str, point_ids: list) -> bool:
    """Löscht Punkte aus einer Qdrant-Collection."""
    if not point_ids:
        return True
    try:
        r = httpx.post(
            f"{qdrant_url.rstrip('/')}/collections/{collection}/points/delete",
            json={"points": point_ids},
            timeout=30.0,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Qdrant delete Fehler ({collection}): {e}")
        return False


def _qdrant_update_payload(
    qdrant_url: str, collection: str, point_id, payload: dict
) -> bool:
    """Aktualisiert das Payload eines Punktes."""
    try:
        r = httpx.post(
            f"{qdrant_url.rstrip('/')}/collections/{collection}/points/payload",
            json={"payload": payload, "points": [point_id]},
            timeout=30.0,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Qdrant update Fehler ({collection}): {e}")
        return False


# ── Cosine Similarity ────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Berechnet Cosine Similarity zwischen zwei Vektoren."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def _find_similar_pairs(
    points: list[dict], threshold: float = 0.9
) -> list[tuple[dict, dict, float]]:
    """
    Findet Paare von Punkten mit Cosine Similarity über dem Threshold.
    Gibt sortierte Liste (höchste Similarity zuerst) zurück.
    """
    pairs = []
    n = len(points)
    if n < 2:
        return pairs

    # Vektoren extrahieren für Batch-Berechnung
    vectors = []
    valid_points = []
    for p in points:
        vec = p.get("vector")
        if vec and isinstance(vec, list) and len(vec) > 0:
            vectors.append(vec)
            valid_points.append(p)

    if len(valid_points) < 2:
        return pairs

    # Matrix-Berechnung für Effizienz
    mat = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normed = mat / norms
    sim_matrix = normed @ normed.T

    for i in range(len(valid_points)):
        for j in range(i + 1, len(valid_points)):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                pairs.append((valid_points[i], valid_points[j], sim))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


# ── Memory-Text Extraktion ───────────────────────────────────────────────────

def _get_memory_text(point: dict) -> str:
    """Extrahiert den Memory-Text aus einem Qdrant-Punkt."""
    payload = point.get("payload", {})
    return payload.get("memory") or payload.get("data", "")
