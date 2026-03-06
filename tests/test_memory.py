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
