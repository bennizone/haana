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

    class _McpStdioServerConfig:
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
    sdk_types.McpStdioServerConfig = _McpStdioServerConfig

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
    """_build_options() entfernt CLAUDECODE aus dem Subprocess-Env."""
    agent = _make_agent({"CLAUDECODE": "1"})
    opts = agent._build_options()
    assert "CLAUDECODE" not in opts.env


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


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Env-Isolation (InProcess-Modus)
# ══════════════════════════════════════════════════════════════════════════════


def test_env_snapshot_captured_at_init():
    """Agent captures env at init, not at runtime."""
    agent = _make_agent({"HAANA_MODEL": "captured-model"})
    # After init, changing os.environ should not affect the agent
    assert agent._env.get("HAANA_MODEL") == "captured-model"
    assert agent.model == "captured-model"


def test_build_options_uses_captured_env():
    """_build_options() uses the captured env snapshot, not current os.environ."""
    agent = _make_agent({"MY_CUSTOM_VAR": "from-init"})
    # Verify the captured env is used
    opts = agent._build_options()
    assert opts.env.get("MY_CUSTOM_VAR") == "from-init"


def test_context_path_uses_data_dir():
    """_context_path respects HAANA_DATA_DIR from env."""
    agent = _make_agent({"HAANA_DATA_DIR": "/data"})
    assert str(agent._context_path).startswith("/data/context/")


def test_context_path_default():
    """_context_path falls back to 'data' when HAANA_DATA_DIR not set."""
    agent = _make_agent()
    assert "context" in str(agent._context_path)


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Voice Memory-Extraktion
# ══════════════════════════════════════════════════════════════════════════════


def test_should_extract_memory_webchat_always():
    """Webchat extrahiert immer."""
    from core.agent import _should_extract_memory
    assert _should_extract_memory("Wie wird das Wetter?", "webchat") is True
    assert _should_extract_memory("Licht an", "repl") is True
    assert _should_extract_memory("Hallo", "whatsapp") is True


def test_should_extract_memory_voice_skips_normal():
    """ha_voice überspringt normale Nachrichten."""
    from core.agent import _should_extract_memory
    assert _should_extract_memory("Wie wird das Wetter?", "ha_voice") is False
    assert _should_extract_memory("Schalte das Licht an", "ha_voice") is False
    assert _should_extract_memory("Temperatur im Wohnzimmer", "ha_voice") is False


def test_should_extract_memory_voice_explicit_save():
    """ha_voice extrahiert bei expliziten Speicher-Befehlen."""
    from core.agent import _should_extract_memory
    assert _should_extract_memory("Merke dir, dass wir abends warmes Licht mögen", "ha_voice") is True
    assert _should_extract_memory("Merk dir bitte das WLAN-Passwort", "ha_voice") is True
    assert _should_extract_memory("Vergiss nicht, dass Bob Laktose nicht verträgt", "ha_voice") is True
    assert _should_extract_memory("Speichere: Müll wird dienstags abgeholt", "ha_voice") is True
    assert _should_extract_memory("Erinner dich daran, dass der Schlüssel unter der Matte liegt", "ha_voice") is True
    assert _should_extract_memory("Remember that we like 21 degrees", "ha_voice") is True
    assert _should_extract_memory("Denk dran, morgen kommt der Handwerker", "ha_voice") is True
    assert _should_extract_memory("Notiere: Pizza bestellen am Freitag", "ha_voice") is True


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Fallback-LLM
# ══════════════════════════════════════════════════════════════════════════════


def test_fallback_available_when_env_set():
    """Fallback ist verfügbar wenn HAANA_FALLBACK_MODEL gesetzt."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "fallback-model",
        "HAANA_FALLBACK_PROVIDER_TYPE": "anthropic",
    })
    assert agent._fallback_available is True
    assert agent._fallback_active is False


def test_fallback_not_available_when_no_env():
    """Fallback ist nicht verfügbar ohne HAANA_FALLBACK_MODEL."""
    agent = _make_agent({})
    assert agent._fallback_available is False


def test_is_fallback_error_auth_patterns():
    """_is_fallback_error erkennt Auth-Fehler korrekt."""
    assert HaanaAgent._is_fallback_error("401 Unauthorized") is True
    assert HaanaAgent._is_fallback_error("403 Forbidden") is True
    assert HaanaAgent._is_fallback_error("invalid api key") is True
    assert HaanaAgent._is_fallback_error("authentication failed") is True
    assert HaanaAgent._is_fallback_error("rate limit exceeded") is True
    assert HaanaAgent._is_fallback_error("overloaded_error") is True
    assert HaanaAgent._is_fallback_error("insufficient quota") is True


def test_is_fallback_error_non_auth():
    """_is_fallback_error ignoriert nicht-auth Fehler."""
    assert HaanaAgent._is_fallback_error("timeout after 30s") is False
    assert HaanaAgent._is_fallback_error("JSON parse error") is False
    assert HaanaAgent._is_fallback_error("model not found") is False


@pytest.mark.asyncio
async def test_activate_fallback_switches_env():
    """_activate_fallback() setzt die Env-Vars auf Fallback-Werte."""
    agent = _make_agent({
        "HAANA_MODEL": "primary-model",
        "HAANA_FALLBACK_MODEL": "fallback-model",
        "HAANA_FALLBACK_PROVIDER_TYPE": "anthropic",
        "HAANA_FALLBACK_API_KEY": "fb-key-123",
        "HAANA_FALLBACK_BASE_URL": "https://fallback.api.com",
    })

    assert agent.model == "primary-model"
    assert agent._fallback_active is False

    result = await agent._activate_fallback()

    assert result is True
    assert agent._fallback_active is True
    assert agent.model == "fallback-model"
    assert agent._env.get("ANTHROPIC_API_KEY") == "fb-key-123"
    assert agent._env.get("ANTHROPIC_BASE_URL") == "https://fallback.api.com"
    assert agent._cli_model == "fallback-model"


@pytest.mark.asyncio
async def test_activate_fallback_minimax():
    """_activate_fallback() setzt MiniMax-spezifische Env-Vars."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "MiniMax-M2.5",
        "HAANA_FALLBACK_PROVIDER_TYPE": "minimax",
        "HAANA_FALLBACK_BASE_URL": "https://api.minimax.io/anthropic",
        "HAANA_FALLBACK_AUTH_TOKEN": "mm-key",
    })

    await agent._activate_fallback()

    assert agent.model == "MiniMax-M2.5"
    assert agent._env.get("ANTHROPIC_BASE_URL") == "https://api.minimax.io/anthropic"
    assert agent._env.get("ANTHROPIC_AUTH_TOKEN") == "mm-key"
    assert agent._env.get("ANTHROPIC_MODEL") == "MiniMax-M2.5"
    assert agent._cli_model is None


@pytest.mark.asyncio
async def test_activate_fallback_ollama():
    """_activate_fallback() setzt Ollama-spezifische Env-Vars."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "llama3:8b",
        "HAANA_FALLBACK_PROVIDER_TYPE": "ollama",
        "HAANA_FALLBACK_BASE_URL": "http://localhost:11434",
        "HAANA_FALLBACK_AUTH_TOKEN": "ollama",
    })

    await agent._activate_fallback()

    assert agent.model == "llama3:8b"
    assert agent._env.get("ANTHROPIC_BASE_URL") == "http://localhost:11434"
    assert agent._env.get("ANTHROPIC_AUTH_TOKEN") == "ollama"
    assert agent._cli_model == "llama3:8b"


@pytest.mark.asyncio
async def test_activate_fallback_openai():
    """_activate_fallback() setzt OpenAI-spezifische Env-Vars."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "gpt-4o",
        "HAANA_FALLBACK_PROVIDER_TYPE": "openai",
        "HAANA_FALLBACK_API_KEY": "sk-test",
        "HAANA_FALLBACK_BASE_URL": "",
    })

    await agent._activate_fallback()

    assert agent.model == "gpt-4o"
    assert agent._env.get("OPENAI_API_KEY") == "sk-test"
    assert agent._env.get("OPENAI_MODEL") == "gpt-4o"
    assert agent._cli_model is None


@pytest.mark.asyncio
async def test_activate_fallback_gemini():
    """_activate_fallback() setzt Gemini-spezifische Env-Vars."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "gemini-2.0-flash",
        "HAANA_FALLBACK_PROVIDER_TYPE": "gemini",
        "HAANA_FALLBACK_API_KEY": "gem-key",
    })

    await agent._activate_fallback()

    assert agent.model == "gemini-2.0-flash"
    assert agent._env.get("GEMINI_API_KEY") == "gem-key"
    assert agent._env.get("GEMINI_MODEL") == "gemini-2.0-flash"
    assert agent._cli_model is None


@pytest.mark.asyncio
async def test_activate_fallback_only_once():
    """_activate_fallback() funktioniert nur einmal (kein Doppel-Fallback)."""
    agent = _make_agent({
        "HAANA_FALLBACK_MODEL": "fb-model",
        "HAANA_FALLBACK_PROVIDER_TYPE": "anthropic",
    })

    result1 = await agent._activate_fallback()
    assert result1 is True

    result2 = await agent._activate_fallback()
    assert result2 is False


@pytest.mark.asyncio
async def test_activate_fallback_clears_old_provider_env():
    """_activate_fallback() entfernt alte Provider-Env-Vars."""
    agent = _make_agent({
        "OPENAI_API_KEY": "old-key",
        "OPENAI_MODEL": "old-model",
        "HAANA_FALLBACK_MODEL": "claude-haiku",
        "HAANA_FALLBACK_PROVIDER_TYPE": "anthropic",
        "HAANA_FALLBACK_API_KEY": "new-key",
    })

    await agent._activate_fallback()

    # Alte OpenAI-Vars müssen weg sein
    assert "OPENAI_API_KEY" not in agent._env
    assert "OPENAI_MODEL" not in agent._env
    # Neue Anthropic-Vars gesetzt
    assert agent._env.get("ANTHROPIC_API_KEY") == "new-key"
