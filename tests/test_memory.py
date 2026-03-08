"""Tests für core/memory.py – Sliding Window, Scope-Klassifikation, Persistenz."""
import time
import core.memory as m


# ── WindowEntry ───────────────────────────────────────────────────────────────

def test_window_entry_defaults():
    e = m._WindowEntry(user="hi", assistant="hey", scope="test_memory")
    assert e.scope == "test_memory"
    assert e.extracting is False
    assert e.classify_retries == 0


def test_window_entry_scope_none():
    e = m._WindowEntry(user="hi", assistant="hey", scope=None)
    assert e.scope is None
    assert e.classify_retries == 0


# ── ConversationWindow ────────────────────────────────────────────────────────

def test_window_add_and_size():
    w = m.ConversationWindow(max_messages=5)
    w.add("hi", "hey", "test_memory")
    assert w.size() == 1


def test_window_overflow():
    w = m.ConversationWindow(max_messages=2, max_age_minutes=0, min_messages=1)
    w.add("a", "b", "s")
    w.add("c", "d", "s")
    # Drittes Element: erstes sollte overflow werden (min_messages=1 schützt nur letztes)
    overflow = w.add("e", "f", "s")
    assert len(overflow) >= 1
    assert overflow[0].user == "a"


def test_window_no_overflow_within_limits():
    w = m.ConversationWindow(max_messages=10, max_age_minutes=60, min_messages=5)
    for i in range(5):
        overflow = w.add(f"u{i}", f"a{i}", "s")
    assert len(overflow) == 0


def test_window_mark_extracted():
    w = m.ConversationWindow(max_messages=1, max_age_minutes=0, min_messages=0)
    w.add("a", "b", "s")
    overflow = w.add("c", "d", "s")
    assert len(overflow) == 1
    w.mark_extracted(overflow[0])
    assert w.size() == 1  # nur "c/d" bleibt


def test_window_mark_failed():
    w = m.ConversationWindow(max_messages=1, max_age_minutes=0, min_messages=0)
    w.add("a", "b", "s")
    overflow = w.add("c", "d", "s")
    entry = overflow[0]
    assert entry.extracting is True
    w.mark_failed(entry)
    assert entry.extracting is False
    assert w.size() == 2  # bleibt im Window


# ── Persistenz ────────────────────────────────────────────────────────────────

def test_serialization_roundtrip():
    w = m.ConversationWindow(max_messages=10)
    w.add("hi", "hey", "test_memory")
    w.add("foo", "bar", None)
    w._entries[-1].classify_retries = 3

    d = w.to_dict()
    assert d["version"] == 1
    assert len(d["entries"]) == 2
    assert d["entries"][0]["scope"] == "test_memory"
    assert d["entries"][1]["scope"] is None
    assert d["entries"][1]["classify_retries"] == 3

    w2 = m.ConversationWindow(max_messages=10)
    w2.from_dict(d)
    assert w2.size() == 2
    assert w2._entries[0].scope == "test_memory"
    assert w2._entries[1].scope is None
    assert w2._entries[1].classify_retries == 3


def test_backwards_compat_old_format():
    """Alte Context-Dateien ohne classify_retries und mit scope immer gesetzt."""
    old_data = {
        "version": 1, "saved_at": 0,
        "config": {"max_messages": 20, "max_age_minutes": 60, "min_messages": 5},
        "entries": [
            {"user": "hi", "assistant": "hey", "scope": "alice_memory", "timestamp": time.time()}
        ],
    }
    w = m.ConversationWindow()
    w.from_dict(old_data)
    assert w._entries[0].classify_retries == 0
    assert w._entries[0].scope == "alice_memory"


def test_pending_extraction_roundtrip():
    w = m.ConversationWindow(max_messages=10)
    w.add("a", "b", "s")
    w._entries[0].extracting = True

    d = w.to_dict()
    assert d["entries"][0]["pending_extraction"] is True

    w2 = m.ConversationWindow(max_messages=10)
    pending = w2.from_dict(d)
    assert len(pending) >= 1
    assert pending[0].user == "a"


# ── _resolve_scope ────────────────────────────────────────────────────────────

def _make_memory(write_scopes, instance="test"):
    """Helper: HaanaMemory ohne echte Mem0/Qdrant-Verbindung."""
    mem = m.HaanaMemory.__new__(m.HaanaMemory)
    mem.instance = instance
    mem.write_scopes = set(write_scopes)
    mem.read_scopes = set(write_scopes)
    mem._qdrant_url = ""
    mem._ollama_url = ""
    mem._memory_model = "ministral-3-32k:3b"
    mem._embed_model = "bge-m3"
    mem._embed_dims = 1024
    mem._extract_url = ""
    mem._extract_key = ""
    mem._extract_type = "ollama"
    mem._extract_oauth_dir = ""
    mem._use_cli_extraction = False
    mem._extract_limiter = m._NOOP_LIMITER
    mem._context_enrichment = False
    mem._consecutive_write_errors = 0
    mem._rate_limit_warned = False
    return mem


def test_resolve_scope_explicit():
    mem = _make_memory(["test_memory", "household_memory"])
    assert mem._resolve_scope("text", "household_memory") == "household_memory"


def test_resolve_scope_regex_match():
    mem = _make_memory(["alice_memory", "household_memory"])
    assert mem._resolve_scope("Gespeichert in household_memory.", None) == "household_memory"


def test_resolve_scope_single_write_scope():
    mem = _make_memory(["test_memory"])
    assert mem._resolve_scope("beliebiger text", None) == "test_memory"


def test_resolve_scope_none_without_llm():
    """Ohne Ollama und ohne Regex-Match: None statt blind fallback."""
    mem = _make_memory(["test_memory", "household_memory"])
    result = mem._resolve_scope("kein scope erkennbar", None)
    assert result is None


def test_resolve_scope_regex_not_in_write_scopes():
    """Regex-Match ignoriert wenn Scope nicht in write_scopes."""
    mem = _make_memory(["test_memory"])
    result = mem._resolve_scope("Text mit household_memory erwähnt", None)
    # household_memory nicht in write_scopes → kein Match
    # Nur ein write_scope → eindeutig
    assert result == "test_memory"


# ── Env-Isolation Tests ──────────────────────────────────────────────────────

def test_memory_captures_env_at_init():
    """HaanaMemory speichert Env-Vars bei Konstruktion."""
    import os
    old = os.environ.get("OLLAMA_URL")
    try:
        os.environ["OLLAMA_URL"] = "http://test-ollama:11434"
        os.environ["QDRANT_URL"] = "http://test-qdrant:6333"
        mem = m.HaanaMemory("test-env")
        assert mem._ollama_url == "http://test-ollama:11434"
        assert mem._qdrant_url == "http://test-qdrant:6333"
    finally:
        if old is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old
        os.environ.pop("QDRANT_URL", None)


def test_classify_scope_uses_captured_ollama_url():
    """_classify_scope_via_llm nutzt die bei Init gespeicherte URL."""
    mem = _make_memory(["test_memory", "household_memory"])
    # _ollama_url ist leer → sollte sofort None zurueckgeben
    assert mem._ollama_url == ""
    result = mem._classify_scope_via_llm("test text")
    assert result is None


# ── Context-aware Extraction Tests ───────────────────────────────────────────

def test_build_extraction_context_with_surrounding():
    """Kontext wird aus umgebenden Window-Einträgen aufgebaut."""
    mem = _make_memory(["test_memory"])
    mem._memories = {}
    mem._window = m.ConversationWindow(max_messages=20)
    mem._pending_tasks = set()
    mem._last_search_hits = 0

    mem._window.add("Unsere Katze heißt Mystique", "Schöner Name!", "test_memory")
    mem._window.add("Sie ist eine Maine Coon", "Toll!", "test_memory")
    mem._window.add("Und 3 Jahre alt", "Notiert!", "test_memory")

    target = mem._window._entries[1]  # "Sie ist eine Maine Coon"
    context = mem._build_extraction_context(target)

    assert "Mystique" in context  # Kontext von davor
    assert ">>> AKTUELLE NACHRICHT:" in context  # Marker
    assert "Maine Coon" in context  # Ziel-Nachricht
    assert "3 Jahre alt" in context  # Kontext von danach


def test_build_extraction_context_no_context_single_entry():
    """Kein Kontext wenn nur ein Eintrag im Window."""
    mem = _make_memory(["test_memory"])
    mem._memories = {}
    mem._window = m.ConversationWindow(max_messages=20)
    mem._pending_tasks = set()
    mem._last_search_hits = 0

    mem._window.add("Hallo", "Hi!", "test_memory")
    target = mem._window._entries[0]
    context = mem._build_extraction_context(target)
    assert context == ""


def test_build_extraction_context_respects_limits():
    """Kontext begrenzt auf context_before=3 und context_after=2."""
    mem = _make_memory(["test_memory"])
    mem._memories = {}
    mem._window = m.ConversationWindow(max_messages=20)
    mem._pending_tasks = set()
    mem._last_search_hits = 0

    # 8 Einträge hinzufügen
    for i in range(8):
        mem._window.add(f"msg_{i}", f"resp_{i}", "test_memory")

    target = mem._window._entries[4]  # msg_4
    context = mem._build_extraction_context(target, context_before=2, context_after=1)

    assert "msg_1" not in context  # zu weit weg (idx 1, target idx 4, limit 2)
    assert "msg_2" in context      # context_before=2
    assert "msg_3" in context      # context_before=2
    assert "msg_5" in context      # context_after=1
    assert "msg_6" not in context  # zu weit weg


def test_build_extraction_context_entry_not_in_window():
    """Gibt leeren String zurück wenn Entry nicht im Window ist."""
    mem = _make_memory(["test_memory"])
    mem._memories = {}
    mem._window = m.ConversationWindow(max_messages=20)
    mem._pending_tasks = set()
    mem._last_search_hits = 0

    orphan = m._WindowEntry(user="orphan", assistant="resp", scope="test_memory")
    context = mem._build_extraction_context(orphan)
    assert context == ""


# ── Context Preservation Tests ───────────────────────────────────────────────

def test_window_persists_through_shutdown_restart(tmp_path):
    """Window-Einträge bleiben nach Serialisierung erhalten (kein flush_all)."""
    w = m.ConversationWindow(max_messages=20, max_age_minutes=60)
    w.add("msg1", "resp1", "test_memory")
    w.add("msg2", "resp2", "test_memory")
    w.add("msg3", "resp3", "test_memory")

    # Simuliert Shutdown: save ohne flush
    data = w.to_dict()
    assert len(data["entries"]) == 3

    # Simuliert Restart: laden in neues Window
    w2 = m.ConversationWindow(max_messages=20, max_age_minutes=60)
    pending = w2.from_dict(data)
    assert w2.size() == 3
    assert w2._entries[0].user == "msg1"
    assert w2._entries[2].user == "msg3"
    # Keine pending Extraktionen (alles innerhalb der Limits)
    assert len(pending) == 0


# ── Embedding-Provider in _build_mem0_config ─────────────────────────────────

def test_build_mem0_config_embed_ollama():
    cfg = m._build_mem0_config(
        "test_scope", qdrant_url="http://localhost:6333",
        ollama_url="http://localhost:11434", memory_llm="test",
        embed_model="bge-m3", embed_dims=1024, embed_type="ollama",
    )
    assert cfg is not None
    assert cfg["embedder"]["provider"] == "ollama"
    assert cfg["embedder"]["config"]["model"] == "bge-m3"
    assert cfg["embedder"]["config"]["ollama_base_url"] == "http://localhost:11434"


def test_build_mem0_config_embed_openai():
    cfg = m._build_mem0_config(
        "test_scope", qdrant_url="http://localhost:6333",
        ollama_url="http://localhost:11434", memory_llm="test",
        embed_model="text-embedding-3-small", embed_dims=1536,
        embed_type="openai", embed_key="sk-test123",
    )
    assert cfg is not None
    assert cfg["embedder"]["provider"] == "openai"
    assert cfg["embedder"]["config"]["model"] == "text-embedding-3-small"
    assert cfg["embedder"]["config"]["api_key"] == "sk-test123"
    assert cfg["embedder"]["config"]["embedding_dims"] == 1536


def test_build_mem0_config_embed_openai_custom_url():
    cfg = m._build_mem0_config(
        "test_scope", qdrant_url="http://localhost:6333",
        ollama_url="http://localhost:11434", memory_llm="test",
        embed_model="text-embedding-3-small", embed_dims=1536,
        embed_type="openai", embed_key="sk-test", embed_url="https://custom.api.com",
    )
    assert cfg["embedder"]["config"]["openai_base_url"] == "https://custom.api.com"


def test_build_mem0_config_embed_gemini():
    cfg = m._build_mem0_config(
        "test_scope", qdrant_url="http://localhost:6333",
        ollama_url="http://localhost:11434", memory_llm="test",
        embed_model="models/text-embedding-004", embed_dims=768,
        embed_type="gemini", embed_key="AIza-test",
    )
    assert cfg is not None
    assert cfg["embedder"]["provider"] == "gemini"
    assert cfg["embedder"]["config"]["api_key"] == "AIza-test"


def test_build_mem0_config_embed_openai_no_key_returns_none():
    cfg = m._build_mem0_config(
        "test_scope", qdrant_url="http://localhost:6333",
        ollama_url="http://localhost:11434", memory_llm="test",
        embed_type="openai", embed_key="",
    )
    assert cfg is None
