"""
HAANA Agent – Claude Agent SDK Basis

Verwendet claude_agent_sdk.query() für den Agent-Loop.
Authentifizierung läuft über die gebundelte Claude Code CLI
(Claude.ai Subscription oder API-Key in der CLI konfiguriert).
Kein direkt eingelegter API-Key im Code.

Custom Tools werden als MCP-Server eingebunden (Phase 2+).
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    CLINotFoundError,
    ProcessError,
    CLIJSONDecodeError,
)
from core.memory import HaanaMemory

logger = logging.getLogger(__name__)


class HaanaAgent:
    def __init__(self, instance_name: str):
        self.instance = instance_name
        # None → CLI-Default-Modell (abhängig von Subscription/Konfiguration)
        self.model: Optional[str] = os.environ.get("HAANA_MODEL") or None
        self.session_id: Optional[str] = None

        # Arbeitsverzeichnis = Verzeichnis mit CLAUDE.md der Instanz.
        # Claude Code CLI lädt CLAUDE.md automatisch als Projektkontext.
        for candidate in [
            Path("/app"),                         # Container: CLAUDE.md via Volume
            Path(f"instanzen/{instance_name}"),   # Lokal: direktes Instanzverzeichnis
        ]:
            if (candidate / "CLAUDE.md").exists():
                self.cwd = candidate
                logger.info(f"[{instance_name}] cwd={self.cwd.resolve()}")
                break
        else:
            raise FileNotFoundError(
                f"CLAUDE.md nicht gefunden für Instanz '{instance_name}'. "
                "Erwartet: /app/CLAUDE.md (Container) oder "
                f"instanzen/{instance_name}/CLAUDE.md (lokal)."
            )

        # Memory-Layer (Mem0 + Qdrant)
        self.memory = HaanaMemory(instance_name)

        # MCP-Server für Custom Tools (Phase 2+: HA, Trilium, Kalender, ...)
        # Format: {"server-name": McpServerConfig oder SdkMcpServer}
        self._mcp_servers: dict = {}

        # Erlaubte Built-in-Tools (Phase 1: Basis)
        self._allowed_tools: list[str] = [
            "Read",
            "Write",
            "Bash",
            "Glob",
            "Grep",
        ]

    # ── Tool-Verwaltung ───────────────────────────────────────────────────────

    def register_mcp_server(self, name: str, server_config: object):
        """
        Registriert einen MCP-Server mit Custom Tools.

        server_config: externes MCP-Server-Dict ({"type": "stdio", ...})
                       oder In-Process SdkMcpServer (via create_sdk_mcp_server).
        """
        self._mcp_servers[name] = server_config
        logger.info(f"[{self.instance}] MCP-Server registriert: {name}")

    def allow_tools(self, tools: list[str]):
        """Fügt weitere erlaubte Tools hinzu (z.B. MCP-Tools)."""
        self._allowed_tools.extend(tools)
        logger.debug(f"[{self.instance}] Tools erweitert: {tools}")

    # ── Haupt-Loop ────────────────────────────────────────────────────────────

    async def run_async(self, user_message: str) -> str:
        """
        Führt einen Agent-Turn aus.

        1. Relevante Memories aus Qdrant suchen
        2. Memory-Kontext dem Prompt voranstellen
        3. claude_agent_sdk.query() streamen
        4. Text aus AssistantMessage-Blöcken sammeln
        5. Session-ID für Kontinuität merken
        6. Konversation in Memory speichern
        """
        # Memory: relevanten Kontext laden
        memory_context = self.memory.search(user_message)

        # Prompt aufbauen: Memory als getaggter Block voranstellen
        if memory_context:
            prompt = (
                f"<relevante_erinnerungen>\n{memory_context}\n</relevante_erinnerungen>\n\n"
                f"{user_message}"
            )
            logger.debug(
                f"[{self.instance}] Memory-Kontext: {len(memory_context)} Zeichen"
            )
        else:
            prompt = user_message

        # CLAUDECODE aus dem laufenden Prozess entfernen damit der Subprocess-Agent
        # starten kann. Das SDK prüft CLAUDECODE im Parent-Prozess und blockiert
        # sonst verschachtelte Sessions. In Produktion (Docker) ist es nicht gesetzt.
        os.environ.pop("CLAUDECODE", None)
        subprocess_env = {k: v for k, v in os.environ.items()}

        # Optionen aufbauen
        options = ClaudeAgentOptions(
            cwd=self.cwd,
            model=self.model,
            max_turns=20,
            allowed_tools=self._allowed_tools,
            permission_mode="acceptEdits",
            # Session-Kontinuität: vorherigen Turn fortsetzen wenn vorhanden
            resume=self.session_id,
            # MCP-Server für Custom Tools
            mcp_servers=self._mcp_servers if self._mcp_servers else {},
            # Nur Projekteinstellungen laden (CLAUDE.md in cwd)
            setting_sources=["project"],
            # Bereinigtes Env ohne CLAUDECODE
            env=subprocess_env,
        )

        # Agent-Loop: Messages streamen
        response_parts: list[str] = []

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                            logger.debug(
                                f"[{self.instance}] TextBlock: {block.text[:80]}..."
                            )
                elif isinstance(message, ResultMessage):
                    # Session-ID für nächsten Turn merken
                    if message.session_id:
                        self.session_id = message.session_id
                        logger.debug(
                            f"[{self.instance}] Session: {self.session_id}"
                        )
                    if message.is_error:
                        logger.error(
                            f"[{self.instance}] ResultMessage Fehler: "
                            f"{message.result}"
                        )

        except CLINotFoundError:
            logger.error(
                "Claude Code CLI nicht gefunden. "
                "Bitte `claude` installieren oder in PATH legen."
            )
            return (
                "Fehler: Claude Code CLI nicht gefunden. "
                "Bitte installieren: curl -fsSL https://claude.ai/install.sh | bash"
            )
        except ProcessError as e:
            logger.error(f"[{self.instance}] CLI-Prozess Fehler (exit {e.exit_code}): {e}")
            return f"Fehler: Agent-Prozess beendet mit Code {e.exit_code}."
        except CLIJSONDecodeError as e:
            logger.error(f"[{self.instance}] JSON-Parse-Fehler: {e}")
            return "Fehler: Ungültige Antwort vom Agent."

        response_text = "".join(response_parts)

        # Memory: Konversation speichern
        if response_text:
            self.memory.add_conversation(user_message, response_text)

        return response_text or "[Keine Antwort]"

    def run(self, user_message: str) -> str:
        """Synchroner Wrapper für run_async() – für einfache Skripte."""
        return asyncio.run(self.run_async(user_message))


# ── CLI / REPL für lokale Tests ───────────────────────────────────────────────

def _setup_logging():
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _repl(agent: HaanaAgent):
    """Einfache REPL-Schleife für lokale Tests."""
    print(f"\nHAANA [{agent.instance}] – REPL (Phase 1)")
    print(f"cwd: {agent.cwd.resolve()}")
    print("Beenden mit Ctrl+C oder 'exit'\n")

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBeendet.")
            break

        if not user_input or user_input.lower() in ("exit", "quit"):
            break

        response = await agent.run_async(user_input)
        print(f"HAANA: {response}\n")


async def _main():
    _setup_logging()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    instance = os.environ.get("HAANA_INSTANCE", "alice")

    try:
        agent = HaanaAgent(instance)
    except FileNotFoundError as e:
        print(f"Fehler: {e}")
        return

    await _repl(agent)


if __name__ == "__main__":
    asyncio.run(_main())
