# HAANA Konfigurationsreferenz

Die Konfiguration wird in `/data/config/config.json` gespeichert.
Aenderungen ueber das Admin-Interface (`/api/config`) oder direkte Dateibearbeitung.

---

## Struktur-Uebersicht

```json
{
  "providers": [...],
  "llms": [...],
  "memory": {...},
  "embedding": {...},
  "log_retention": {...},
  "services": {...},
  "users": [...],
  "ollama_compat": {...},
  "whatsapp": {...}
}
```

---

## providers[]

Provider sind die Verbindungen zu LLM-Diensten. Jeder Provider hat einen Typ und Zugangsdaten.

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `id` | string | ja | Eindeutige ID (z.B. `anthropic-1`, `ollama-home`) |
| `name` | string | ja | Anzeigename (z.B. "Anthropic (Primaer)") |
| `type` | string | ja | Provider-Typ: `anthropic`, `ollama`, `minimax`, `openai`, `gemini`, `custom` |
| `url` | string | nein | API-URL (leer = Standard des Providers). Bei Ollama Pflicht. |
| `key` | string | nein | API-Key. Bei Ollama nicht noetig, bei Anthropic OAuth optional. |
| `auth_method` | string | nein | Nur bei `anthropic`: `api_key` oder `oauth` |
| `oauth_dir` | string | nein | Nur bei OAuth: Pfad zum Credentials-Verzeichnis (default: `/data/claude-auth/{id}`). Muss `.credentials.json` enthalten. |

**Provider-Typen:**

| Typ | Beschreibung | URL | Key |
|---|---|---|---|
| `anthropic` | Claude AI (Opus, Sonnet, Haiku) | Optional (Standard: api.anthropic.com) | API-Key oder OAuth |
| `ollama` | Lokale Modelle (Llama, Mistral etc.) | Pflicht (z.B. `http://10.83.1.110:11434`) | Nicht noetig |
| `minimax` | MiniMax (Anthropic-kompatible API) | Standard: `https://api.minimax.io/anthropic` | API-Key |
| `openai` | OpenAI (GPT-4o, o1, o3) | Optional (Standard: api.openai.com) | API-Key |
| `gemini` | Google Gemini (Flash, Pro) | Automatisch | API-Key |
| `custom` | Eigener Endpunkt / Proxy | URL noetig | Optional |

**Zentraler Token-Store (OAuth):**

Credentials werden pro Anthropic-Provider in `/data/claude-auth/{provider-id}/.credentials.json` gespeichert.
Agent-Container symlinken diesen Pfad auf `~/.claude/.credentials.json` beim Start.
Bei Read-Only-Filesystemen wird kopiert statt symlinkt.

Der Credential-Watcher in `core/agent.py` ueberwacht `mtime` der Credentials-Datei.
Aendert sich der Token (z.B. nach erneutem Login), wird der Fallback automatisch zurueckgesetzt — kein Container-Restart noetig.

**OAuth Login Flow:**

Der Login-Flow nutzt `claude setup-token` (nicht `claude auth login`):
- `setup-token` erzeugt langlebige Tokens (~1 Jahr, `expiresAt=0`) — ideal fuer headless Container-Betrieb
- `TERM=dumb` + breites PTY-Fenster verhindern TUI-Modus und URL-Umbruch
- Code wird via PTY-stdin uebertragen
- Fallback: Token-String (`sk-ant-...`) wird per Regex aus PTY-Output extrahiert wenn keine Credentials-Datei geschrieben wird

---

## llms[]

LLMs sind konkrete Modelle, die einem Provider zugeordnet sind.

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `id` | string | ja | Eindeutige ID (z.B. `claude-primary`, `ollama-extract`) |
| `name` | string | ja | Anzeigename (z.B. "Claude Sonnet") |
| `provider_id` | string | ja | Referenz auf `providers[].id` |
| `model` | string | ja | Modell-Identifier (z.B. `claude-sonnet-4-6`, `ministral-3-32k:3b`) |

---

## memory

Globale Memory-Einstellungen (Sliding Window, Extraktion, Kontext).

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `extraction_llm` | string | `""` | LLM-ID fuer Memory-Extraktion (global fuer alle User) |
| `extraction_llm_fallback` | string | `""` | Fallback-LLM fuer Extraktion |
| `context_enrichment` | bool | `false` | Pronomen-Aufloesung vor Extraktion (extra LLM-Call) |
| `context_before` | int | `3` | Anzahl Nachrichten vor der aktuellen bei Extraktion |
| `context_after` | int | `2` | Anzahl Nachrichten nach der aktuellen bei Extraktion |
| `window_size` | int | `20` | Max. Nachrichten im Sliding Window |
| `window_minutes` | int | `60` | Max. Alter in Minuten bevor Window extrahiert wird |
| `min_messages` | int | `5` | Minimum Nachrichten die immer im Window bleiben |

---

## embedding

Embedding-Modell-Konfiguration fuer Qdrant-Vektoren.

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `provider_id` | string | `"ollama-home"` | Provider-ID fuer Embeddings |
| `model` | string | `"bge-m3"` | Embedding-Modell (z.B. `bge-m3`, `text-embedding-3-small`) |
| `dims` | int | `1024` | Vektor-Dimensionen (muss zum Modell passen) |
| `fallback_provider_id` | string | `""` | Fallback-Provider fuer Embeddings |

**Wichtig:** Beim Wechsel des Embedding-Modells muessen alle Qdrant-Collections neu aufgebaut werden (Memory Rebuild). Verschiedene Dimensionen sind nicht kompatibel.

---

## log_retention

Aufbewahrungsfristen fuer operative Logs (in Tagen). Konversations-Logs werden nie geloescht.

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `conversations` | null | `null` | Immer `null` (nie loeschen, Source of Truth) |
| `llm-calls` | int | `30` | LLM-Call-Logs nach X Tagen loeschen |
| `tool-calls` | int | `30` | Tool-Call-Logs nach X Tagen loeschen |
| `memory-ops` | int | `30` | Memory-Operations-Logs nach X Tagen loeschen |

---

## services

Externe Dienste und Integrationen.

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `ha_url` | string | `""` | Home Assistant URL (z.B. `http://homeassistant.local:8123`) |
| `ha_token` | string | `""` | HA Long-Lived Access Token |
| `ha_mcp_enabled` | bool | `false` | MCP Server aktiviert |
| `ha_mcp_type` | string | `"extended"` | `"builtin"` (HA 2025.1+, 6 Tools) oder `"extended"` (ha-mcp Add-on, 89 Tools) |
| `ha_mcp_url` | string | `""` | MCP Server URL (leer = Auto-Detect) |
| `ha_mcp_token` | string | `""` | MCP Auth-Token (leer = HA-Token verwenden) |
| `ha_auto_backup` | bool | `false` | HA-Backup vor Agent-Aenderungen |
| `qdrant_url` | string | `"http://qdrant:6333"` | Qdrant-Server URL |
| `stt_entity` | string | `""` | HA STT Entity (z.B. `stt.home_assistant_cloud`) |
| `tts_entity` | string | `""` | HA TTS Entity (z.B. `tts.home_assistant_cloud`) |
| `stt_language` | string | `"de-DE"` | Sprache fuer STT/TTS |
| `tts_voice` | string | `""` | TTS Stimme (z.B. `DeAmala`, leer = Standard) |
| `tts_also_text` | bool | `false` | Antwort zusaetzlich als Text senden |

---

## users[]

User-Konfiguration. System-Instanzen (`ha-assist`, `ha-advanced`) sind geschuetzt.

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `id` | string | ja | Eindeutige User-ID (`[a-z0-9-]`, max 30 Zeichen) |
| `display_name` | string | ja | Anzeigename |
| `role` | string | ja | `admin`, `user`, `voice`, `voice-advanced` |
| `system` | bool | nein | `true` bei System-Instanzen (nicht loeschbar) |
| `primary_llm` | string | ja | LLM-ID fuer primaeres Modell |
| `fallback_llm` | string | nein | LLM-ID fuer Fallback |
| `ha_user` | string | nein | HA Person-Entity (z.B. `alice`) |
| `whatsapp_phone` | string | nein | WhatsApp-Rufnummer (ohne +, z.B. `491234567890`) |
| `whatsapp_lid` | string | nein | WhatsApp LID (Fallback-Routing) |
| `api_port` | int | auto | Agent-API Port (automatisch vergeben ab 8001) |
| `container_name` | string | auto | Docker Container Name |
| `claude_md_template` | string | nein | Template-Name: `admin`, `user`, `ha-assist`, `ha-advanced` |
| `language` | string | nein | Antwortsprache des Agents. Default: `"de"`. Moegliche Werte: `de`, `en`, `tr`, `fr`, `es`, `it`. Wird als `{{RESPONSE_LANGUAGE}}` in CLAUDE.md eingesetzt. |
| `caldav_url` | string | nein | CalDAV Server URL |
| `caldav_user` | string | nein | CalDAV Benutzername |
| `caldav_pass` | string | nein | CalDAV Passwort |
| `imap_host` | string | nein | IMAP Server |
| `imap_port` | int | `993` | IMAP Port |
| `imap_user` | string | nein | IMAP Benutzername |
| `imap_pass` | string | nein | IMAP Passwort |
| `smtp_host` | string | nein | SMTP Server |
| `smtp_port` | int | `587` | SMTP Port |
| `smtp_user` | string | nein | SMTP Benutzername |
| `smtp_pass` | string | nein | SMTP Passwort |

**System-Instanzen:**
- `ha-assist` — HAANA Voice (Ollama-basiert, nur Lichtschalter etc., kein Memory-Write)
- `ha-advanced` — HAANA Advanced (Claude-basiert, schreibt in `household_memory`)

---

## ollama_compat

Fake-Ollama-API fuer HA Voice Integration (universeller LLM-Proxy).

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `enabled` | bool | `false` | Ollama-kompatible API aktivieren |
| `exposed_models` | list | `["ha-assist", "ha-advanced"]` | Modelle die als Ollama-Modelle exponiert werden |
| `delegation` | dict | `{}` | Delegationsregeln (z.B. `{"ha-assist": "ha-advanced"}`) |

**Agent-Routing:** Alle User-Agents werden automatisch als Ollama-Modelle exponiert. Wenn ein Modell nicht in `exposed_models` steht, wird die Anfrage direkt an die Agent-API geroutet. Modelle in `exposed_models` nutzen den LLM-Proxy-Pfad (direkter API-Call ohne Claude CLI).

**Delegation:** Bei konfiguriertem Delegationsziel wird ein `[DELEGATE]`-Marker in die Antwort injiziert, der die Weiterleitung an den konfigurierten Agent ausloest.

---

## whatsapp

WhatsApp-Bridge Konfiguration.

| Feld | Typ | Default | Beschreibung |
|---|---|---|---|
| `mode` | string | `"separate"` | `"separate"` (eigene SIM) oder `"self"` (eigene Nummer + Prefix) |
| `self_prefix` | string | `"!h "` | Prefix fuer Self-Modus (nur wenn `mode = "self"`) |

---

## Umgebungsvariablen

Einige Werte werden aus Umgebungsvariablen gelesen (Defaults fuer Config).

| Variable | Default | Beschreibung |
|---|---|---|
| `HAANA_DATA_DIR` | `/data` | Basis-Datenverzeichnis |
| `HAANA_LOG_DIR` | `/data/logs` | Log-Verzeichnis |
| `HAANA_CONF_FILE` | `/data/config/config.json` | Config-Datei Pfad |
| `HAANA_INST_DIR` | `/app/instanzen` | Instanzen-Verzeichnis |
| `HAANA_MODE` | auto | `addon` oder `standalone` (Auto-Detect via Docker-Socket) |
| `HAANA_MEMORY_MODEL` | `ministral-3-32k:3b` | Modell fuer Scope-Klassifikation |
| `HAANA_WINDOW_SIZE` | `20` | Default Sliding Window Groesse |
| `HAANA_WINDOW_MINUTES` | `60` | Default Window Alter |
| `HAANA_EMBEDDING_MODEL` | `bge-m3` | Default Embedding-Modell |
| `HAANA_EMBEDDING_DIMS` | `1024` | Default Embedding-Dimensionen |
| `HAANA_CONTEXT_ENRICHMENT` | `false` | Kontext-Anreicherung |
| `HAANA_CONTEXT_BEFORE` | `3` | Kontext-Fenster davor |
| `HAANA_CONTEXT_AFTER` | `2` | Kontext-Fenster danach |
| `HAANA_EXTRACT_URL` | (aus Config) | Extraction-LLM URL |
| `HAANA_EXTRACT_KEY` | (aus Config) | Extraction-LLM API-Key |
| `HAANA_EXTRACT_PROVIDER_TYPE` | (aus Config) | Extraction-LLM Provider-Typ |
| `HAANA_EXTRACT_THINK` | `""` | Ollama Thinking-Modus (`true`/`false`/`""`) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama Default-URL |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant Default-URL |
| `HA_URL` | `""` | Home Assistant URL |
| `WHATSAPP_BRIDGE_URL` | `http://whatsapp-bridge:3001` | WhatsApp Bridge URL |

---

## Config-Migration

Alte Konfigurationen werden automatisch migriert:
1. `llm_providers[]` wird zu `providers[]` + `llms[]` aufgespalten
2. Integer-Slots (`primary_llm_slot`) werden zu String-IDs (`primary_llm`)
3. `services.ollama_url` wird entfernt (URL kommt aus Providern)
4. `auth_method` wird bei Anthropic-Providern ergaenzt
5. `oauth_dir` wird bei OAuth-Providern gesetzt
