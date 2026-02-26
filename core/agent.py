"""
HAANA Agent – Phase 1 Basis

Einfacher Agent-Loop: Nachricht eingehend → Memory → LLM → Tool-Aufruf oder Antwort.
System-Prompt kommt aus CLAUDE.md der jeweiligen Instanz.
"""

import os
import logging
from pathlib import Path

from anthropic import Anthropic
from core.memory import HaanaMemory

logger = logging.getLogger(__name__)


class HaanaAgent:
    def __init__(self, instance_name: str):
        self.instance = instance_name
        self.model = os.environ.get("HAANA_MODEL", "claude-haiku-4-5-20251001")

        # Anthropic-Client
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # System-Prompt aus CLAUDE.md laden
        # Im Container: /app/CLAUDE.md (via Volume gemountet)
        # Lokal: instanzen/{name}/CLAUDE.md
        for candidate in [
            Path("/app/CLAUDE.md"),
            Path(f"instanzen/{instance_name}/CLAUDE.md"),
        ]:
            if candidate.exists():
                self.system_prompt = candidate.read_text(encoding="utf-8")
                logger.info(f"[{instance_name}] CLAUDE.md geladen: {candidate}")
                break
        else:
            raise FileNotFoundError(
                f"CLAUDE.md nicht gefunden für Instanz '{instance_name}'. "
                "Erwartet: /app/CLAUDE.md oder instanzen/{name}/CLAUDE.md"
            )

        # Memory
        self.memory = HaanaMemory(instance_name)

        # Tool-Registry: name → callable
        self.tools: dict[str, callable] = {}
        self._tool_schemas: list[dict] = []

        # Ping-Tool als Strukturtest (Phase 1)
        self.register_tool(
            name="ping",
            fn=lambda message="pong": f"pong: {message}",
            schema={
                "description": "Einfaches Test-Tool. Gibt eine Pong-Antwort zurück.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Optionale Nachricht",
                        }
                    },
                    "required": [],
                },
            },
        )

    def register_tool(self, name: str, fn: callable, schema: dict):
        """
        Registriert ein Tool.

        schema muss enthalten:
          - "description": str
          - "input_schema": dict (JSON Schema)
        """
        self.tools[name] = fn
        self._tool_schemas.append({"name": name, **schema})
        logger.debug(f"[{self.instance}] Tool registriert: {name}")

    def run(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """
        Haupt-Einstiegspunkt.

        1. Relevante Memories suchen
        2. System-Prompt + Memory-Kontext aufbauen
        3. Agent-Loop (Tool-Use oder direkte Antwort)
        4. Konversation in Memory speichern
        5. Antwort-Text zurückgeben
        """
        if conversation_history is None:
            conversation_history = []

        # Memory: relevanten Kontext laden
        memory_context = self.memory.search(user_message)

        system = self.system_prompt
        if memory_context:
            system += f"\n\n## Relevante Erinnerungen\n{memory_context}"
            logger.debug(f"[{self.instance}] Memory-Kontext angehängt ({len(memory_context)} Zeichen)")

        messages = conversation_history + [{"role": "user", "content": user_message}]

        response_text = self._agent_loop(system, messages)

        # Memory: Konversation speichern
        self.memory.add_conversation(user_message, response_text)

        return response_text

    def _agent_loop(self, system: str, messages: list[dict]) -> str:
        """
        Tool-Use-Loop: läuft bis stop_reason == "end_turn".
        Bei "tool_use": Tool ausführen, Ergebnis zurückschicken, weiter.
        """
        while True:
            kwargs: dict = {
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": messages,
            }
            if self._tool_schemas:
                kwargs["tools"] = self._tool_schemas

            response = self.client.messages.create(**kwargs)
            logger.debug(f"[{self.instance}] stop_reason={response.stop_reason}, tokens={response.usage}")

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            elif response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        logger.info(
                            f"[{self.instance}] Tool '{block.name}' "
                            f"inputs={block.input} → {result!r}"
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })

                messages.append({"role": "user", "content": tool_results})

            else:
                logger.warning(f"[{self.instance}] Unbekannter stop_reason: {response.stop_reason}")
                break

        return "[Keine Antwort]"

    def _execute_tool(self, name: str, inputs: dict) -> str:
        """Führt ein registriertes Tool aus."""
        if name not in self.tools:
            return f"Fehler: Tool '{name}' ist nicht registriert."
        try:
            result = self.tools[name](**inputs)
            return str(result)
        except Exception as e:
            logger.error(f"[{self.instance}] Tool '{name}' Fehler: {e}", exc_info=True)
            return f"Fehler beim Ausführen von '{name}': {e}"


# ── CLI / REPL für lokale Tests ───────────────────────────────────────────────

def _setup_logging():
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main():
    _setup_logging()

    # .env laden wenn vorhanden
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    instance = os.environ.get("HAANA_INSTANCE", "alice")
    agent = HaanaAgent(instance)

    print(f"\nHAANA [{instance}] – REPL (Phase 1)")
    print("Beenden mit Ctrl+C oder 'exit'\n")

    history: list[dict] = []

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBeendet.")
            break

        if not user_input or user_input.lower() in ("exit", "quit"):
            break

        response = agent.run(user_input, history)
        print(f"HAANA: {response}\n")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
