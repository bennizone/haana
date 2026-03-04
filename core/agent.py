"""
HAANA Agent – Claude Agent SDK Basis (ClaudeSDKClient)

Verwendet ClaudeSDKClient für bidirektionale Kommunikation mit einem einzigen
persistenten claude-Subprocess. Kein Subprocess-Start pro Nachricht →
kein ~5s Startup-Overhead nach der ersten Verbindung.

Authentifizierung läuft über die gebundelte Claude Code CLI
(Claude.ai Subscription oder API-Key in der CLI konfiguriert).

Custom Tools werden als MCP-Server eingebunden (Phase 2+).
"""

import os
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    CLINotFoundError,
    CLIConnectionError,
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
        self._mcp_servers: dict = {}

        # Erlaubte Built-in-Tools (Phase 1: Basis)
        self._allowed_tools: list[str] = [
            "Read",
            "Write",
            "Bash",
            "Glob",
            "Grep",
        ]

        # Persistenter Client – lazy initialisiert beim ersten run_async()
        self._client: Optional[ClaudeSDKClient] = None

    # ── Tool-Verwaltung ───────────────────────────────────────────────────────

    def register_mcp_server(self, name: str, server_config: object):
        """Registriert einen MCP-Server mit Custom Tools."""
        self._mcp_servers[name] = server_config
        logger.info(f"[{self.instance}] MCP-Server registriert: {name}")

    def allow_tools(self, tools: list[str]):
        """Fügt weitere erlaubte Tools hinzu."""
        self._allowed_tools.extend(tools)
        logger.debug(f"[{self.instance}] Tools erweitert: {tools}")

    # ── Verbindungsverwaltung ─────────────────────────────────────────────────

    def _build_options(self) -> ClaudeAgentOptions:
        """Erstellt ClaudeAgentOptions. CLAUDECODE wird entfernt damit der
        Subprocess-Agent in einer Claude Code Session starten kann."""
        os.environ.pop("CLAUDECODE", None)
        subprocess_env = dict(os.environ)
        return ClaudeAgentOptions(
            cwd=self.cwd,
            model=self.model,
            max_turns=20,
            allowed_tools=self._allowed_tools,
            permission_mode="acceptEdits",
            mcp_servers=self._mcp_servers if self._mcp_servers else {},
            setting_sources=["project"],
            env=subprocess_env,
        )

    async def _ensure_connected(self):
        """Stellt sicher dass der persistente Subprocess läuft. Lazy-Init."""
        if self._client is None:
            options = self._build_options()
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            logger.info(f"[{self.instance}] Claude subprocess gestartet")

    async def close(self):
        """Schließt den persistenten Subprocess sauber."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.debug(f"[{self.instance}] Disconnect-Fehler (ignoriert): {e}")
            finally:
                self._client = None
            logger.info(f"[{self.instance}] Claude subprocess geschlossen")

    # ── Haupt-Loop ────────────────────────────────────────────────────────────

    async def run_async(self, user_message: str) -> str:
        """
        Führt einen Agent-Turn aus.

        1. Relevante Memories aus Qdrant suchen
        2. Memory-Kontext dem Prompt voranstellen
        3. Prompt an persistenten Subprocess senden (kein neuer Prozess!)
        4. Text aus AssistantMessage-Blöcken sammeln
        5. Session-ID für Kontinuität merken
        6. Konversation in Memory speichern
        """
        # Memory: relevanten Kontext laden
        memory_context = self.memory.search(user_message)
        if memory_context:
            prompt = (
                f"<relevante_erinnerungen>\n{memory_context}\n</relevante_erinnerungen>\n\n"
                f"{user_message}"
            )
            logger.debug(f"[{self.instance}] Memory-Kontext: {len(memory_context)} Zeichen")
        else:
            prompt = user_message

        # Verbindung sicherstellen (lazy init oder nach Fehler)
        try:
            await self._ensure_connected()
        except CLINotFoundError:
            logger.error("Claude Code CLI nicht gefunden.")
            return (
                "Fehler: Claude Code CLI nicht gefunden. "
                "Bitte installieren: curl -fsSL https://claude.ai/install.sh | bash"
            )

        # Prompt senden und Antwort empfangen
        response_parts: list[str] = []
        t_start = time.monotonic()

        try:
            await self._client.query(prompt)

            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                            logger.debug(
                                f"[{self.instance}] TextBlock: {block.text[:80]}..."
                            )
                elif isinstance(message, ResultMessage):
                    if message.session_id:
                        self.session_id = message.session_id
                        logger.debug(f"[{self.instance}] Session: {self.session_id}")
                    if message.is_error:
                        logger.error(
                            f"[{self.instance}] ResultMessage Fehler: {message.result}"
                        )

        except CLINotFoundError:
            self._client = None
            logger.error("Claude Code CLI nicht gefunden.")
            return "Fehler: Claude Code CLI nicht gefunden."
        except CLIConnectionError as e:
            self._client = None
            logger.error(f"[{self.instance}] Verbindungsfehler: {e}")
            return "Fehler: Verbindung zum Agent verloren. Nächste Nachricht startet neu."
        except ProcessError as e:
            self._client = None
            logger.error(f"[{self.instance}] CLI-Prozess Fehler (exit {e.exit_code}): {e}")
            return f"Fehler: Agent-Prozess beendet mit Code {e.exit_code}."
        except CLIJSONDecodeError as e:
            logger.error(f"[{self.instance}] JSON-Parse-Fehler: {e}")
            return "Fehler: Ungültige Antwort vom Agent."

        elapsed = time.monotonic() - t_start
        logger.info(f"[{self.instance}] Antwort in {elapsed:.2f}s")

        response_text = "".join(response_parts)

        # Memory: Konversation async im Hintergrund speichern (non-blocking)
        if response_text:
            await self.memory.add_conversation_async(user_message, response_text)

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
    """Einfache REPL-Schleife für lokale Tests mit Latenz-Messung."""
    print(f"\nHAANA [{agent.instance}] – REPL (ClaudeSDKClient, persistenter Subprocess)")
    print(f"cwd: {agent.cwd.resolve()}")
    print("Beenden mit Ctrl+C oder 'exit'\n")

    try:
        while True:
            try:
                user_input = input("Du: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBeendet.")
                break

            if not user_input or user_input.lower() in ("exit", "quit"):
                break

            t0 = time.monotonic()
            response = await agent.run_async(user_input)
            elapsed = time.monotonic() - t0
            print(f"HAANA ({elapsed:.2f}s): {response}\n")
    finally:
        await agent.close()


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
