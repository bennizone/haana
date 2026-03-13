# HA Voice Channel

Integriert Home Assistant Sprachassistenten mit HAANA-Agenten ohne
HACS-Addon. HAANA täuscht einen Ollama-Server vor.

## Wie es funktioniert (Fake-Ollama / 3-Tier Voice)

```
HA (Spracherkennung) -> Ollama-API -> HAANA Admin-Interface
                                          |
                              core/ollama_compat.py
                                          |
                         ha-assist (schnell, lokal) oder
                         ha-advanced (Claude, komplex) oder
                         User-Agent (direktes Routing)
```

1. HA sendet erkannte Sprache im Ollama-Format an HAANA (`POST /api/chat`)
2. HAANA wählt den richtigen Agenten anhand des "Modellnamens"
3. Bei komplexen Anfragen: Delegation von ha-assist -> ha-advanced (Claude)
4. Antwort wird im Ollama-Format zurückgesendet und von HA vorgelesen

## Abhängigkeiten

- Home Assistant mit eingebauter Ollama-Integration (kein HACS nötig)
- Konfigurierbarer LLM-Provider für ha-assist (Ollama lokal empfohlen)
- Optional: Anthropic/Claude für ha-advanced (Delegation)
- HA Add-on: Whisper (STT) + Piper (TTS) für lokale Sprachverarbeitung

## Konfigurationsfelder

### Global (`config.json["services"]` + `config.json["ollama_compat"]`)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ollama_compat_enabled` | toggle | Fake-Ollama aktivieren |
| `ha_url` | text | Home Assistant URL |
| `ha_token` | password | HA Long-Lived Access Token |
| `stt_entity` | text | STT-Entität für Spracherkennung (z.B. `stt.faster_whisper`) |
| `tts_entity` | text | TTS-Entität für Sprachausgabe (z.B. `tts.piper`) |

### Pro-User (`config.json["users"][]["ha_person_entity"]`)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `ha_person_entity` | text | HA Personen-Entität (z.B. `person.benni`) |

## Exponierte "Modelle"

HAANA exponiert konfigurierte Instanzen als Ollama-Modelle:
- `ha-assist:latest` -- schneller lokaler Assistent (Ollama/Piper)
- `ha-advanced:latest` -- leistungsstarker Assistent (Claude)
- `{user_id}:latest` -- User-Agenten (direktes Routing an Agent-API)

## Keine eigener Docker-Service

HA Voice läuft vollständig im `admin-interface` Container.
Die Ollama-kompatiblen Endpoints (`/api/chat`, `/api/tags`, etc.)
werden von `core/ollama_compat.py` bereitgestellt.
