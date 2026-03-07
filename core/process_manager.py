"""
HAANA Agent Process Manager – Abstraktion für Agent-Lifecycle

Zwei Implementierungen:
  DockerAgentManager   – Standalone/Dev: Container via Docker SDK (wie bisher)
  InProcessAgentManager – Add-on: Agents als Python-Objekte im selben Prozess

Auto-Detection via HAANA_MODE env oder Docker-Socket-Verfügbarkeit.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentManager(Protocol):
    """Protocol für Agent-Lifecycle-Management."""

    async def start_agent(self, user: dict, cfg: dict) -> dict:
        """Startet einen Agent für einen User. Gibt {"ok": bool, ...} zurück."""
        ...

    async def stop_agent(self, instance: str, force: bool = False) -> dict:
        """Stoppt einen Agent. force=True → sofortiges Beenden."""
        ...

    async def restart_agent(self, instance: str) -> dict:
        """Neustart eines Agents (stop + start mit aktueller Config)."""
        ...

    def agent_status(self, instance: str) -> str:
        """Status: 'running', 'exited', 'absent', 'unknown'."""
        ...

    def agent_url(self, instance: str) -> str:
        """HTTP-URL zum Agent-API Endpunkt."""
        ...

    def list_agents(self) -> dict[str, str]:
        """Alle bekannten Agents mit Status. {instance: status}."""
        ...

    async def remove_agent(self, instance: str) -> dict:
        """Agent vollständig entfernen (Container/Prozess + Cleanup)."""
        ...


def _build_agent_env(user: dict, cfg: dict, resolve_llm_fn, find_ollama_url_fn) -> dict:
    """Baut die Env-Vars für einen Agent-Prozess auf.

    Gemeinsame Logik für Docker- und InProcess-Manager.
    resolve_llm_fn: (llm_id, cfg) -> (llm_dict, provider_dict)
    find_ollama_url_fn: (cfg) -> str
    """
    uid = user["id"]
    api_port = user.get("api_port", 8001)
    write_scopes = f"{uid}_memory,household_memory"
    read_scopes = f"{uid}_memory,household_memory"

    primary_llm_id = user.get("primary_llm", "")
    extract_llm_id = user.get("extraction_llm", "") or cfg.get("memory", {}).get("extraction_llm", "")
    p_llm, p_prov = resolve_llm_fn(primary_llm_id, cfg)
    e_llm, e_prov = resolve_llm_fn(extract_llm_id, cfg)

    ollama_url = find_ollama_url_fn(cfg)
    emb = cfg.get("embedding", {})

    env = {
        "HAANA_INSTANCE":        uid,
        "HAANA_API_PORT":        str(api_port),
        "HAANA_LOG_DIR":         os.environ.get("HAANA_LOG_DIR", "/data/logs"),
        "HAANA_WRITE_SCOPES":    write_scopes,
        "HAANA_READ_SCOPES":     read_scopes,
        "HAANA_MODEL":           p_llm.get("model", "claude-sonnet-4-6"),
        "HAANA_MEMORY_MODEL":    e_llm.get("model", "ministral-3-32k:3b"),
        "HAANA_WINDOW_SIZE":     str(cfg.get("memory", {}).get("window_size", 20)),
        "HAANA_WINDOW_MINUTES":  str(cfg.get("memory", {}).get("window_minutes", 60)),
        "HAANA_EMBEDDING_MODEL": emb.get("model", "bge-m3"),
        "HAANA_EMBEDDING_DIMS":  str(emb.get("dims", 1024)),
        "QDRANT_URL":            cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333"),
        "OLLAMA_URL":            ollama_url,
        "HA_URL":                cfg.get("services", {}).get("ha_url", ""),
        "HA_TOKEN":              cfg.get("services", {}).get("ha_token", ""),
    }

    # HA MCP-Server URL
    services = cfg.get("services", {})
    if services.get("ha_mcp_enabled"):
        ha_mcp_type = services.get("ha_mcp_type", "extended")
        ha_mcp_url = services.get("ha_mcp_url", "").strip()
        if not ha_mcp_url:
            ha_url = services.get("ha_url", "").rstrip("/")
            if ha_url and ha_mcp_type == "builtin":
                ha_mcp_url = f"{ha_url}/mcp_server/sse"
        if ha_mcp_url:
            env["HA_MCP_URL"] = ha_mcp_url
            env["HA_MCP_TYPE"] = ha_mcp_type

    # Provider-spezifische Env-Vars
    is_minimax = p_prov.get("type") == "minimax"
    if is_minimax:
        env["ANTHROPIC_BASE_URL"] = p_prov.get("url") or "https://api.minimax.io/anthropic"
        env["ANTHROPIC_AUTH_TOKEN"] = p_prov.get("key", "")
        env["ANTHROPIC_MODEL"] = p_llm.get("model", "MiniMax-M2.5")
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    elif p_prov.get("type") == "ollama":
        # Ollama: OpenAI-kompatiblen Endpoint nutzen (/v1/)
        ollama_base = (p_prov.get("url") or ollama_url or "http://localhost:11434").rstrip("/")
        env["OPENAI_BASE_URL"] = f"{ollama_base}/v1"
        env["OPENAI_API_KEY"] = "ollama"  # Dummy – Ollama braucht keinen Key, CLI verlangt einen
        env["OPENAI_MODEL"] = p_llm.get("model", "ministral-3-32k:3b")
    elif p_prov.get("type") == "openai":
        if p_prov.get("key"):
            env["OPENAI_API_KEY"] = p_prov["key"]
        if p_prov.get("url"):
            env["OPENAI_BASE_URL"] = p_prov["url"]
        env["OPENAI_MODEL"] = p_llm.get("model", "gpt-4o")
    elif p_prov.get("type") == "gemini":
        if p_prov.get("key"):
            env["GEMINI_API_KEY"] = p_prov["key"]
        env["GEMINI_MODEL"] = p_llm.get("model", "gemini-2.0-flash")
    else:
        if p_prov.get("key"):
            env["ANTHROPIC_API_KEY"] = p_prov["key"]
        if p_prov.get("url"):
            env["ANTHROPIC_BASE_URL"] = p_prov["url"]

    return env


class DockerAgentManager:
    """Agent-Management via Docker SDK (Standalone/Development-Modus)."""

    def __init__(self, docker_client, *, host_base: str, data_volume: str,
                 compose_network: str, agent_image: str,
                 resolve_llm_fn, find_ollama_url_fn):
        self._client = docker_client
        self._host_base = host_base
        self._data_volume = data_volume
        self._compose_network = compose_network
        self._agent_image = agent_image
        self._resolve_llm = resolve_llm_fn
        self._find_ollama_url = find_ollama_url_fn

    def _get_image(self, instance: str = "") -> str:
        """Agent-Image auto-detektieren. Bevorzugt Image mit passendem Namen."""
        if not self._client:
            return self._agent_image
        try:
            # Erst: exaktes Image für diese Instanz suchen
            if instance:
                for tag in [f"haana-instanz-{instance}:latest", f"haana-instanz-{instance}"]:
                    try:
                        self._client.images.get(tag)
                        return tag
                    except Exception:
                        pass
            # Fallback: Image von einem laufenden Instanz-Container
            containers = self._client.containers.list(all=True)
            for c in containers:
                if "instanz-" in c.name or "haana-instanz" in c.name:
                    return c.image.tags[0] if c.image.tags else self._agent_image
        except Exception:
            pass
        return self._agent_image

    def _get_network(self) -> str:
        """Docker-Netzwerk auto-detektieren."""
        if not self._client:
            return self._compose_network
        for net_name in [self._compose_network, "haana-default", "haana_default", "bridge"]:
            try:
                self._client.networks.get(net_name)
                return net_name
            except Exception:
                pass
        return self._compose_network

    def _container_name(self, user_or_instance) -> str:
        if isinstance(user_or_instance, dict):
            return user_or_instance.get("container_name", f"haana-instanz-{user_or_instance['id']}-1")
        return f"haana-instanz-{user_or_instance}-1"

    async def start_agent(self, user: dict, cfg: dict) -> dict:
        if not self._client:
            return {"ok": False, "error": "Docker nicht verfügbar (kein Socket gemountet?)"}

        uid = user["id"]
        api_port = user["api_port"]
        container_name = self._container_name(user)

        env = _build_agent_env(user, cfg, self._resolve_llm, self._find_ollama_url)
        image = self._get_image(uid)
        network = self._get_network()

        # Host-Pfade
        host_claude_md = f"{self._host_base}/instanzen/{uid}/CLAUDE.md"
        host_skills = f"{self._host_base}/skills"
        host_claude_config = "/root/.claude"

        volumes = {
            host_claude_md:    {"bind": "/app/CLAUDE.md", "mode": "ro"},
            host_skills:       {"bind": "/app/skills",     "mode": "ro"},
            self._data_volume: {"bind": "/data",           "mode": "rw"},
        }

        # Provider aus env rekonstruieren für OAuth-Mount
        p_prov = self._resolve_llm(user.get("primary_llm", ""), cfg)[1]
        is_minimax = p_prov.get("type") == "minimax"
        is_oauth = p_prov.get("type") == "anthropic" and p_prov.get("auth_method") == "oauth"

        if is_oauth and p_prov.get("oauth_dir"):
            # oauth_dir ist ein Container-interner Pfad (z.B. /data/claude-auth/anthropic-1).
            # Da haana-data bereits unter /data gemountet wird, setzen wir eine Env-Var
            # damit der Agent beim Start die Credentials symlinkt.
            oauth_data_path = p_prov["oauth_dir"]  # e.g. /data/claude-auth/anthropic-1
            env["HAANA_OAUTH_DIR"] = oauth_data_path
        elif not is_minimax and p_prov.get("type") not in ("openai", "gemini"):
            volumes[host_claude_config] = {"bind": "/home/haana/.claude", "mode": "rw"}
            claude_json_host = Path("/root/.claude.json")
            try:
                has_claude_json = claude_json_host.is_file()
            except PermissionError:
                has_claude_json = False
            if has_claude_json:
                volumes[str(claude_json_host)] = {"bind": "/home/haana/.claude.json", "mode": "rw"}

        try:
            # Alten Container entfernen
            try:
                old = self._client.containers.get(container_name)
                old.stop(timeout=5)
                old.remove()
            except Exception:
                pass

            container = self._client.containers.run(
                image,
                name=container_name,
                environment=env,
                volumes=volumes,
                ports={f"{api_port}/tcp": api_port},
                network=network,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
            )
            return {"ok": True, "container_id": container.short_id, "container_name": container_name}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    async def stop_agent(self, instance: str, force: bool = False) -> dict:
        if not self._client:
            return {"ok": False, "error": "Docker nicht verfügbar"}
        container_name = self._container_name(instance)
        try:
            c = self._client.containers.get(container_name)
            if force:
                c.kill()
            else:
                c.stop(timeout=10)
            return {"ok": True, "container": container_name}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def restart_agent(self, instance: str) -> dict:
        if not self._client:
            return {"ok": False, "error": "Docker nicht verfügbar"}
        container_name = self._container_name(instance)
        try:
            c = self._client.containers.get(container_name)
            c.restart(timeout=10)
            return {"ok": True, "container": container_name}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def agent_status(self, instance: str) -> str:
        if not self._client:
            return "unknown"
        container_name = self._container_name(instance)
        try:
            c = self._client.containers.get(container_name)
            return c.status
        except Exception:
            return "absent"

    def agent_url(self, instance: str) -> str:
        container_name = self._container_name(instance)
        # Versuche Port aus bekannten Instanzen
        port_map = {"alice": 8001, "bob": 8002, "ha-assist": 8003, "ha-advanced": 8004}
        port = port_map.get(instance, 8001)
        return f"http://{container_name}:{port}"

    def list_agents(self) -> dict[str, str]:
        if not self._client:
            return {}
        result = {}
        try:
            containers = self._client.containers.list(all=True)
            for c in containers:
                if "instanz-" in c.name or "haana-instanz" in c.name:
                    # Extract instance name from container name
                    name = c.name.replace("haana-instanz-", "").replace("-1", "")
                    result[name] = c.status
        except Exception:
            pass
        return result

    async def remove_agent(self, instance: str) -> dict:
        if not self._client:
            return {"ok": False, "error": "Docker nicht verfügbar"}
        container_name = self._container_name(instance)
        try:
            c = self._client.containers.get(container_name)
            c.stop(timeout=5)
            c.remove()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


class InProcessAgentManager:
    """Agent-Management im selben Prozess (HA Add-on Modus).

    Agents laufen als HaanaAgent-Objekte mit eigener FastAPI Sub-App.
    """

    def __init__(self, *, main_app, resolve_llm_fn, find_ollama_url_fn,
                 inst_dir: Path, data_root: Path):
        self._agents: dict[str, object] = {}  # instance -> HaanaAgent
        self._api_apps: dict[str, object] = {}  # instance -> FastAPI sub-app
        self._main_app = main_app
        self._resolve_llm = resolve_llm_fn
        self._find_ollama_url = find_ollama_url_fn
        self._inst_dir = inst_dir
        self._data_root = data_root

    async def start_agent(self, user: dict, cfg: dict) -> dict:
        uid = user["id"]

        # Bereits laufend? Erst stoppen
        if uid in self._agents:
            await self.stop_agent(uid)

        env = _build_agent_env(user, cfg, self._resolve_llm, self._find_ollama_url)

        # Env-Vars setzen für diesen Agent (In-Process: teilen sich os.environ)
        # Wir setzen die Vars temporär für die Agent-Initialisierung
        old_env = {}
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            from core.agent import HaanaAgent
            from core.api import create_api

            agent = HaanaAgent(uid)
            api = create_api(agent)

            self._agents[uid] = agent
            self._api_apps[uid] = api

            # Sub-App mounten
            prefix = f"/agent/{uid}"
            self._main_app.mount(prefix, api)
            logger.info(f"[InProcess] Agent '{uid}' gestartet unter {prefix}")

            return {"ok": True, "mode": "in-process", "url": prefix}
        except Exception as e:
            logger.error(f"[InProcess] Agent '{uid}' Start fehlgeschlagen: {e}")
            return {"ok": False, "error": str(e)[:300]}
        finally:
            # Env wiederherstellen
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    async def stop_agent(self, instance: str, force: bool = False) -> dict:
        agent = self._agents.pop(instance, None)
        self._api_apps.pop(instance, None)
        if not agent:
            return {"ok": False, "error": f"Agent '{instance}' nicht aktiv"}

        try:
            if hasattr(agent, 'shutdown'):
                await agent.shutdown()
        except Exception as e:
            logger.warning(f"[InProcess] Shutdown '{instance}': {e}")

        # Sub-App aus Routes entfernen
        prefix = f"/agent/{instance}"
        self._main_app.routes[:] = [
            r for r in self._main_app.routes
            if not (hasattr(r, 'path') and r.path.startswith(prefix))
        ]

        logger.info(f"[InProcess] Agent '{instance}' gestoppt")
        return {"ok": True}

    async def restart_agent(self, instance: str) -> dict:
        # Für Restart brauchen wir user + cfg
        return {"ok": False, "error": "restart_agent benötigt user+cfg, nutze start_agent stattdessen"}

    def agent_status(self, instance: str) -> str:
        if instance in self._agents:
            return "running"
        return "absent"

    def agent_url(self, instance: str) -> str:
        if instance in self._agents:
            return f"/agent/{instance}"
        return ""

    def list_agents(self) -> dict[str, str]:
        return {k: "running" for k in self._agents}

    async def remove_agent(self, instance: str) -> dict:
        return await self.stop_agent(instance)


def detect_mode() -> str:
    """Erkennt den Betriebsmodus: 'standalone' oder 'addon'."""
    mode = os.environ.get("HAANA_MODE", "auto")
    if mode != "auto":
        return mode
    # Auto-detect: Docker-Socket vorhanden → standalone
    if Path("/var/run/docker.sock").exists():
        return "standalone"
    return "addon"


def create_agent_manager(mode: str, *, main_app=None, docker_client=None,
                         resolve_llm_fn=None, find_ollama_url_fn=None,
                         **kwargs) -> AgentManager:
    """Factory: Erstellt den passenden AgentManager."""
    if mode == "standalone":
        return DockerAgentManager(
            docker_client,
            host_base=kwargs.get("host_base", os.environ.get("HAANA_HOST_BASE", "/opt/haana")),
            data_volume=kwargs.get("data_volume", os.environ.get("HAANA_DATA_VOLUME", "haana_haana-data")),
            compose_network=kwargs.get("compose_network", os.environ.get("HAANA_COMPOSE_NETWORK", "haana_default")),
            agent_image=kwargs.get("agent_image", os.environ.get("HAANA_AGENT_IMAGE", "haana-instanz-alice")),
            resolve_llm_fn=resolve_llm_fn,
            find_ollama_url_fn=find_ollama_url_fn,
        )
    else:
        return InProcessAgentManager(
            main_app=main_app,
            resolve_llm_fn=resolve_llm_fn,
            find_ollama_url_fn=find_ollama_url_fn,
            inst_dir=kwargs.get("inst_dir", Path(os.environ.get("HAANA_INST_DIR", "/app/instanzen"))),
            data_root=kwargs.get("data_root", Path(os.environ.get("HAANA_DATA_DIR", "/data"))),
        )
