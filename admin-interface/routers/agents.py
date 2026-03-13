"""Agent-Instance management: start/stop/restart, health, qdrant."""

from fastapi import APIRouter, HTTPException

from .deps import (
    load_config, get_all_instances, get_agent_url,
    agent_manager, docker_client, INSTANCES,
)

router = APIRouter(tags=["agents"])


@router.post("/api/instances/{instance}/restart")
async def restart_instance(instance: str):
    """Agent-Instanz neu starten."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    if not agent_manager:
        raise HTTPException(503, "Agent-Manager nicht verfügbar")
    cfg = load_config()
    for user in cfg.get("users", []):
        if user["id"] == instance:
            return await agent_manager.start_agent(user, cfg)
    return await agent_manager.restart_agent(instance)


@router.post("/api/instances/{instance}/stop")
async def stop_instance(instance: str):
    """Agent-Instanz graceful stoppen."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    if not agent_manager:
        raise HTTPException(503, "Agent-Manager nicht verfügbar")
    return await agent_manager.stop_agent(instance)


@router.post("/api/instances/{instance}/force-stop")
async def force_stop_instance(instance: str):
    """Agent-Instanz sofort beenden."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    if not agent_manager:
        raise HTTPException(503, "Agent-Manager nicht verfügbar")
    return await agent_manager.stop_agent(instance, force=True)


@router.post("/api/instances/restart-all")
async def restart_all_instances():
    """Alle Agent-Instanzen mit aktueller Config neu starten."""
    if not agent_manager:
        raise HTTPException(503, "Agent-Manager nicht verfügbar")
    cfg = load_config()
    results = {}

    for user in cfg.get("users", []):
        uid = user["id"]
        result = await agent_manager.start_agent(user, cfg)
        results[uid] = result

    for inst in INSTANCES:
        if inst not in results:
            result = await agent_manager.restart_agent(inst)
            results[inst] = result

    all_ok = all(r.get("ok", False) for r in results.values())
    return {"ok": all_ok, "results": results}


@router.post("/api/qdrant/restart")
async def restart_qdrant():
    """Qdrant-Container neu starten."""
    if not docker_client:
        return {"ok": False, "error": "Docker nicht verfügbar"}
    try:
        c = docker_client.containers.get("haana-qdrant-1")
        c.restart(timeout=10)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.delete("/api/qdrant/collections/{name}")
async def delete_qdrant_collection(name: str):
    """Löscht eine Qdrant-Collection."""
    import httpx
    cfg = load_config()
    qdrant_url = cfg.get("services", {}).get("qdrant_url", "http://qdrant:6333")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{qdrant_url}/collections/{name}")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/api/agent-health/{instance}")
async def agent_health(instance: str):
    """Prüft ob ein Agent-Container erreichbar ist."""
    if instance not in get_all_instances():
        raise HTTPException(404)
    agent_url = get_agent_url(instance)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{agent_url}/health")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}
