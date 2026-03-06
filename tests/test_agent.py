"""Tests fuer core/agent.py – HaanaAgent Init, MCP-Registrierung, Options-Building."""
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest


# ── Mock des claude_agent_sdk Moduls BEVOR core.agent importiert wird ─────────

def _build_sdk_mocks():
    """Erstellt ein gefaktes claude_agent_sdk Modul mit allen noetigen Klassen."""
    sdk = types.ModuleType("claude_agent_sdk")
    sdk_types = types.ModuleType("claude_agent_sdk.types")

    class _ClaudeSDKClient:
        def __init__(self, **kw):
            self._opts = kw

    class _ClaudeAgentOptions:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class _McpHttpServerConfig:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class _McpSSEServerConfig:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    sdk.ClaudeSDKClient = _ClaudeSDKClient
    sdk.ClaudeAgentOptions = _ClaudeAgentOptions
    sdk.AssistantMessage = type("AssistantMessage", (), {})
    sdk.ResultMessage = type("ResultMessage", (), {})
    sdk.TextBlock = type("TextBlock", (), {})
    sdk.ToolUseBlock = type("ToolUseBlock", (), {})
    sdk.CLINotFoundError = type("CLINotFoundError", (Exception,), {})
    sdk.CLIConnectionError = type("CLIConnectionError", (Exception,), {})
    sdk.ProcessError = type("ProcessError", (Exception,), {"exit_code": 1})
    sdk.CLIJSONDecodeError = type("CLIJSONDecodeError", (Exception,), {})

    sdk_types.McpHttpServerConfig = _McpHttpServerConfig
    sdk_types.McpSSEServerConfig = _McpSSEServerConfig

    return sdk, sdk_types


_sdk, _sdk_types = _build_sdk_mocks()

# ── Temporaer Mocks in sys.modules injizieren, core.agent importieren,
#    dann Original-Module wiederherstellen damit test_memory.py nicht bricht. ──

_orig_sdk = sys.modules.get("claude_agent_sdk")
_orig_sdk_types = sys.modules.get("claude_agent_sdk.types")
_orig_memory = sys.modules.get("core.memory")
_orig_logger = sys.modules.get("core.logger")

sys.modules["claude_agent_sdk"] = _sdk
sys.modules["claude_agent_sdk.types"] = _sdk_types

# Mock core.memory und core.logger damit kein Qdrant/Ollama noetig ist
_mock_memory_mod = types.ModuleType("core.memory")


class _FakeHaanaMemory:
    def __init__(self, instance):
        self.instance = instance
        self._last_search_hits = 0

    def search(self, q):
        return ""

    async def load_context(self, p):
        return 0

    def save_context(self, p):
        pass

    def pending_count(self):
        return 0


_mock_memory_mod.HaanaMemory = _FakeHaanaMemory
sys.modules["core.memory"] = _mock_memory_mod

_mock_logger_mod = types.ModuleType("core.logger")
_mock_logger_mod.log_conversation = lambda **kw: None
_mock_logger_mod.log_tool_call = lambda **kw: None
sys.modules["core.logger"] = _mock_logger_mod

# ── Jetzt kann core.agent importiert werden ───────────────────────────────────
from core.agent import HaanaAgent  # noqa: E402

# ── Original-Module wiederherstellen (fuer test_memory.py etc.) ───────────────
# core.agent ist jetzt geladen und referenziert die Mocks intern,
# aber sys.modules zeigt wieder auf die echten Module.
for _key, _orig in [
    ("core.memory", _orig_memory),
    ("core.logger", _orig_logger),
]:
    if _orig is not None:
        sys.modules[_key] = _orig
    else:
        sys.modules.pop(_key, None)


# ── Hilfsfunktion: Agent mit gemocktem CLAUDE.md erstellen ────────────────────

def _make_agent(env_overrides: dict | None = None, tmp_path: Path | None = None):
    """Erstellt einen HaanaAgent mit einem temporaeren CLAUDE.md."""
    env = {
        "HAANA_MODEL": "test-model",
    }
    if env_overrides:
        env.update(env_overrides)

    # CLAUDE.md muss existieren – wir patchen Path.exists()
    with mock.patch.dict(os.environ, env, clear=False):
        # Patch damit /app/CLAUDE.md gefunden wird
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test-instanz")
    return agent


# ══════════════════════════════════════════════════════════════════════════════
# Tests: __init__() – MCP-Server Registrierung
# ══════════════════════════════════════════════════════════════════════════════


def test_init_no_mcp_url_no_servers():
    """Ohne HA_MCP_URL werden keine MCP-Server registriert."""
    env = {"HAANA_MODEL": "m"}
    # Sicherstellen dass HA_MCP_URL NICHT gesetzt ist
    cleaned = {k: v for k, v in os.environ.items() if k != "HA_MCP_URL"}
    cleaned.update(env)
    with mock.patch.dict(os.environ, cleaned, clear=True):
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test")

    assert agent._mcp_servers == {}


def test_init_extended_mcp_type():
    """HA_MCP_TYPE=extended -> McpHttpServerConfig mit type='http'."""
    agent = _make_agent({
        "HA_MCP_URL": "http://ha:9583/private_abc",
        "HA_MCP_TYPE": "extended",
    })
    assert "home-assistant" in agent._mcp_servers
    srv = agent._mcp_servers["home-assistant"]
    assert srv.type == "http"
    assert srv.url == "http://ha:9583/private_abc"


def test_init_extended_is_default_type():
    """Ohne explizites HA_MCP_TYPE wird 'extended' verwendet (Default)."""
    env = {
        "HAANA_MODEL": "m",
        "HA_MCP_URL": "http://ha:9583/private_xyz",
    }
    cleaned = {k: v for k, v in os.environ.items()
               if k not in ("HA_MCP_TYPE", "HA_MCP_URL")}
    cleaned.update(env)
    with mock.patch.dict(os.environ, cleaned, clear=True):
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test")

    srv = agent._mcp_servers["home-assistant"]
    assert srv.type == "http"


def test_init_builtin_mcp_type():
    """HA_MCP_TYPE=builtin -> McpSSEServerConfig mit type='sse' und Authorization Header."""
    agent = _make_agent({
        "HA_MCP_URL": "http://ha:8123/mcp_server/sse",
        "HA_MCP_TYPE": "builtin",
        "HA_TOKEN": "my-secret-token",
    })
    assert "home-assistant" in agent._mcp_servers
    srv = agent._mcp_servers["home-assistant"]
    assert srv.type == "sse"
    assert srv.url == "http://ha:8123/mcp_server/sse"
    assert srv.headers == {"Authorization": "Bearer my-secret-token"}


def test_init_builtin_mcp_no_token():
    """HA_MCP_TYPE=builtin ohne HA_TOKEN -> leerer headers dict."""
    env = {
        "HAANA_MODEL": "m",
        "HA_MCP_URL": "http://ha:8123/mcp_server/sse",
        "HA_MCP_TYPE": "builtin",
    }
    cleaned = {k: v for k, v in os.environ.items() if k != "HA_TOKEN"}
    cleaned.update(env)
    with mock.patch.dict(os.environ, cleaned, clear=True):
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test")

    srv = agent._mcp_servers["home-assistant"]
    assert srv.type == "sse"
    assert srv.headers == {}


def test_init_claude_md_not_found():
    """Wenn CLAUDE.md nirgends existiert -> FileNotFoundError."""
    with mock.patch.dict(os.environ, {"HAANA_MODEL": "m"}, clear=False):
        with mock.patch.object(Path, "exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="CLAUDE.md nicht gefunden"):
                HaanaAgent("nonexistent")


def test_init_model_from_env():
    """HAANA_MODEL Env-Var wird als self.model gesetzt."""
    agent = _make_agent({"HAANA_MODEL": "claude-opus-4-20250514"})
    assert agent.model == "claude-opus-4-20250514"


def test_init_model_none_if_empty():
    """Leeres HAANA_MODEL -> self.model ist None."""
    env = {"HAANA_MODEL": ""}
    cleaned = {k: v for k, v in os.environ.items() if k != "HAANA_MODEL"}
    cleaned.update(env)
    with mock.patch.dict(os.environ, cleaned, clear=True):
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test")

    assert agent.model is None


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _build_options()
# ══════════════════════════════════════════════════════════════════════════════


def test_build_options_allowed_tools():
    """_build_options() setzt die erwarteten allowed_tools."""
    agent = _make_agent()
    opts = agent._build_options()
    assert "Read" in opts.allowed_tools
    assert "Write" in opts.allowed_tools
    assert "Bash" in opts.allowed_tools
    assert "Glob" in opts.allowed_tools
    assert "Grep" in opts.allowed_tools


def test_build_options_mcp_servers_included():
    """_build_options() gibt registrierte MCP-Server weiter."""
    agent = _make_agent({
        "HA_MCP_URL": "http://ha:9583/x",
        "HA_MCP_TYPE": "extended",
    })
    opts = agent._build_options()
    assert "home-assistant" in opts.mcp_servers
    assert opts.mcp_servers["home-assistant"].type == "http"


def test_build_options_empty_mcp_when_none():
    """Ohne MCP-Server -> mcp_servers ist leeres dict."""
    env = {"HAANA_MODEL": "m"}
    cleaned = {k: v for k, v in os.environ.items() if k != "HA_MCP_URL"}
    cleaned.update(env)
    with mock.patch.dict(os.environ, cleaned, clear=True):
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).endswith("CLAUDE.md") and str(self.parent) == "/app":
                return True
            return original_exists(self)

        with mock.patch.object(Path, "exists", fake_exists):
            agent = HaanaAgent("test")

    opts = agent._build_options()
    assert opts.mcp_servers == {}


def test_build_options_removes_claudecode_env():
    """_build_options() entfernt CLAUDECODE aus os.environ."""
    agent = _make_agent()
    os.environ["CLAUDECODE"] = "1"
    agent._build_options()
    assert "CLAUDECODE" not in os.environ


def test_build_options_model_passed():
    """_build_options() setzt das konfigurierte Modell."""
    agent = _make_agent({"HAANA_MODEL": "test-model-42"})
    opts = agent._build_options()
    assert opts.model == "test-model-42"


def test_build_options_permission_mode():
    """_build_options() setzt permission_mode auf bypassPermissions."""
    agent = _make_agent()
    opts = agent._build_options()
    assert opts.permission_mode == "bypassPermissions"


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Tool-Verwaltung
# ══════════════════════════════════════════════════════════════════════════════


def test_register_mcp_server():
    """register_mcp_server() fuegt Server korrekt hinzu."""
    agent = _make_agent()
    fake_config = type("Cfg", (), {"type": "http", "url": "http://test"})()
    agent.register_mcp_server("my-tool", fake_config)
    assert "my-tool" in agent._mcp_servers
    assert agent._mcp_servers["my-tool"].url == "http://test"


def test_allow_tools_extends_list():
    """allow_tools() erweitert die erlaubten Tools."""
    agent = _make_agent()
    initial_count = len(agent._allowed_tools)
    agent.allow_tools(["CustomTool1", "CustomTool2"])
    assert len(agent._allowed_tools) == initial_count + 2
    assert "CustomTool1" in agent._allowed_tools
    assert "CustomTool2" in agent._allowed_tools
