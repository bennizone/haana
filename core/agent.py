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
import signal
import time
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    CLIJSONDecodeError,
)
from claude_agent_sdk.types import McpHttpServerConfig
from core.memory import HaanaMemory
import core.logger as haana_log

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

        # Memory-Layer (Mem0 + Qdrant + Sliding Window)
        self.memory = HaanaMemory(instance_name)

        # Pfad für Window-Persistenz
        self._context_path = Path("data") / "context" / f"{instance_name}.json"

        # MCP-Server für Custom Tools (Phase 2+: HA, Trilium, Kalender, ...)
        self._mcp_servers: dict = {}

        # Home Assistant MCP (ha-mcp Add-on) – automatisch einbinden wenn konfiguriert
        ha_mcp_url = os.environ.get("HA_MCP_URL")
        if ha_mcp_url:
            self._mcp_servers["home-assistant"] = McpHttpServerConfig(
                type="http",
                url=ha_mcp_url,
            )
            logger.info(f"[{instance_name}] HA MCP-Server registriert: {ha_mcp_url}")

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
            permission_mode="bypassPermissions",
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
        """Schließt nur den persistenten Subprocess (kein Memory-Flush)."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.debug(f"[{self.instance}] Disconnect-Fehler (ignoriert): {e}")
            finally:
                self._client = None
            logger.info(f"[{self.instance}] Claude subprocess geschlossen")

    # ── Startup / Shutdown ────────────────────────────────────────────────────

    async def startup(self):
        """
        Startet den Agenten:
        1. Gespeicherten Window-Context laden
        2. Pending Extraktionen vom letzten Lauf sofort nachextrahieren
        """
        pending = await self.memory.load_context(self._context_path)
        if pending > 0:
            logger.info(
                f"[{self.instance}] {pending} Einträge aus letzter Session "
                "werden nachträglich extrahiert..."
            )
            await self.memory.flush_pending(timeout=60.0)
            # Context nach Extraktion aktualisieren
            self.memory.save_context(self._context_path)

    async def shutdown(self, timeout: float = 60.0):
        """
        Sauberes Shutdown:
        1. ALLE Window-Einträge zu Qdrant extrahieren (nicht nur Overflow)
        2. Window-Context final speichern (leer wenn alles extrahiert)
        3. Subprocess schließen
        """
        total = self.memory._window.size()
        if total > 0:
            print(f"  Extrahiere {total} Einträge zu Qdrant...", flush=True)
        cancelled = await self.memory.flush_all(timeout=timeout)
        if cancelled > 0:
            logger.warning(
                f"[{self.instance}] {cancelled} Extraktionen nach "
                f"{timeout}s abgebrochen und im Context-File gespeichert."
            )

        self.memory.save_context(self._context_path)
        await self.close()

    # ── Haupt-Loop ────────────────────────────────────────────────────────────

    async def run_async(self, user_message: str, channel: str = "repl") -> str:
        """
        Führt einen Agent-Turn aus.

        1. Relevante Memories aus Qdrant suchen
        2. Memory-Kontext dem Prompt voranstellen
        3. Prompt an persistenten Subprocess senden (kein neuer Prozess!)
        4. Text aus AssistantMessage-Blöcken sammeln
        5. Session-ID für Kontinuität merken
        6. Konversation non-blocking ins Sliding Window schreiben
        7. Vollständige Konversation + Tool-Calls ins Log schreiben
        """
        # Memory: relevanten Kontext laden (in Executor – blockiert Event-Loop nicht)
        loop = asyncio.get_running_loop()
        memory_context = await loop.run_in_executor(None, self.memory.search, user_message)
        parts = []
        if memory_context:
            parts.append(f"<relevante_erinnerungen>\n{memory_context}\n</relevante_erinnerungen>")
            logger.debug(f"[{self.instance}] Memory-Kontext: {len(memory_context)} Zeichen")
        if channel == "whatsapp_voice":
            parts.append(
                "<hinweis>Diese Nachricht kam als Sprachnachricht. "
                "Deine Antwort wird per Text-to-Speech vorgelesen. "
                "Antworte daher ohne Emojis, ohne Markdown-Formatierung, ohne Sonderzeichen. "
                "Schreibe natürlich und gesprächig, als würdest du sprechen. "
                "Halte dich kurz und prägnant.</hinweis>"
            )
        parts.append(user_message)
        prompt = "\n\n".join(parts)

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
        tool_calls_log: list[dict] = []
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
                        elif isinstance(block, ToolUseBlock):
                            t_tool = time.monotonic()
                            logger.info(
                                f"[{self.instance}] Tool-Aufruf: {block.name} "
                                f"| input={str(block.input)[:120]}"
                            )
                            tool_calls_log.append({
                                "tool": block.name,
                                "input": str(block.input)[:300],
                            })
                            haana_log.log_tool_call(
                                instance=self.instance,
                                tool_name=block.name,
                                tool_input=block.input,
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

        response_text = "".join(response_parts).strip()

        # Memory: Konversation async im Hintergrund speichern (non-blocking)
        if response_text:
            await self.memory.add_conversation_async(user_message, response_text)

        # Strukturiertes Log schreiben
        haana_log.log_conversation(
            instance=self.instance,
            channel=channel,
            user_message=user_message,
            assistant_response=response_text,
            latency_s=elapsed,
            memory_used=bool(memory_context),
            memory_hits=self.memory._last_search_hits,
            tool_calls=tool_calls_log,
        )

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
    """
    REPL-Schleife für lokale Tests.

    Befehle:
      /exit       – Sauberes Shutdown (pending Extraktionen abwarten, dann beenden)
      exit / quit – wie /exit
      Ctrl+C      – wie /exit

    Signal-Handler:
      SIGTERM / SIGINT → setzt shutdown_event → REPL beendet sich sauber
    """
    print(f"\nHAANA [{agent.instance}] – REPL (ClaudeSDKClient, persistenter Subprocess)")
    print(f"cwd:     {agent.cwd.resolve()}")
    print(f"context: {agent._context_path}")
    print("Beenden mit /exit, exit, quit oder Ctrl+C\n")

    shutdown_event = asyncio.Event()

    # Signal-Handler: SIGTERM + SIGINT → setzt shutdown_event
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_event.set)
        except (NotImplementedError, OSError):
            # Windows unterstützt add_signal_handler nicht
            pass

    async def _do_shutdown():
        """Shutdown-Sequenz mit Status-Output."""
        pending = agent.memory.pending_count()
        if pending > 0:
            print(f"\n  Extrahiere noch {pending} Einträge...", flush=True)
        await agent.shutdown(timeout=30.0)
        print("Tschüss!")

    try:
        while not shutdown_event.is_set():
            # Non-blocking input: gibt den Event-Loop frei für pending async Tasks
            try:
                user_input = await asyncio.to_thread(input, "Du: ")
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                break

            # Shutdown-Signal kam während input() lief
            if shutdown_event.is_set():
                break

            # Leere Eingabe → ignorieren
            if not user_input:
                continue

            # /exit Befehl
            if user_input.lower() in ("/exit", "exit", "quit"):
                break

            t0 = time.monotonic()
            response = await agent.run_async(user_input)
            elapsed = time.monotonic() - t0
            print(f"HAANA ({elapsed:.2f}s): {response}\n")

            # Context nach jeder Nachricht persistieren (atomares JSON-Write)
            agent.memory.save_context(agent._context_path)

    finally:
        await _do_shutdown()


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

    # Startup: Context laden, pending Einträge aus letzter Session extrahieren
    await agent.startup()

    api_port = int(os.environ.get("HAANA_API_PORT", "0"))
    if api_port:
        # API-Modus: nur HTTP-Server starten (kein REPL – kein TTY im Container)
        import uvicorn
        from core.api import create_api
        api_app = create_api(agent)
        api_host = os.environ.get("HAANA_API_HOST", "0.0.0.0")
        config = uvicorn.Config(
            api_app, host=api_host, port=api_port,
            log_level="warning", access_log=False,
        )
        server = uvicorn.Server(config)
        logger.info(f"[{instance}] API-Server startet auf {api_host}:{api_port}")

        # Graceful shutdown bei SIGTERM/SIGINT
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except (NotImplementedError, OSError):
                pass

        async def _run_server():
            await server.serve()
            stop_event.set()

        async def _wait_for_stop():
            await stop_event.wait()
            server.should_exit = True

        await asyncio.gather(_run_server(), _wait_for_stop())
        await agent.shutdown(timeout=30.0)
    else:
        await _repl(agent)


if __name__ == "__main__":
    asyncio.run(_main())
