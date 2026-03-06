"""Tests fuer admin-interface/main.py – Config laden, Default-Merge, Env-Var Mapping."""
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# ── Mocks fuer Imports die im admin-interface/main.py gebraucht werden ────────

# Docker-Client mocken
_mock_docker = types.ModuleType("docker")
_mock_docker_client = mock.MagicMock()
_mock_docker.from_env = mock.MagicMock(return_value=_mock_docker_client)
sys.modules.setdefault("docker", _mock_docker)

# dotenv optional
sys.modules.setdefault("dotenv", types.ModuleType("dotenv"))
if not hasattr(sys.modules["dotenv"], "load_dotenv"):
    sys.modules["dotenv"].load_dotenv = lambda: None

# FastAPI und Jinja2 muessen nicht echt sein fuer Config-Tests,
# aber main.py importiert sie auf Modul-Ebene. Wir importieren main.py direkt
# mit sys.path Erweiterung.

# Sicherstellen dass admin-interface im Pfad ist
_admin_path = str(Path("/opt/haana/admin-interface"))
if _admin_path not in sys.path:
    sys.path.insert(0, _admin_path)

# Auch /opt/haana fuer core imports
_root_path = str(Path("/opt/haana"))
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)


# ══════════════════════════════════════════════════════════════════════════════
# Tests: DEFAULT_CONFIG Struktur
# ══════════════════════════════════════════════════════════════════════════════

# Wir importieren main.py-Level-Objekte. Da main.py bei Import FastAPI-App
# erstellt und static-files mounted, muessen wir den CWD patchen.
@pytest.fixture(autouse=True)
def _chdir_to_admin(tmp_path, monkeypatch):
    """Wechselt CWD zu einem temp-Verzeichnis mit minimaler Struktur."""
    (tmp_path / "static").mkdir()
    (tmp_path / "templates").mkdir()
    monkeypatch.chdir(tmp_path)


def _import_main():
    """Importiert admin-interface/main.py (cached nach erstem Aufruf)."""
    # Re-import erzwingen wenn noetig
    if "main" in sys.modules:
        return sys.modules["main"]
    import main
    return main


def test_default_config_has_services():
    """DEFAULT_CONFIG enthaelt 'services' Sektion."""
    main = _import_main()
    assert "services" in main.DEFAULT_CONFIG


def test_default_config_has_ha_mcp_type():
    """DEFAULT_CONFIG.services hat ha_mcp_type."""
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_mcp_type" in services
    assert services["ha_mcp_type"] in ("builtin", "extended")


def test_default_config_has_ha_auto_backup():
    """DEFAULT_CONFIG.services hat ha_auto_backup."""
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_auto_backup" in services
    assert isinstance(services["ha_auto_backup"], bool)


def test_default_config_has_ha_mcp_enabled():
    """DEFAULT_CONFIG.services hat ha_mcp_enabled."""
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_mcp_enabled" in services


def test_default_config_has_ha_mcp_url():
    """DEFAULT_CONFIG.services hat ha_mcp_url."""
    main = _import_main()
    services = main.DEFAULT_CONFIG["services"]
    assert "ha_mcp_url" in services


def test_default_config_has_memory():
    """DEFAULT_CONFIG hat memory-Sektion mit window_size."""
    main = _import_main()
    assert "memory" in main.DEFAULT_CONFIG
    assert "window_size" in main.DEFAULT_CONFIG["memory"]


def test_default_config_has_embedding():
    """DEFAULT_CONFIG hat embedding-Sektion."""
    main = _import_main()
    assert "embedding" in main.DEFAULT_CONFIG
    assert "model" in main.DEFAULT_CONFIG["embedding"]
    assert "dims" in main.DEFAULT_CONFIG["embedding"]


def test_default_config_has_users():
    """DEFAULT_CONFIG hat users-Liste mit mindestens 2 Eintraegen."""
    main = _import_main()
    assert "users" in main.DEFAULT_CONFIG
    assert len(main.DEFAULT_CONFIG["users"]) >= 2


def test_default_config_has_whatsapp():
    """DEFAULT_CONFIG hat whatsapp-Sektion."""
    main = _import_main()
    assert "whatsapp" in main.DEFAULT_CONFIG
    assert "mode" in main.DEFAULT_CONFIG["whatsapp"]


def test_default_config_has_log_retention():
    """DEFAULT_CONFIG hat log_retention-Sektion."""
    main = _import_main()
    assert "log_retention" in main.DEFAULT_CONFIG


# ══════════════════════════════════════════════════════════════════════════════
# Tests: load_config – Merge mit Defaults
# ══════════════════════════════════════════════════════════════════════════════


def test_load_config_returns_default_when_no_file(tmp_path):
    """Wenn keine config.json existiert, wird DEFAULT_CONFIG zurueckgegeben."""
    main = _import_main()
    fake_conf = tmp_path / "nonexistent" / "config.json"  # existiert nicht
    with mock.patch.object(main, "CONF_FILE", fake_conf):
        cfg = main.load_config()
    assert "services" in cfg
    assert "memory" in cfg


def test_load_config_reads_existing_file(tmp_path):
    """load_config liest eine bestehende config.json."""
    main = _import_main()
    custom_cfg = {
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
             "api_port": 8001, "container_name": "haana-test-1"},
        ],
        "memory": {"window_size": 30, "window_minutes": 120, "min_messages": 5},
    }
    conf_file = tmp_path / "config.json"
    conf_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with mock.patch.object(main, "CONF_FILE", conf_file):
        cfg = main.load_config()

    assert cfg["services"]["ha_url"] == "http://my-ha:8123"
    assert cfg["services"]["ha_auto_backup"] is True
    assert cfg["memory"]["window_size"] == 30


def test_load_config_strips_embeddings_use_case(tmp_path):
    """load_config entfernt den 'embeddings' Use-Case (deprecated)."""
    main = _import_main()
    custom_cfg = {
        "use_cases": {"chat": {"label": "Chat", "primary": 1, "fallback": 2},
                      "embeddings": {"label": "old", "primary": 3, "fallback": 3}},
        "users": [],
    }
    conf_file = tmp_path / "config.json"
    conf_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with mock.patch.object(main, "CONF_FILE", conf_file):
        cfg = main.load_config()

    assert "embeddings" not in cfg.get("use_cases", {})


def test_load_config_ensures_system_users(tmp_path):
    """load_config fuegt System-User (ha-assist, ha-advanced) hinzu."""
    main = _import_main()
    custom_cfg = {
        "users": [
            {"id": "alice", "display_name": "Alice", "role": "admin",
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
# Tests: _start_agent_container – Env-Var Mapping
# ══════════════════════════════════════════════════════════════════════════════


def _make_cfg_with_mcp(mcp_enabled=True, mcp_type="extended", mcp_url="http://ha:9583/x",
                       ha_url="http://ha:8123"):
    """Erstellt eine Config mit MCP-Einstellungen."""
    return {
        "services": {
            "ha_url": ha_url,
            "ha_token": "tok",
            "ha_mcp_enabled": mcp_enabled,
            "ha_mcp_type": mcp_type,
            "ha_mcp_url": mcp_url,
            "ha_mcp_token": "",
            "ha_auto_backup": False,
            "ollama_url": "http://ollama:11434",
            "qdrant_url": "http://qdrant:6333",
        },
        "llm_providers": [
            {"slot": 1, "name": "Test", "type": "anthropic",
             "url": "", "key": "sk-test", "model": "claude-sonnet-4-6"},
            {"slot": 3, "name": "Local", "type": "ollama",
             "url": "http://ollama:11434", "key": "", "model": "ministral"},
        ],
        "memory": {"window_size": 20, "window_minutes": 60},
        "embedding": {"model": "bge-m3", "dims": 1024},
    }


def _make_user():
    return {
        "id": "testuser",
        "display_name": "Test",
        "api_port": 8001,
        "container_name": "haana-test-1",
        "claude_md_template": "user",
        "primary_llm_slot": 1,
        "extraction_llm_slot": 3,
    }


def test_start_container_sets_mcp_url_and_type():
    """_start_agent_container setzt HA_MCP_URL und HA_MCP_TYPE wenn MCP aktiviert."""
    main = _import_main()
    cfg = _make_cfg_with_mcp(mcp_enabled=True, mcp_type="extended",
                             mcp_url="http://ha:9583/private_abc")
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        result = main._start_agent_container(user, cfg)

    assert result["ok"] is True
    # Pruefe die Environment-Variablen die an Docker uebergeben wurden
    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    assert env["HA_MCP_URL"] == "http://ha:9583/private_abc"
    assert env["HA_MCP_TYPE"] == "extended"


def test_start_container_no_mcp_when_disabled():
    """Wenn ha_mcp_enabled=False, werden HA_MCP_URL/TYPE nicht gesetzt."""
    main = _import_main()
    cfg = _make_cfg_with_mcp(mcp_enabled=False)
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    assert "HA_MCP_URL" not in env
    assert "HA_MCP_TYPE" not in env


def test_start_container_builtin_auto_url():
    """Bei builtin + leerer mcp_url wird URL automatisch aus ha_url generiert."""
    main = _import_main()
    cfg = _make_cfg_with_mcp(mcp_enabled=True, mcp_type="builtin", mcp_url="",
                             ha_url="http://homeassistant.local:8123")
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    assert env["HA_MCP_URL"] == "http://homeassistant.local:8123/mcp_server/sse"
    assert env["HA_MCP_TYPE"] == "builtin"


def test_start_container_extended_no_auto_url():
    """Bei extended + leerer mcp_url wird KEINE Auto-URL generiert -> kein HA_MCP_URL."""
    main = _import_main()
    cfg = _make_cfg_with_mcp(mcp_enabled=True, mcp_type="extended", mcp_url="",
                             ha_url="http://ha:8123")
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    # extended ohne explizite URL -> kein MCP
    assert "HA_MCP_URL" not in env


def test_start_container_no_docker():
    """Ohne Docker-Client wird Fehler zurueckgegeben."""
    main = _import_main()
    cfg = _make_cfg_with_mcp()
    user = _make_user()

    with mock.patch.object(main, "_docker_client", None):
        result = main._start_agent_container(user, cfg)

    assert result["ok"] is False
    assert "Docker" in result["error"]


def test_start_container_basic_env_vars():
    """Grundlegende Env-Vars (HAANA_INSTANCE, HAANA_API_PORT, etc.) werden gesetzt."""
    main = _import_main()
    cfg = _make_cfg_with_mcp(mcp_enabled=False)
    user = _make_user()

    with mock.patch.object(main, "_docker_client", mock.MagicMock()) as dc:
        dc.containers.get.side_effect = Exception("not found")
        dc.containers.run.return_value = mock.MagicMock(short_id="abc123")
        main._start_agent_container(user, cfg)

    call_kwargs = dc.containers.run.call_args
    env = call_kwargs[1]["environment"] if "environment" in call_kwargs[1] else call_kwargs.kwargs["environment"]
    assert env["HAANA_INSTANCE"] == "testuser"
    assert env["HAANA_API_PORT"] == "8001"
    assert env["QDRANT_URL"] == "http://qdrant:6333"
    assert env["HAANA_MODEL"] == "claude-sonnet-4-6"
