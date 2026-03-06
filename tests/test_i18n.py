"""Tests fuer i18n – Konsistenz zwischen de.json und en.json."""
import json
from pathlib import Path

import pytest

I18N_DIR = Path("/opt/haana/admin-interface/static/i18n")


def _load_i18n(lang: str) -> dict:
    """Laedt eine i18n-Datei und gibt den geparsten Dict zurueck."""
    fpath = I18N_DIR / f"{lang}.json"
    return json.loads(fpath.read_text(encoding="utf-8"))


def _collect_keys(d: dict, prefix: str = "") -> set[str]:
    """Sammelt alle Keys rekursiv als dot-notierte Pfade."""
    keys = set()
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.update(_collect_keys(v, full_key))
        else:
            keys.update({full_key})
    return keys


def _collect_values(d: dict) -> list[tuple[str, str]]:
    """Sammelt alle Blatt-Werte rekursiv als (key, value) Paare."""
    items = []
    for k, v in d.items():
        if isinstance(v, dict):
            for sub_k, sub_v in _collect_values(v):
                items.append((f"{k}.{sub_k}", sub_v))
        else:
            items.append((k, v))
    return items


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════


def test_de_json_is_valid():
    """de.json ist valides JSON."""
    data = _load_i18n("de")
    assert isinstance(data, dict)
    assert len(data) > 0


def test_en_json_is_valid():
    """en.json ist valides JSON."""
    data = _load_i18n("en")
    assert isinstance(data, dict)
    assert len(data) > 0


def test_de_keys_exist_in_en():
    """Alle Keys in de.json muessen auch in en.json existieren."""
    de_keys = _collect_keys(_load_i18n("de"))
    en_keys = _collect_keys(_load_i18n("en"))
    missing = de_keys - en_keys
    assert missing == set(), f"Keys in de.json aber nicht in en.json: {missing}"


def test_en_keys_exist_in_de():
    """Alle Keys in en.json muessen auch in de.json existieren."""
    de_keys = _collect_keys(_load_i18n("de"))
    en_keys = _collect_keys(_load_i18n("en"))
    missing = en_keys - de_keys
    assert missing == set(), f"Keys in en.json aber nicht in de.json: {missing}"


def test_de_no_empty_values():
    """Keine leeren Werte in de.json."""
    items = _collect_values(_load_i18n("de"))
    empty = [k for k, v in items if isinstance(v, str) and v.strip() == ""]
    assert empty == [], f"Leere Werte in de.json: {empty}"


def test_en_no_empty_values():
    """Keine leeren Werte in en.json."""
    items = _collect_values(_load_i18n("en"))
    empty = [k for k, v in items if isinstance(v, str) and v.strip() == ""]
    assert empty == [], f"Leere Werte in en.json: {empty}"


def test_same_top_level_sections():
    """de.json und en.json haben die gleichen Top-Level-Sektionen."""
    de = _load_i18n("de")
    en = _load_i18n("en")
    assert set(de.keys()) == set(en.keys()), (
        f"Unterschiedliche Top-Level-Keys: "
        f"nur de={set(de.keys()) - set(en.keys())}, "
        f"nur en={set(en.keys()) - set(de.keys())}"
    )


def test_i18n_files_exist():
    """Beide i18n-Dateien (de.json, en.json) existieren."""
    assert (I18N_DIR / "de.json").exists(), "de.json fehlt"
    assert (I18N_DIR / "en.json").exists(), "en.json fehlt"
