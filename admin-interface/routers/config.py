"""Config-Endpoints: CRUD, references, fetch-models, embeddings, test-connection."""

import re
import time

from fastapi import APIRouter, HTTPException, Request

import auth as _auth
from .deps import (
    load_config, save_config, find_references, find_ollama_url,
    SYSTEM_USER_IDS, INST_DIR,
)

router = APIRouter(tags=["config"])


# ── Config CRUD ──────────────────────────────────────────────────────────────

@router.get("/api/config")
async def get_config():
    return load_config()


@router.post("/api/config")
async def post_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")
    save_config(body)
    return {"ok": True}


@router.get("/api/references/{entity_type}/{entity_id}")
async def get_references(entity_type: str, entity_id: str):
    """Gibt alle Referenzen auf eine Entity (provider/llm) zurück."""
    if entity_type not in ("provider", "llm"):
        raise HTTPException(400, "entity_type muss 'provider' oder 'llm' sein")
    cfg = load_config()
    refs = find_references(entity_type, entity_id, cfg)
    return {"refs": refs, "count": len(refs)}


# ── CLAUDE.md ────────────────────────────────────────────────────────────────

@router.get("/api/claude-md/{instance}")
async def get_claude_md(instance: str):
    from .deps import get_all_instances
    if instance not in get_all_instances():
        raise HTTPException(404, "Instanz nicht gefunden")
    path = INST_DIR / instance / "CLAUDE.md"
    if not path.exists():
        raise HTTPException(404, "CLAUDE.md nicht gefunden")
    return {"content": path.read_text(encoding="utf-8")}


@router.post("/api/claude-md/{instance}")
async def post_claude_md(instance: str, request: Request):
    from .deps import get_all_instances
    if instance not in get_all_instances():
        raise HTTPException(404, "Instanz nicht gefunden")
    try:
        body = await request.json()
        content = body.get("content", "")
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")
    path = INST_DIR / instance / "CLAUDE.md"
    if not path.parent.exists():
        raise HTTPException(404, "Instanz-Verzeichnis nicht gefunden")
    path.write_text(content, encoding="utf-8")
    return {"ok": True}


@router.get("/api/claude-md-template/{template_name}")
async def get_claude_md_template(template_name: str):
    """Liefert den Rohinhalt eines CLAUDE.md-Templates."""
    from .deps import TEMPLATES_DIR
    safe = re.sub(r"[^a-z0-9\-]", "", template_name.lower())
    tpl_path = TEMPLATES_DIR / f"{safe}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "user.md"
    if not tpl_path.exists():
        raise HTTPException(404, "Template nicht gefunden")
    return {"content": tpl_path.read_text(encoding="utf-8"), "template": safe}


# ── Fetch Models ─────────────────────────────────────────────────────────────

@router.post("/api/fetch-models")
async def fetch_models(request: Request):
    """Fragt verfügbare Modelle eines LLM-Providers ab."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    type_ = (body.get("type") or "").strip()
    url = (body.get("url") or "").strip()
    key = (body.get("key") or "").strip()

    _ANTHROPIC_KNOWN = [
        "claude-opus-4-6", "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-5", "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if type_ == "ollama":
                target = url or "http://localhost:11434"
                r = await client.get(f"{target}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return {"models": models}

            elif type_ == "minimax":
                return {"models": ["MiniMax-M2.5", "MiniMax-Text-01"]}

            elif type_ == "anthropic":
                if url and "minimax" in url.lower():
                    return {"models": ["MiniMax-M2.5", "MiniMax-Text-01"]}
                if not key:
                    return {"models": _ANTHROPIC_KNOWN, "fallback": True}
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
                try:
                    r = await client.get("https://api.anthropic.com/v1/models", headers=headers)
                    if r.status_code == 200:
                        models = [m["id"] for m in r.json().get("data", [])]
                        return {"models": models}
                except Exception:
                    pass
                return {"models": _ANTHROPIC_KNOWN, "fallback": True}

            elif type_ == "openai":
                target = url or "https://api.openai.com"
                headers = {"Authorization": f"Bearer {key}"}
                r = await client.get(f"{target}/v1/models", headers=headers)
                if r.status_code == 200:
                    models = sorted([m["id"] for m in r.json().get("data", [])])
                    return {"models": models}
                return {"models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"], "fallback": True}

            elif type_ == "gemini":
                return {"models": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"], "fallback": True}

            else:
                return {"models": [], "manual": True}
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}


# ── Embedding Models ─────────────────────────────────────────────────────────

_OPENAI_EMBEDDINGS = [
    {"id": "text-embedding-3-small", "dims": 1536},
    {"id": "text-embedding-3-large", "dims": 3072},
    {"id": "text-embedding-ada-002", "dims": 1536},
]
_GEMINI_EMBEDDINGS = [
    {"id": "models/gemini-embedding-001", "dims": 3072},
    {"id": "models/text-embedding-004", "dims": 768},
]
_FASTEMBED_MODELS = [
    {"id": "BAAI/bge-small-en-v1.5", "dims": 384, "is_embed": True},
    {"id": "BAAI/bge-m3", "dims": 1024, "is_embed": True},
]
_OLLAMA_EMBED_PATTERN = re.compile(r"embed|bge|minilm|nomic|mxbai|snowflake|arctic", re.I)
_OLLAMA_DIMS = {
    "bge-m3": 1024, "nomic-embed-text": 768, "all-minilm": 384,
    "bge-small-en-v1.5": 384, "mxbai-embed-large": 1024,
    "snowflake-arctic-embed": 1024,
}


@router.post("/api/fetch-embedding-models")
async def fetch_embedding_models(request: Request):
    """Gibt Embedding-Modelle für einen Provider zurück."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    type_ = (body.get("type") or "").strip()
    url = (body.get("url") or "").strip()
    key = (body.get("key") or "").strip()

    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if type_ == "ollama":
                target = url or "http://localhost:11434"
                r = await client.get(f"{target}/api/tags")
                all_models = [m["name"] for m in r.json().get("models", [])]
                embed_models = []
                for m in all_models:
                    base = m.split(":")[0]
                    dims = _OLLAMA_DIMS.get(base, 0)
                    is_embed = bool(_OLLAMA_EMBED_PATTERN.search(m))
                    embed_models.append({"id": m, "dims": dims, "is_embed": is_embed})
                embed_models.sort(key=lambda x: (not x["is_embed"], x["id"]))
                return {"models": embed_models}

            elif type_ == "openai":
                target = url or "https://api.openai.com"
                if key:
                    try:
                        headers = {"Authorization": f"Bearer {key}"}
                        r = await client.get(f"{target}/v1/models", headers=headers)
                        if r.status_code == 200:
                            api_models = [m["id"] for m in r.json().get("data", [])
                                          if "embed" in m["id"].lower()]
                            if api_models:
                                models = []
                                for m in sorted(api_models):
                                    known = next((e for e in _OPENAI_EMBEDDINGS if e["id"] == m), None)
                                    models.append({"id": m, "dims": known["dims"] if known else 0})
                                return {"models": models}
                    except Exception:
                        pass
                return {"models": _OPENAI_EMBEDDINGS, "fallback": True}

            elif type_ == "gemini":
                return {"models": _GEMINI_EMBEDDINGS, "fallback": True}

            elif type_ == "fastembed":
                return {"models": _FASTEMBED_MODELS}

            else:
                return {"models": []}
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}


@router.post("/api/test-embedding")
async def test_embedding(request: Request):
    """Testet ein Embedding-Modell."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    type_ = (body.get("type") or "").strip()
    url = (body.get("url") or "").strip()
    key = (body.get("key") or "").strip()
    model = (body.get("model") or "").strip()

    if not model:
        return {"ok": False, "error": "Kein Modell angegeben"}

    import httpx
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if type_ == "ollama":
                target = url or "http://localhost:11434"
                r = await client.post(f"{target}/api/embed", json={"model": model, "input": "Test embedding"})
                if r.status_code != 200:
                    return {"ok": False, "error": f"Ollama Fehler: {r.status_code} {r.text[:100]}"}
                data = r.json()
                embeddings = data.get("embeddings", [[]])
                dims = len(embeddings[0]) if embeddings and embeddings[0] else 0

            elif type_ == "openai":
                target = url or "https://api.openai.com"
                r = await client.post(
                    f"{target}/v1/embeddings",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "input": "Test embedding"},
                )
                if r.status_code != 200:
                    return {"ok": False, "error": f"OpenAI Fehler: {r.status_code} {r.text[:100]}"}
                data = r.json()
                emb = data.get("data", [{}])[0].get("embedding", [])
                dims = len(emb)

            elif type_ == "gemini":
                api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:embedContent?key={key}"
                r = await client.post(api_url, json={
                    "model": model,
                    "content": {"parts": [{"text": "Test embedding"}]},
                })
                if r.status_code != 200:
                    return {"ok": False, "error": f"Gemini Fehler: {r.status_code} {r.text[:100]}"}
                data = r.json()
                emb = data.get("embedding", {}).get("values", [])
                dims = len(emb)

            elif type_ == "fastembed":
                try:
                    from fastembed import TextEmbedding
                    fe_model = model or "BAAI/bge-small-en-v1.5"
                    embedding_model = TextEmbedding(model_name=fe_model)
                    embeddings = list(embedding_model.embed(["Test embedding"]))
                    dims = len(embeddings[0]) if embeddings else 0
                except ImportError:
                    return {"ok": False, "error": "fastembed nicht installiert"}
                except Exception as fe_err:
                    return {"ok": False, "error": f"FastEmbed Fehler: {str(fe_err)[:100]}"}

            else:
                return {"ok": False, "error": f"Unbekannter Provider-Typ: {type_}"}

            elapsed = int((time.time() - start) * 1000)
            return {"ok": True, "dims": dims, "time_ms": elapsed}

    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── Test-Connection ──────────────────────────────────────────────────────────

@router.post("/api/test-connection")
async def test_connection(request: Request):
    """Testet eine Verbindung zu einem Dienst."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    url = (body.get("url") or "").strip()
    type_ = (body.get("type") or "http").strip()

    if not url:
        raise HTTPException(400, "url fehlt")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if type_ == "qdrant":
                r = await client.get(f"{url}/collections")
                colls = r.json().get("result", {}).get("collections", [])
                return {"ok": True, "detail": f"{len(colls)} Collection(s)"}
            elif type_ == "ollama":
                r = await client.get(f"{url}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                return {"ok": True, "detail": f"{len(models)} Modell(e)"}
            else:
                r = await client.get(url)
                return {"ok": r.status_code < 400, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        if "ConnectError" in type(e).__name__:
            return {"ok": False, "detail": f"Verbindung abgelehnt: {str(e)[:100]}"}
        if "Timeout" in type(e).__name__:
            return {"ok": False, "detail": "Timeout (>5s)"}
        return {"ok": False, "detail": str(e)[:200]}
