#!/usr/bin/env python3 -u
"""Extraction Quality Test Runner.

Usage: python3 run-test.py <test_num> <extraction_llm_id> <embed_provider_id> <embed_model> <embed_dims>

Example: python3 run-test.py 1 ministral ollama-2 bge-m3 1024
"""
import json, sys, time, subprocess
from pathlib import Path
try:
    import httpx
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

ADMIN_URL = "http://localhost:8080"
QDRANT_URL = "http://10.83.1.11:6333"
INSTANCE = "alice"
RESULTS_DIR = Path("/opt/haana/test-results/extraction-quality")

def main():
    if len(sys.argv) < 6:
        print(__doc__)
        sys.exit(1)

    test_num = int(sys.argv[1])
    extract_llm = sys.argv[2]
    embed_provider = sys.argv[3]
    embed_model = sys.argv[4]
    embed_dims = int(sys.argv[5])

    result_file = RESULTS_DIR / f"test-{test_num}.json"
    print(f"\n=== Test {test_num}: extraction_llm={extract_llm}, embedding={embed_model} ({embed_dims}d) ===\n")

    client = httpx.Client(timeout=30.0)

    # 0. Cancel any running rebuild
    try:
        client.post(f"{ADMIN_URL}/api/rebuild-cancel/{INSTANCE}")
        time.sleep(2)
    except Exception:
        pass

    # 1. Delete collections
    print("[1/7] Deleting Qdrant collections...")
    for col in ["alice_memory", "household_memory"]:
        try:
            r = client.delete(f"{QDRANT_URL}/collections/{col}")
            print(f"  {col}: deleted ({r.status_code})")
        except Exception as e:
            print(f"  {col}: {e}")

    # 2. Update config
    print("[2/7] Updating config...")
    cfg = client.get(f"{ADMIN_URL}/api/config").json()
    cfg["memory"]["extraction_llm"] = extract_llm
    cfg["memory"]["context_enrichment"] = True
    cfg["embedding"]["provider_id"] = embed_provider
    cfg["embedding"]["model"] = embed_model
    cfg["embedding"]["dims"] = embed_dims
    resp = client.post(f"{ADMIN_URL}/api/config", json=cfg)
    print(f"  Config saved: {resp.json()}")

    # 3. Restart agent
    print(f"[3/7] Restarting agent {INSTANCE}...")
    resp = client.post(f"{ADMIN_URL}/api/instances/{INSTANCE}/restart")
    print(f"  {resp.json()}")

    # 4. Wait for agent health
    print("[4/7] Waiting for agent health...")
    for i in range(90):
        try:
            r = client.get("http://localhost:8001/health")
            if r.is_success:
                print(f"  Agent healthy after {i+1}s")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("  ERROR: Agent not healthy after 90s")
        sys.exit(1)

    # 5. Trigger rebuild
    print("[5/7] Starting rebuild...")
    start_time = time.time()
    resp = client.post(
        f"{ADMIN_URL}/api/rebuild-memory/{INSTANCE}",
        json={"skip_trivial": True, "delay_ms": 500},
    )
    rebuild_resp = resp.json()
    total_entries = rebuild_resp.get("total", 0)
    print(f"  Rebuild started: {total_entries} entries")

    if not rebuild_resp.get("ok"):
        print(f"  ERROR: {rebuild_resp}")
        sys.exit(1)

    # 6. Wait for rebuild completion (poll Qdrant counts + detect stability)
    # The rebuild sends entries to the agent which processes them asynchronously.
    # We need to wait long enough for all background extractions to complete.
    print("[6/7] Waiting for rebuild completion...")
    prev_total = 0
    stable_count = 0
    STABLE_THRESHOLD = 8  # 8 consecutive polls with no change = done (2 min)
    MIN_WAIT = 120  # minimum wait before checking stability
    while True:
        time.sleep(15)
        elapsed = int(time.time() - start_time)

        counts = {}
        for col in ["alice_memory", "household_memory"]:
            try:
                r = client.get(f"{QDRANT_URL}/collections/{col}")
                counts[col] = r.json().get("result", {}).get("points_count", 0)
            except Exception:
                counts[col] = 0
        total_points = sum(counts.values())

        print(f"  [{elapsed}s] Points: alice={counts['alice_memory']} household={counts['household_memory']} total={total_points}")

        if elapsed >= MIN_WAIT and total_points == prev_total and total_points > 0:
            stable_count += 1
        else:
            stable_count = 0
        prev_total = total_points

        if stable_count >= STABLE_THRESHOLD:
            print(f"  Rebuild complete (stable for {STABLE_THRESHOLD * 15}s)")
            break

        if elapsed > 2700:
            print("  TIMEOUT after 45 minutes")
            break

    duration = int(time.time() - start_time)

    # 7. Collect results
    print("[7/7] Collecting results...")

    # Final counts
    final_counts = {}
    for col in ["alice_memory", "household_memory"]:
        try:
            r = client.get(f"{QDRANT_URL}/collections/{col}")
            final_counts[col] = r.json().get("result", {}).get("points_count", 0)
        except Exception:
            final_counts[col] = 0

    # Dump memories
    memories = {}
    for col in ["alice_memory", "household_memory"]:
        try:
            r = client.post(
                f"{QDRANT_URL}/collections/{col}/points/scroll",
                json={"limit": 1000, "with_payload": True, "with_vector": False},
            )
            points = r.json().get("result", {}).get("points", [])
            memories[col] = [
                {
                    "id": str(p.get("id", "")),
                    "memory": p.get("payload", {}).get("memory", p.get("payload", {}).get("data", "")),
                    "hash": p.get("payload", {}).get("hash", ""),
                    "created_at": p.get("payload", {}).get("created_at", ""),
                }
                for p in points
            ]
        except Exception as e:
            print(f"  Warning: Could not dump {col}: {e}")
            memories[col] = []

    result = {
        "test_number": test_num,
        "extraction_llm": extract_llm,
        "embedding_provider": embed_provider,
        "embedding_model": embed_model,
        "embedding_dims": embed_dims,
        "context_enrichment": True,
        "duration_seconds": duration,
        "rebuild_entries": total_entries,
        "points": {
            "alice_memory": final_counts["alice_memory"],
            "household_memory": final_counts["household_memory"],
            "total": sum(final_counts.values()),
        },
        "memories": memories,
    }

    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n  Results saved to {result_file}")
    print(f"  Duration: {duration}s")
    print(f"  Points: alice={final_counts['alice_memory']}, household={final_counts['household_memory']}, total={sum(final_counts.values())}")
    print(f"\n=== Test {test_num} complete ===\n")

    client.close()


if __name__ == "__main__":
    main()
