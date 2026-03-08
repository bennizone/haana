"""Tests fuer core/ollama_compat.py – Universeller LLM-Proxy mit Tool-Support."""
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

_root_path = str(Path("/opt/haana"))
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

from core.ollama_compat import (
    create_ollama_router, _text_response, _strip_tag,
    _extract_messages, _ollama_tools_to_anthropic,
    _ollama_msgs_to_anthropic, _anthropic_response_to_ollama,
    _openai_response_to_ollama, _raw_response,
)


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Hilfsfunktionen
# ══════════════════════════════════════════════════════════════════════════════

def test_strip_tag_latest():
    assert _strip_tag("ha-assist:latest") == "ha-assist"

def test_strip_tag_version():
    assert _strip_tag("ha-assist:v1.0") == "ha-assist"

def test_strip_tag_no_tag():
    assert _strip_tag("ha-assist") == "ha-assist"

def test_strip_tag_empty():
    assert _strip_tag("") == ""


def test_extract_messages_basic():
    msgs = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Erste Frage"},
        {"role": "assistant", "content": "Antwort"},
        {"role": "user", "content": "Zweite Frage"},
    ]
    system, user = _extract_messages(msgs)
    assert system == "System prompt"
    assert user == "Zweite Frage"

def test_extract_messages_no_system():
    msgs = [{"role": "user", "content": "Hallo"}]
    system, user = _extract_messages(msgs)
    assert system == ""
    assert user == "Hallo"

def test_extract_messages_empty():
    system, user = _extract_messages([])
    assert system == ""
    assert user == ""


def test_single_response_structure():
    resp = _text_response("Hallo Welt", "ha-assist:latest", 1.5)
    assert resp["model"] == "ha-assist:latest"
    assert resp["done"] is True
    assert resp["done_reason"] == "stop"
    assert resp["message"]["role"] == "assistant"
    assert resp["message"]["content"] == "Hallo Welt"
    assert resp["total_duration"] == 1_500_000_000
    assert resp["eval_count"] == 2

def test_single_response_empty():
    resp = _text_response("", "test:latest", 0.0)
    assert resp["message"]["content"] == ""
    assert resp["done"] is True
    assert resp["eval_count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Tool-Format-Übersetzung
# ══════════════════════════════════════════════════════════════════════════════

def test_ollama_tools_to_anthropic():
    """Ollama/OpenAI Tool-Definitionen → Anthropic Format."""
    tools = [{
        "function": {
            "name": "GetLiveContext",
            "description": "Get current state",
            "parameters": {
                "type": "object",
                "properties": {"area": {"type": "string"}},
            },
        },
    }]
    result = _ollama_tools_to_anthropic(tools)
    assert len(result) == 1
    assert result[0]["name"] == "GetLiveContext"
    assert result[0]["description"] == "Get current state"
    assert result[0]["input_schema"]["properties"]["area"]["type"] == "string"


def test_ollama_tools_to_anthropic_flat():
    """Tools ohne 'function' Wrapper (flaches Format)."""
    tools = [{
        "name": "HassTurnOn",
        "description": "Turn on entity",
        "parameters": {"type": "object", "properties": {}},
    }]
    result = _ollama_tools_to_anthropic(tools)
    assert result[0]["name"] == "HassTurnOn"


def test_ollama_msgs_to_anthropic_basic():
    """System wird extrahiert, User/Assistant bleiben erhalten."""
    msgs = [
        {"role": "system", "content": "You are a helper"},
        {"role": "user", "content": "Licht an"},
        {"role": "assistant", "content": "OK"},
    ]
    system, api_msgs = _ollama_msgs_to_anthropic(msgs)
    assert system == "You are a helper"
    assert len(api_msgs) == 2
    assert api_msgs[0] == {"role": "user", "content": "Licht an"}
    assert api_msgs[1]["role"] == "assistant"
    assert api_msgs[1]["content"][0]["type"] == "text"
    assert api_msgs[1]["content"][0]["text"] == "OK"


def test_ollama_msgs_to_anthropic_tool_calls():
    """Assistant mit tool_calls → Anthropic tool_use Blöcke."""
    msgs = [
        {"role": "user", "content": "Status"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_123",
            "function": {"name": "GetLiveContext", "arguments": '{"area": "wohnzimmer"}'},
        }]},
    ]
    _, api_msgs = _ollama_msgs_to_anthropic(msgs)
    assert len(api_msgs) == 2
    asst = api_msgs[1]
    assert asst["role"] == "assistant"
    tool_use = [b for b in asst["content"] if b["type"] == "tool_use"]
    assert len(tool_use) == 1
    assert tool_use[0]["name"] == "GetLiveContext"
    assert tool_use[0]["input"] == {"area": "wohnzimmer"}
    assert tool_use[0]["id"] == "call_123"


def test_ollama_msgs_to_anthropic_tool_result():
    """Tool-Result → Anthropic user message mit tool_result Block."""
    msgs = [
        {"role": "user", "content": "Status"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_abc",
            "function": {"name": "GetLiveContext", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "call_abc", "content": "Temp: 21°C"},
    ]
    _, api_msgs = _ollama_msgs_to_anthropic(msgs)
    assert len(api_msgs) == 3
    tool_result_msg = api_msgs[2]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "call_abc"
    assert tool_result_msg["content"][0]["content"] == "Temp: 21°C"


def test_ollama_msgs_to_anthropic_tool_result_infers_id():
    """Tool-Result ohne tool_call_id → ID aus letzter Assistant-Message."""
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "inferred_id",
            "function": {"name": "Test", "arguments": "{}"},
        }]},
        {"role": "tool", "content": "result data"},
    ]
    _, api_msgs = _ollama_msgs_to_anthropic(msgs)
    assert api_msgs[1]["content"][0]["tool_use_id"] == "inferred_id"


def test_anthropic_response_to_ollama_text():
    """Anthropic text response → Ollama Format."""
    data = {
        "content": [{"type": "text", "text": "Licht ist an."}],
        "stop_reason": "end_turn",
    }
    result = _anthropic_response_to_ollama(data, "ha-assist")
    assert result["message"]["content"] == "Licht ist an."
    assert result["done"] is True
    assert result["done_reason"] == "stop"
    assert "tool_calls" not in result["message"]


def test_anthropic_response_to_ollama_tool_use():
    """Anthropic tool_use response → Ollama Format mit tool_calls."""
    data = {
        "content": [
            {"type": "text", "text": "Checking..."},
            {"type": "tool_use", "id": "tu_123", "name": "GetLiveContext",
             "input": {"area": "wohnzimmer"}},
        ],
        "stop_reason": "tool_use",
    }
    result = _anthropic_response_to_ollama(data, "ha-assist")
    assert result["message"]["content"] == "Checking..."
    assert len(result["message"]["tool_calls"]) == 1
    tc = result["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "GetLiveContext"
    assert json.loads(tc["function"]["arguments"]) == {"area": "wohnzimmer"}
    assert result["done"] is False
    assert result["done_reason"] == "tool_calls"


def test_openai_response_to_ollama_text():
    """OpenAI text response → Ollama Format."""
    data = {
        "choices": [{"message": {"content": "Hallo"}, "finish_reason": "stop"}],
    }
    result = _openai_response_to_ollama(data, "test-model")
    assert result["message"]["content"] == "Hallo"
    assert result["done"] is True


def test_openai_response_to_ollama_tool_calls():
    """OpenAI tool_calls response → Ollama Format."""
    data = {
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": "call_xyz",
                    "function": {"name": "HassTurnOn", "arguments": '{"entity_id": "light.wohnzimmer"}'},
                }],
            },
            "finish_reason": "tool_calls",
        }],
    }
    result = _openai_response_to_ollama(data, "test-model")
    assert result["message"]["content"] == ""
    assert len(result["message"]["tool_calls"]) == 1
    assert result["done"] is False


def test_raw_response_adds_timing():
    """_raw_response ergänzt Timing-Felder."""
    resp = {"model": "test", "message": {"content": "Hello World"}, "done": True}
    result = _raw_response(resp, 2.5)
    assert result["total_duration"] == 2_500_000_000
    assert result["eval_count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Router-Erstellung und Endpoints
# ══════════════════════════════════════════════════════════════════════════════

_USERS = [
    {"id": "ha-assist", "primary_llm": "ollama-ministral"},
    {"id": "ha-advanced", "primary_llm": "ollama-ministral"},
]
_LLMS = [
    {"id": "ollama-ministral", "provider_id": "ollama-home", "model": "ministral-3-32k:3b"},
]
_PROVIDERS = [
    {"id": "ollama-home", "type": "ollama", "url": "http://localhost:11434", "key": ""},
]


@pytest.fixture
def config_enabled():
    return {
        "ollama_compat": {"enabled": True, "exposed_models": ["ha-assist", "ha-advanced"]},
        "users": list(_USERS),
        "llms": list(_LLMS),
        "providers": list(_PROVIDERS),
    }


@pytest.fixture
def config_disabled():
    return {
        "ollama_compat": {"enabled": False, "exposed_models": []},
        "users": list(_USERS),
        "llms": list(_LLMS),
        "providers": list(_PROVIDERS),
    }


def _resolve_llm(llm_id, cfg):
    llm = next((l for l in cfg.get("llms", []) if l["id"] == llm_id), {})
    if not llm:
        return {}, {}
    prov = next((p for p in cfg.get("providers", []) if p["id"] == llm.get("provider_id")), {})
    return llm, prov


@pytest.fixture
def app_with_router(config_enabled):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda cfg: "http://localhost:11434",
    )
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def app_disabled(config_disabled):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_disabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda cfg: "",
    )
    app.include_router(router)
    return TestClient(app)


# ── GET /api/tags ────────────────────────────────────────────────────────────

def test_tags_returns_models(app_with_router):
    resp = app_with_router.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) == 2
    names = [m["name"] for m in data["models"]]
    assert "ha-assist:latest" in names
    assert "ha-advanced:latest" in names


def test_tags_disabled_returns_empty(app_disabled):
    resp = app_disabled.get("/api/tags")
    assert resp.status_code == 200
    assert resp.json()["models"] == []


def test_tags_no_llm_configured():
    """User ohne LLM-Config wird nicht als Modell gelistet."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = {
        "ollama_compat": {"enabled": True, "exposed_models": ["ha-assist"]},
        "users": [{"id": "ha-assist", "primary_llm": "nonexistent"}],
        "llms": [], "providers": [],
    }
    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: cfg,
        resolve_llm=_resolve_llm, find_ollama_url=lambda c: "",
    )
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/tags")
    assert resp.json()["models"] == []


# ── GET /api/version ─────────────────────────────────────────────────────────

def test_version(app_with_router):
    resp = app_with_router.get("/api/version")
    assert resp.status_code == 200
    assert "haana" in resp.json()["version"]


# ── POST /api/show ───────────────────────────────────────────────────────────

def test_show_valid_model(app_with_router):
    resp = app_with_router.post("/api/show", json={"name": "ha-assist:latest"})
    assert resp.status_code == 200
    assert resp.json()["details"]["family"] == "haana"

def test_show_unknown_model(app_with_router):
    resp = app_with_router.post("/api/show", json={"name": "unknown:latest"})
    assert resp.status_code == 404

def test_show_disabled(app_disabled):
    resp = app_disabled.post("/api/show", json={"name": "ha-assist"})
    assert resp.status_code == 503


# ── GET /api/ps ──────────────────────────────────────────────────────────────

def test_ps_returns_models(app_with_router):
    resp = app_with_router.get("/api/ps")
    assert resp.status_code == 200
    assert len(resp.json()["models"]) == 2

def test_ps_disabled(app_disabled):
    resp = app_disabled.get("/api/ps")
    assert resp.json()["models"] == []


# ── POST /api/chat ───────────────────────────────────────────────────────────

def test_chat_disabled(app_disabled):
    resp = app_disabled.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Hallo"}],
        "stream": False,
    })
    assert resp.status_code == 503


def test_chat_unknown_model(app_with_router):
    resp = app_with_router.post("/api/chat", json={
        "model": "unknown",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
    })
    assert resp.status_code == 404


def test_chat_invalid_json(app_with_router):
    resp = app_with_router.post(
        "/api/chat", content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_chat_no_user_message(app_with_router):
    resp = app_with_router.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "system", "content": "System"}],
        "stream": False,
    })
    assert resp.status_code == 200
    assert resp.json()["message"]["content"] == ""


def _ollama_llm_response(text, model="ministral-3-32k:3b"):
    """Erzeugt ein Ollama-Format Response-Dict wie von _call_llm()."""
    return {
        "model": model,
        "created_at": "2024-01-01T00:00:00.000000000Z",
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
    }


def _ollama_tool_call_response(tool_calls, model="ministral-3-32k:3b", text=""):
    """Erzeugt ein Ollama-Format Response-Dict mit Tool-Calls."""
    return {
        "model": model,
        "created_at": "2024-01-01T00:00:00.000000000Z",
        "message": {
            "role": "assistant",
            "content": text,
            "tool_calls": tool_calls,
        },
        "done": False,
        "done_reason": "tool_calls",
    }


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_calls_llm_directly(mock_llm, mock_mem, config_enabled):
    """Chat ruft LLM direkt auf (kein Agent-Stack)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("Licht ist an.")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist:latest",
        "messages": [{"role": "user", "content": "Licht an"}],
        "stream": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"]["content"] == "Licht ist an."
    assert data["done"] is True

    mock_llm.assert_called_once()
    call_kw = mock_llm.call_args[1]
    assert call_kw["provider_type"] == "ollama"
    assert call_kw["model"] == "ministral-3-32k:3b"
    assert call_kw["url"] == "http://localhost:11434"


@mock.patch("core.ollama_compat._memory_search", return_value="[household_memory] Alice mag warmweiss")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_includes_memories(mock_llm, mock_mem, config_enabled):
    """Memory-Ergebnisse werden in den System-Prompt eingebettet."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("OK")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [
            {"role": "system", "content": "entities here"},
            {"role": "user", "content": "Licht an"},
        ],
        "stream": False,
    })

    # Memory-Search wurde aufgerufen
    mock_mem.assert_called_once()

    # Messages an LLM enthalten Memory-Ergebnisse
    messages = mock_llm.call_args[1]["messages"]
    system = messages[0]["content"]
    assert "Alice mag warmweiss" in system
    assert "entities here" in system


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_system_prompt_passthrough(mock_llm, mock_mem, config_enabled):
    """HA System-Prompt wird 1:1 durchgereicht ohne extra Instruktionen."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("OK")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [
            {"role": "system", "content": "HA system prompt here"},
            {"role": "user", "content": "test"},
        ],
        "stream": False,
    })

    messages = mock_llm.call_args[1]["messages"]
    system = messages[0]["content"]
    # System prompt passed through exactly (no memory = no additions)
    assert system == "HA system prompt here"


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_streaming(mock_llm, mock_mem, config_enabled):
    """Streaming-Modus liefert NDJSON zurueck."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("Ja klar")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,
    })
    assert resp.status_code == 200
    lines = [l for l in resp.text.strip().split("\n") if l.strip()]
    assert len(lines) >= 2
    last = json.loads(lines[-1])
    assert last["done"] is True
    first = json.loads(lines[0])
    assert first["done"] is False


@mock.patch("core.ollama_compat._call_llm")
def test_chat_no_llm_configured(mock_llm):
    """503 wenn kein LLM fuer die Instanz konfiguriert."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = {
        "ollama_compat": {"enabled": True, "exposed_models": ["ha-assist"]},
        "users": [{"id": "ha-assist", "primary_llm": "nonexistent"}],
        "llms": [], "providers": [],
    }
    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: cfg,
        resolve_llm=_resolve_llm, find_ollama_url=lambda c: "",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Hallo"}],
        "stream": False,
    })
    assert resp.status_code == 503
    mock_llm.assert_not_called()


@mock.patch("core.ollama_compat._memory_search", side_effect=Exception("Qdrant down"))
@mock.patch("core.ollama_compat._call_llm")
def test_chat_memory_failure_still_works(mock_llm, mock_mem, config_enabled):
    """Wenn Memory-Suche fehlschlaegt, antwortet LLM trotzdem."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("Antwort ohne Memory")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Hallo"}],
        "stream": False,
    })
    assert resp.status_code == 200
    assert resp.json()["message"]["content"] == "Antwort ohne Memory"


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_tool_call_response(mock_llm, mock_mem, config_enabled):
    """Tool-Call Responses werden direkt als JSON zurueckgegeben (kein Streaming)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_tool_call_response([{
        "id": "call_123",
        "type": "function",
        "function": {"name": "GetLiveContext", "arguments": '{"area": "wohnzimmer"}'},
    }])

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Wohnzimmer Status"}],
        "tools": [{"function": {"name": "GetLiveContext", "parameters": {}}}],
        "stream": True,  # Should still return JSON, not stream
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is False
    assert data["done_reason"] == "tool_calls"
    assert len(data["message"]["tool_calls"]) == 1
    assert data["message"]["tool_calls"][0]["function"]["name"] == "GetLiveContext"


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_tool_result_skips_memory(mock_llm, mock_mem, config_enabled):
    """Bei Tool-Result Follow-ups wird kein Memory-Lookup gemacht."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("Temperatur ist 21 Grad.")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [
            {"role": "user", "content": "Wohnzimmer Status"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1", "function": {"name": "GetLiveContext", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": "Temp: 21°C"},
        ],
        "stream": False,
    })
    assert resp.status_code == 200
    assert resp.json()["message"]["content"] == "Temperatur ist 21 Grad."
    # Memory-Search sollte NICHT aufgerufen werden bei Tool-Result
    mock_mem.assert_not_called()


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_tools_passed_to_llm(mock_llm, mock_mem, config_enabled):
    """Tools aus dem HA-Request werden an den LLM-Call weitergegeben."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("OK")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    tools = [{"function": {"name": "HassTurnOn", "parameters": {"type": "object"}}}]
    client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "Licht an"}],
        "tools": tools,
        "stream": False,
    })

    call_kw = mock_llm.call_args[1]
    assert call_kw["tools"] == tools


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_model_alias_in_response(mock_llm, mock_mem, config_enabled):
    """Response verwendet den Alias-Namen (ha-assist:latest), nicht das echte Modell."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mock_llm.return_value = _ollama_llm_response("OK", model="ministral-3-32k:3b")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist:latest",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
    })
    assert resp.json()["model"] == "ha-assist:latest"


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm", side_effect=Exception("Connection refused"))
def test_chat_llm_error_returns_error_message(mock_llm, mock_mem, config_enabled):
    """Bei LLM-Fehler kommt eine Fehlermeldung statt 500."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: config_enabled,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "http://localhost:11434",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
    })
    assert resp.status_code == 200
    assert "Fehler" in resp.json()["message"]["content"]


# ── Tests: Provider-spezifische Konfiguration ────────────────────────────────

@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_anthropic_provider(mock_llm, mock_mem):
    """Anthropic Provider wird korrekt an _call_llm weitergegeben."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = {
        "ollama_compat": {"enabled": True, "exposed_models": ["ha-assist"]},
        "users": [{"id": "ha-assist", "primary_llm": "haiku"}],
        "llms": [{"id": "haiku", "provider_id": "anthropic-main", "model": "claude-3-haiku-20240307"}],
        "providers": [{"id": "anthropic-main", "type": "anthropic", "key": "sk-test-123"}],
    }
    mock_llm.return_value = _ollama_llm_response("Haiku says hi")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: cfg,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "",
    )
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
    })
    assert resp.status_code == 200

    call_kw = mock_llm.call_args[1]
    assert call_kw["provider_type"] == "anthropic"
    assert call_kw["model"] == "claude-3-haiku-20240307"
    assert call_kw["api_key"] == "sk-test-123"
    assert "anthropic.com" in call_kw["url"]


@mock.patch("core.ollama_compat._memory_search", return_value="")
@mock.patch("core.ollama_compat._call_llm")
def test_chat_minimax_provider(mock_llm, mock_mem):
    """MiniMax Provider wird korrekt geroutet."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = {
        "ollama_compat": {"enabled": True, "exposed_models": ["ha-assist"]},
        "users": [{"id": "ha-assist", "primary_llm": "minimax-m2"}],
        "llms": [{"id": "minimax-m2", "provider_id": "mm", "model": "MiniMax-M2.5"}],
        "providers": [{"id": "mm", "type": "minimax", "key": "mm-key-123"}],
    }
    mock_llm.return_value = _ollama_llm_response("MiniMax says hi")

    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: cfg,
        resolve_llm=_resolve_llm,
        find_ollama_url=lambda c: "",
    )
    app.include_router(router)
    client = TestClient(app)

    client.post("/api/chat", json={
        "model": "ha-assist",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
    })

    call_kw = mock_llm.call_args[1]
    assert call_kw["provider_type"] == "minimax"
    assert call_kw["url"] == "https://api.minimax.io/anthropic"


# ── Tests: Default exposed_models ────────────────────────────────────────────

def test_default_exposed_models():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = {
        "ollama_compat": {"enabled": True, "exposed_models": []},
        "users": list(_USERS), "llms": list(_LLMS), "providers": list(_PROVIDERS),
    }
    app = FastAPI()
    router = create_ollama_router(
        get_config=lambda: cfg,
        resolve_llm=_resolve_llm, find_ollama_url=lambda c: "",
    )
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/tags")
    names = [m["name"] for m in resp.json()["models"]]
    assert "ha-assist:latest" in names
    assert "ha-advanced:latest" in names
