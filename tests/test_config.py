"""Tests fuer admin-interface/main.py – Config laden, Default-Merge, Migration, Env-Var Mapping."""
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# ── Mocks fuer Imports die im admin-interface/main.py gebraucht werden ────────

_mock_docker = types.ModuleType("docker")
_mock_docker_client = mock.MagicMock()
_mock_docker.from_env = mock.MagicMock(return_value=_mock_docker_client)
sys.modules.setdefault("docker", _mock_docker)

sys.modules.setdefault("dotenv", types.ModuleType("dotenv"))
if not hasattr(sys.modules["dotenv"], "load_dotenv"):
    sys.modules["dotenv"].load_dotenv = lambda: None

_admin_path = str(Path("/opt/haana/admin-interface"))
if _admin_path not in sys.path:
    sys.path.insert(0, _admin_path)

_root_path = str(Path("/opt/haana"))
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _chdir_to_admin(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    (tmp_path / "templates").mkdir()
    monkeypatch.chdir(tmp_path)


def _import_main():
    if "main" in sys.modules:
        return sys.modules["main"]
    import main
    return main


# ══════════════════════════════════════════════════════════════════════════════
# Tests: DEFAULT_CONFIG Struktur (neue Provider/LLM-Trennung)
# ══════════════════════════════════════════════════════════════════════════════

def test_default_config_has_providers():
    main = _import_main()
    assert "providers" in main.DEFAULT_CONFIG
    assert len(main.DEFAULT_CONFIG["providers"]) >= 2
    for p in main.DEFAULT_CONFIG["providers"]:
        assert "id" in p
        assert "type" in p


def test_default_config_has_llms():
    main = _import_main()
    assert "llms" in main.DEFAULT_CONFIG
    assert len(main.DEFAULT_CONFIG["llms"]) >= 2
    for l in main.DEFAULT_CONFIG["llms"]:
        assert "id" in l
        assert "provider_id" in l
        assert "model" in l


def test_default_config_no_llm_providers():
    """Alte llm_providers-Struktur darf nicht mehr vorhanden sein."""
    main = _import_main()
    assert "llm_providers" not in main.DEFAULT_CONFIG


def test_default_config_has_services():
    main = _import_main()
    assert "services" in main.DEFAULT_CONFIG


def test_default_config_has_ha_mcp_type():
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_mcp_type" in services
    assert services["ha_mcp_type"] in ("builtin", "extended")


def test_default_config_has_ha_auto_backup():
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_auto_backup" in services
    assert isinstance(services["ha_auto_backup"], bool)


def test_default_config_has_memory():
    main = _import_main()
    assert "memory" in main.DEFAULT_CONFIG
    mem = main.DEFAULT_CONFIG["memory"]
    assert "window_size" in mem
    assert "extraction_llm" in mem


def test_default_config_has_embedding():
    main = _import_main()
    emb = main.DEFAULT_CONFIG["embedding"]
    assert "provider_id" in emb
    assert "model" in emb
    assert "dims" in emb
    assert "fallback_provider_id" in emb


def test_default_config_has_users():
    main = _import_main()
    assert "users" in main.DEFAULT_CONFIG
    assert len(main.DEFAULT_CONFIG["users"]) >= 2
    for u in main.DEFAULT_CONFIG["users"]:
        assert "primary_llm" in u
        assert "fallback_llm" in u


def test_default_config_has_whatsapp():
    main = _import_main()
    assert "whatsapp" in main.DEFAULT_CONFIG
    assert "mode" in main.DEFAULT_CONFIG["whatsapp"]


def test_default_config_has_log_retention():
    main = _import_main()
    assert "log_retention" in main.DEFAULT_CONFIG


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Config-Migration (alte → neue Struktur)
# ══════════════════════════════════════════════════════════════════════════════

def test_migrate_config_from_old_format():
    """Migration von llm_providers[] zu providers[] + llms[]."""
    main = _import_main()
    old_cfg = {
        "llm_providers": [
            {"slot": 1, "name": "Anthropic", "type": "anthropic",
             "url": "", "key": "sk-test", "model": "claude-sonnet-4-6"},
            {"slot": 2, "name": "Fallback", "type": "anthropic",
             "url": "", "key": "sk-test", "model": "claude-haiku-4-5-20251001"},
            {"slot": 3, "name": "Ollama", "type": "ollama",
             "url": "http://ollama:11434", "key": "", "model": "ministral-3-32k:3b"},
        ],
        "use_cases": {"chat": {"label": "Chat", "primary": 1, "fallback": 2}},
        "users": [
            {"id": "alice", "primary_llm_slot": 1, "extraction_llm_slot": 3,
             "display_name": "Alice", "role": "admin", "api_port": 8001,
             "container_name": "haana-alice-1"},
        ],
        "embedding": {"provider": "ollama", "model": "bge-m3", "dims": 1024},
        "memory": {"window_size": 20, "window_minutes": 60},
    }

    result = main._migrate_config(old_cfg)
    assert result is True

    # providers[] wurde erstellt
    assert "providers" in old_cfg
    assert "llm_providers" not in old_cfg
    assert "use_cases" not in old_cfg

    # Deduplizierung: Slot 1 und 2 haben gleichen Provider (type+url+key)
    providers = old_cfg["providers"]
    assert len(providers) == 2  # anthropic (dedupliziert) + ollama

    # llms[] wurde erstellt
    llms = old_cfg["llms"]
    assert len(llms) == 3

    # User-Felder migriert
    user = old_cfg["users"][0]
    assert "primary_llm" in user
    assert "primary_llm_slot" not in user
    assert "fallback_llm" in user
    assert user["primary_llm"] == llms[0]["id"]  # Slot 1 → erstes LLM

    # Embedding migriert
    assert "provider_id" in old_cfg["embedding"]
    assert "provider" not in old_cfg["embedding"]

    # Memory extraction_llm
    assert "extraction_llm" in old_cfg["memory"]


def test_migrate_config_noop_if_already_migrated():
    """Migration macht nichts wenn providers[] schon existiert."""
    main = _import_main()
    cfg = {
        "providers": [{"id": "p1", "name": "P1", "type": "anthropic", "url": "", "key": ""}],
        "llms": [{"id": "l1", "name": "L1", "provider_id": "p1", "model": "m1"}],
    }
    result = main._migrate_config(cfg)
    assert result is False


def test_migrate_config_no_llm_providers():
    """Migration macht nichts wenn llm_providers nicht existiert."""
    main = _import_main()
    cfg = {"services": {}}
    result = main._migrate_config(cfg)
    assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _find_references
# ══════════════════════════════════════════════════════════════════════════════

def test_find_references_provider():
    main = _import_main()
    cfg = {
        "providers": [{"id": "p1", "name": "P1", "type": "anthropic", "url": "", "key": ""}],
        "llms": [
            {"id": "l1", "name": "L1", "provider_id": "p1", "model": "m1"},
            {"id": "l2", "name": "L2", "provider_id": "other", "model": "m2"},
        ],
        "embedding": {"provider_id": "p1", "fallback_provider_id": ""},
        "users": [],
        "memory": {},
    }
    refs = main._find_references("provider", "p1", cfg)
    assert any("L1" in r for r in refs)
    assert any("Embedding" in r for r in refs)
    assert not any("L2" in r for r in refs)


def test_find_references_llm():
    main = _import_main()
    cfg = {
        "providers": [],
        "llms": [],
        "embedding": {},
        "users": [
            {"id": "u1", "primary_llm": "l1", "fallback_llm": "", "extraction_llm": ""},
            {"id": "u2", "primary_llm": "l2", "fallback_llm": "l1", "extraction_llm": ""},
        ],
        "memory": {"extraction_llm": "l1", "extraction_llm_fallback": ""},
    }
    refs = main._find_references("llm", "l1", cfg)
    assert len(refs) == 3  # u1 primary, u2 fallback, memory extraction


# ══════════════════════════════════════════════════════════════════════════════
# Tests: load_config
# ══════════════════════════════════════════════════════════════════════════════

def test_load_config_returns_default_when_no_file(tmp_path):
    main = _import_main()
    fake_conf = tmp_path / "nonexistent" / "config.json"
    with mock.patch.object(main, "CONF_FILE", fake_conf):
        cfg = main.load_config()
    assert "providers" in cfg
    assert "llms" in cfg
    assert "services" in cfg
    assert "memory" in cfg


def test_load_config_reads_existing_file(tmp_path):
    main = _import_main()
    custom_cfg = {
        "providers": [{"id": "p1", "name": "P1", "type": "anthropic", "url": "", "key": "sk-x"}],
        "llms": [{"id": "l1", "name": "L1", "provider_id": "p1", "model": "claude-sonnet-4-6"}],
        "services": {
            "ha_url": "http://my-ha:8123",
            "ha_token": "tok123",
            "ha_mcp_enabled": True,
            "ha_mcp_type": "builtin",
            "ha_mcp_url": "",
            "ha_mcp_token": "",
            "ha_auto_backup": True,
            "ollama_url": "http://ollama:11434",
            "qdrant_url": "http://qdrant:6333",
        },
        "users": [
            {"id": "testuser", "display_name": "Test", "role": "admin",
             "primary_llm": "l1", "fallback_llm": "", "extraction_llm": "",
             "api_port": 8001, "container_name": "haana-test-1"},
        ],
        "memory": {"window_size": 30, "window_minutes": 120, "min_messages": 5,
                    "extraction_llm": "l1", "extraction_llm_fallback": ""},
        "embedding": {"provider_id": "p1", "model": "bge-m3", "dims": 1024, "fallback_provider_id": ""},
    }
    conf_file = tmp_path / "config.json"
    conf_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with mock.patch.object(main, "CONF_FILE", conf_file):
        cfg = main.load_config()

    assert cfg["services"]["ha_url"] == "http://my-ha:8123"
    assert cfg["memory"]["window_size"] == 30


def test_load_config_migrates_old_format(tmp_path):
    """load_config migriert und speichert automatisch."""
    main = _import_main()
    old_cfg = {
        "llm_providers": [
            {"slot": 1, "name": "Anthropic", "type": "anthropic",
             "url": "", "key": "sk-test", "model": "claude-sonnet-4-6"},
        ],
        "users": [
            {"id": "testuser", "display_name": "Test", "role": "admin",
             "primary_llm_slot": 1, "extraction_llm_slot": 1,
             "api_port": 8001, "container_name": "haana-test-1"},
        ],
        "embedding": {"provider": "ollama", "model": "bge-m3", "dims": 1024},
        "memory": {"window_size": 20, "window_minutes": 60},
    }
    conf_file = tmp_path / "config.json"
    conf_file.write_text(json.dumps(old_cfg), encoding="utf-8")

    with mock.patch.object(main, "CONF_FILE", conf_file):
        cfg = main.load_config()

    assert "providers" in cfg
    assert "llms" in cfg
    assert "llm_providers" not in cfg
    # Datei wurde nach Migration gespeichert
    saved = json.loads(conf_file.read_text())
    assert "providers" in saved


def test_load_config_ensures_system_users(tmp_path):
    main = _import_main()
    custom_cfg = {
        "providers": [{"id": "p1", "name": "P1", "type": "anthropic", "url": "", "key": ""}],
        "llms": [{"id": "l1", "name": "L1", "provider_id": "p1", "model": "m"}],
        "users": [
            {"id": "alice", "display_name": "Alice", "role": "admin",
             "primary_llm": "l1", "fallback_llm": "", "extraction_llm": "",
             "api_port": 8001, "container_name": "haana-alice-1"},
        ],
    }
    conf_file = tmp_path / "config.json"
    conf_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with mock.patch.object(main, "CONF_FILE", conf_file):
        cfg = main.load_config()

    user_ids = [u["id"] for u in cfg["users"]]
    assert "ha-assist" in user_ids
    assert "ha-advanced" in user_ids


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _start_agent_container – Env-Var Mapping (neue Struktur)
# ══════════════════════════════════════════════════════════════════════════════

def _make_cfg(**overrides):
    cfg = {
        "providers": [
            {"id": "anthropic-1", "name": "Anthropic", "type": "anthropic",
             "url": "", "key": "sk-test"},
            {"id": "ollama-home", "name": "Ollama", "type": "ollama",
             "url": "http://ollama:11434", "key": ""},
        ],
        "llms": [
            {"id": "claude-primary", "name": "Claude", "provider_id": "anthropic-1",
             "model": "claude-sonnet-4-6"},
            {"id": "ollama-extract", "name": "Ministral", "provider_id": "ollama-home",
             "model": "ministral-3-32k:3b"},
        ],
        "services": {
            "ha_url": "http://ha:8123",
            "ha_token": "tok",
            "ha_mcp_enabled": False,
            "ha_mcp_type": "extended",
            "ha_mcp_url": "",
            "ha_mcp_token": "",
            "ha_auto_backup": False,
            "ollama_url": "http://ollama:11434",
            "qdrant_url": "http://qdrant:6333",
        },
        "memory": {"window_size": 20, "window_minutes": 60,
                    "extraction_llm": "ollama-extract", "extraction_llm_fallback": ""},
        "embedding": {"provider_id": "ollama-home", "model": "bge-m3", "dims": 1024,
                       "fallback_provider_id": ""},
    }
    cfg.update(overrides)
    return cfg


def _make_user(**overrides):
    user = {
        "id": "testuser",
        "display_name": "Test",
        "api_port": 8001,
        "container_name": "haana-test-1",
        "claude_md_template": "user",
        "primary_llm": "claude-primary",
        "fallback_llm": "",
        "extraction_llm": "",
    }
    user.update(overrides)
    return user


def test_start_container_basic_env_vars():
    main = _import_main()
    cfg = _make_cfg()
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    assert env["HAANA_INSTANCE"] == "testuser"
    assert env["HAANA_API_PORT"] == "8001"
    assert env["HAANA_MODEL"] == "claude-sonnet-4-6"
    assert env["ANTHROPIC_API_KEY"] == "sk-test"
    assert env["QDRANT_URL"] == "http://qdrant:6333"
    assert env["OLLAMA_URL"] == "http://ollama:11434"


def test_start_container_extraction_llm():
    """Extraction-LLM wird aus User oder Global-Memory aufgeloest."""
    main = _import_main()
    cfg = _make_cfg()
    user = _make_user()  # extraction_llm leer → fällt auf global zurück

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    env = dc.containers.run.call_args[1]["environment"]
    assert env["HAANA_MEMORY_MODEL"] == "ministral-3-32k:3b"


def test_start_container_user_extraction_override():
    """User-spezifisches Extraction-LLM ueberschreibt Global."""
    main = _import_main()
    cfg = _make_cfg()
    user = _make_user(extraction_llm="claude-primary")

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    env = dc.containers.run.call_args[1]["environment"]
    assert env["HAANA_MEMORY_MODEL"] == "claude-sonnet-4-6"


def test_start_container_minimax_provider():
    """MiniMax-Provider setzt ANTHROPIC_BASE_URL/AUTH_TOKEN statt API_KEY."""
    main = _import_main()
    cfg = _make_cfg(providers=[
        {"id": "mm-1", "name": "MiniMax", "type": "minimax",
         "url": "https://api.minimax.io/anthropic", "key": "mm-key"},
    ], llms=[
        {"id": "mm-llm", "name": "MiniMax M2.5", "provider_id": "mm-1", "model": "MiniMax-M2.5"},
    ])
    user = _make_user(primary_llm="mm-llm")

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    env = dc.containers.run.call_args[1]["environment"]
    assert env["ANTHROPIC_BASE_URL"] == "https://api.minimax.io/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "mm-key"
    assert "ANTHROPIC_API_KEY" not in env


def test_start_container_mcp_enabled():
    main = _import_main()
    cfg = _make_cfg()
    cfg["services"]["ha_mcp_enabled"] = True
    cfg["services"]["ha_mcp_url"] = "http://ha:9583/private_abc"
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        result = main._start_agent_container(user, cfg)

    assert result["ok"] is True
    env = dc.containers.run.call_args[1]["environment"]
    assert env["HA_MCP_URL"] == "http://ha:9583/private_abc"
    assert env["HA_MCP_TYPE"] == "extended"


def test_start_container_no_mcp_when_disabled():
    main = _import_main()
    cfg = _make_cfg()
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    env = dc.containers.run.call_args[1]["environment"]
    assert "HA_MCP_URL" not in env
    assert "HA_MCP_TYPE" not in env


def test_start_container_builtin_auto_url():
    main = _import_main()
    cfg = _make_cfg()
    cfg["services"]["ha_mcp_enabled"] = True
    cfg["services"]["ha_mcp_type"] = "builtin"
    cfg["services"]["ha_mcp_url"] = ""
    cfg["services"]["ha_url"] = "http://homeassistant.local:8123"
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    env = dc.containers.run.call_args[1]["environment"]
    assert env["HA_MCP_URL"] == "http://homeassistant.local:8123/mcp_server/sse"
    assert env["HA_MCP_TYPE"] == "builtin"


def test_start_container_no_docker():
    main = _import_main()
    cfg = _make_cfg()
    user = _make_user()

    with mock.patch.object(main, "_docker_client", None):
        result = main._start_agent_container(user, cfg)

    assert result["ok"] is False
    assert "Docker" in result["error"]


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _resolve_llm
# ══════════════════════════════════════════════════════════════════════════════

def test_resolve_llm_found():
    main = _import_main()
    cfg = _make_cfg()
    llm, prov = main._resolve_llm("claude-primary", cfg)
    assert llm["model"] == "claude-sonnet-4-6"
    assert prov["type"] == "anthropic"


def test_resolve_llm_not_found():
    main = _import_main()
    cfg = _make_cfg()
    llm, prov = main._resolve_llm("nonexistent", cfg)
    assert llm == {}
    assert prov == {}


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _slugify
# ══════════════════════════════════════════════════════════════════════════════

def test_slugify():
    main = _import_main()
    assert main._slugify("Anthropic (Primär)") == "anthropic-primaer"
    assert main._slugify("Ollama Lokal") == "ollama-lokal"
    assert main._slugify("   ") == "item"
    assert main._slugify("Löwe & Bär") == "loewe-baer"
