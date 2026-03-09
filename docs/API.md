# HAANA Admin API-Referenz

Alle API-Endpunkte des Admin-Interface (`admin-interface/main.py`).
Base-URL: `http://<host>:8080`

---

## Uebersicht

| Bereich | Endpunkte |
|---|---|
| HTML | 1 |
| Instanzen | 6 |
| Konversationen | 5 |
| Logs | 4 |
| Konfiguration | 3 |
| CLAUDE.md | 3 |
| Status | 2 |
| Chat | 1 |
| Memory | 7 |
| Verbindungstests | 3 |
| HA Integration | 3 |
| WhatsApp | 4 |
| User-Management | 5 |
| Claude Auth | 8 |
| SSE Events | 1 |
| LLM-Modelle | 3 |

---

## HTML

### GET /
**Beschreibung:** Liefert die SPA-Hauptseite (index.html).
**Response:** HTML

---

## Instanzen

### GET /api/instances
**Beschreibung:** Liste aller Instanzen (statische + dynamische User) mit Anzahl Log-Tage.
**Response:** `[{"name": "alice", "log_days": 12}, ...]`

### POST /api/instances/{instance}/restart
**Beschreibung:** Agent-Instanz neu starten (Container wird mit aktueller Config neu erstellt).
**Parameter:** `instance` (Path) — Instanz-ID
**Response:** `{"ok": true}` oder Fehlerdetails

### POST /api/instances/{instance}/stop
**Beschreibung:** Agent-Instanz graceful stoppen.
**Parameter:** `instance` (Path)
**Response:** `{"ok": true}`

### POST /api/instances/{instance}/force-stop
**Beschreibung:** Agent-Instanz sofort beenden (SIGKILL). Laufende Memory-Extraktion geht verloren.
**Parameter:** `instance` (Path)
**Response:** `{"ok": true}`

### POST /api/instances/restart-all
**Beschreibung:** Alle Agent-Instanzen mit aktueller Config neu starten.
**Response:** `{"ok": true, "results": {"alice": {"ok": true}, ...}}`

### GET /api/agent-health/{instance}
**Beschreibung:** Prueft ob ein Agent-Container erreichbar ist (Health-Check).
**Parameter:** `instance` (Path)
**Response:** `{"ok": true}` oder `{"ok": false, "error": "..."}`

---

## Konversationen

### GET /api/conversations/{instance}
**Beschreibung:** Letzte Konversations-Eintraege einer Instanz (neueste zuerst).
**Parameter:**
- `instance` (Path) — Instanz-ID
- `limit` (Query, optional, default 50) — Max. Anzahl Eintraege
**Response:** `[{"user": "...", "assistant": "...", "timestamp": "...", ...}, ...]`

### GET /api/conversations/{instance}/files
**Beschreibung:** Listet alle vorhandenen Datumsdateien (JSONL) fuer eine Instanz.
**Parameter:** `instance` (Path)
**Response:** `[{"date": "2026-03-09", "entries": 42, "size_kb": 12.3}, ...]`

### GET /api/conversations/{instance}/raw/{date}
**Beschreibung:** Gibt den rohen JSONL-Inhalt einer Datums-Log-Datei zurueck.
**Parameter:**
- `instance` (Path)
- `date` (Path) — Format YYYY-MM-DD
**Response:** `{"content": "...", "entries": 42}`

### PUT /api/conversations/{instance}/raw/{date}
**Beschreibung:** Ueberschreibt eine Datums-Log-Datei mit neuem Inhalt.
**Parameter:**
- `instance` (Path)
- `date` (Path) — Format YYYY-MM-DD
**Body:** `{"content": "..."}`
**Response:** `{"ok": true, "entries": 42}`

---

## Logs

### GET /api/logs/{category}
**Beschreibung:** Letzte Log-Eintraege einer Kategorie.
**Parameter:**
- `category` (Path) — `memory-ops` | `tool-calls` | `llm-calls`
- `limit` (Query, optional, default 100)
**Response:** `[{"timestamp": "...", ...}, ...]`

### GET /api/logs-download
**Beschreibung:** Erstellt ein ZIP mit Logs.
**Parameter:** `scope` (Query) — `all` | `system` | `conversations` | `conversations:{instance}`
**Response:** ZIP-Datei (application/zip)

### DELETE /api/logs-delete
**Beschreibung:** Loescht Logs.
**Body:** `{"scope": "all"|"system"|"conversations"|"conversations:alice"}`
**Response:** `{"ok": true, "deleted": 5}`

---

## Konfiguration

### GET /api/config
**Beschreibung:** Aktuelle Konfiguration (config.json) laden.
**Response:** Komplettes Config-Objekt (siehe CONFIG.md)

### POST /api/config
**Beschreibung:** Konfiguration speichern (ueberschreibt config.json).
**Body:** Komplettes Config-Objekt
**Response:** `{"ok": true}`

### GET /api/references/{entity_type}/{entity_id}
**Beschreibung:** Gibt alle Referenzen auf eine Entity (Provider oder LLM) zurueck. Nuetzlich vor dem Loeschen.
**Parameter:**
- `entity_type` (Path) — `provider` | `llm`
- `entity_id` (Path)
**Response:** `{"refs": ["User alice (Primary)", "LLM claude-primary"], "count": 2}`

---

## CLAUDE.md

### GET /api/claude-md/{instance}
**Beschreibung:** CLAUDE.md einer Instanz lesen.
**Parameter:** `instance` (Path)
**Response:** `{"content": "..."}`

### POST /api/claude-md/{instance}
**Beschreibung:** CLAUDE.md einer Instanz speichern.
**Parameter:** `instance` (Path)
**Body:** `{"content": "..."}`
**Response:** `{"ok": true}`

### GET /api/claude-md-template/{template_name}
**Beschreibung:** Liefert den Rohinhalt eines CLAUDE.md-Templates.
**Parameter:** `template_name` (Path) — z.B. `admin`, `user`, `ha-assist`
**Response:** `{"content": "...", "template": "admin"}`

---

## Status

### GET /api/status
**Beschreibung:** Systemstatus (Qdrant, Ollama, Log-Statistiken, Embedding-Dimensions-Check).
**Response:**
```json
{
  "qdrant": {"ok": true, "collections": [...], "rebuild_suggested": false, "dims_mismatch": false},
  "ollama": {"ok": true, "models": [...]},
  "logs": {"alice": {"days": 12, "latest": "2026-03-09"}}
}
```

### GET /api/memory-stats
**Beschreibung:** Pro Instanz: Konversations-Logs (Zeilen), Qdrant-Vektoren pro Scope. Fuer Memory-Rebuild-UI.
**Response:**
```json
[{
  "instance": "alice",
  "log_entries": 500,
  "log_days": 12,
  "scopes": {"alice_memory": 120, "household_memory": 45},
  "total_vectors": 165,
  "rebuild_suggested": false
}]
```

---

## Chat

### POST /api/chat/{instance}
**Beschreibung:** Sendet eine Nachricht an eine Agent-Instanz (Proxy zur Agent-API).
**Parameter:** `instance` (Path)
**Body:** `{"message": "Hallo HAANA"}`
**Response:** `{"response": "...", "model": "...", "latency_ms": 1234, ...}`
**Fehler:**
- 503: Agent nicht erreichbar
- 504: Timeout (>120s)

---

## Memory Rebuild

### POST /api/rebuild-scan/{instance}
**Beschreibung:** Scannt Logs und gibt Statistiken zurueck (Pre-Filtering, Kosten-Schaetzung).
**Body:** `{"skip_trivial": true}` (optional)
**Response:**
```json
{
  "total_raw": 500,
  "total_filtered": 120,
  "total_relevant": 380,
  "est_tokens": 57000,
  "provider_type": "ollama",
  "is_api": false
}
```

### POST /api/rebuild-memory/{instance}
**Beschreibung:** Startet den Memory-Rebuild aus Konversations-Logs.
**Body:** `{"skip_trivial": true, "delay_ms": 100, "resume": false}`
**Response:** `{"ok": true, "total": 380, "skipped_trivial": 120, "resumed_from": 0}`

### POST /api/rebuild-cancel/{instance}
**Beschreibung:** Pausiert/bricht einen laufenden Rebuild ab. Progress wird gespeichert.
**Response:** `{"ok": true}`

### DELETE /api/rebuild-progress/{instance}
**Beschreibung:** Verwirft gespeicherten Rebuild-Fortschritt.
**Response:** `{"ok": true}`

### GET /api/rebuild-resume-info/{instance}
**Beschreibung:** Info ueber gespeicherten Rebuild-Fortschritt.
**Response:** `{"has_progress": true, "processed": 200, "total_entries": 380, "paused_at": 1741...}`

### GET /api/rebuild-progress/{instance}
**Beschreibung:** SSE-Stream mit Rebuild-Fortschritt.
**Response:** Server-Sent Events mit `{"done": 50, "total": 380, "status": "running", "eta_s": 120}`

---

## Verbindungstests

### POST /api/test-connection
**Beschreibung:** Testet eine Verbindung zu einem Dienst.
**Body:** `{"type": "qdrant"|"ollama"|"http", "url": "..."}`
**Response:** `{"ok": true, "detail": "3 Collection(s)"}`

### POST /api/test-ha
**Beschreibung:** Testet Home Assistant URL + Long-Lived Token.
**Body:** `{"ha_url": "http://...", "ha_token": "..."}`
**Response:** `{"ok": true, "detail": "API erreichbar"}`

### POST /api/test-ha-mcp
**Beschreibung:** Testet den HA MCP Server (SSE oder HTTP).
**Body:** `{"mcp_url": "...", "token": "...", "mcp_type": "extended"|"builtin"}`
**Response:** `{"ok": true, "detail": "MCP Server erreichbar"}`

---

## HA Integration

### GET /api/ha-stt-tts
**Beschreibung:** Listet verfuegbare STT- und TTS-Entitaeten aus Home Assistant auf.
**Response:** `{"ok": true, "stt": [{"id": "stt.cloud", "name": "Cloud"}], "tts": [...]}`

### GET /api/ha-users
**Beschreibung:** Listet Home Assistant Person-Entitaeten fuer User-Mapping.
**Response:** `{"ok": true, "users": [{"id": "alice", "display_name": "Alice"}]}`

### GET /api/whatsapp-config
**Beschreibung:** Liefert WhatsApp-Routing-Konfiguration fuer die Bridge (intern, wird von Bridge gepollt).
**Response:**
```json
{
  "mode": "separate",
  "self_prefix": "!h ",
  "routes": [{"jid": "491234@s.whatsapp.net", "agent_url": "http://...", "user_id": "alice"}],
  "stt": {"ha_url": "...", "ha_token": "...", "stt_entity": "...", "stt_language": "de-DE"},
  "tts": {"ha_url": "...", "ha_token": "...", "tts_entity": "...", "tts_voice": "DeAmala"}
}
```

---

## WhatsApp Bridge

### GET /api/whatsapp-status
**Beschreibung:** Proxy: Bridge-Verbindungsstatus abfragen.
**Response:** `{"status": "connected", "user": {...}}` oder `{"status": "offline"}`

### GET /api/whatsapp-qr
**Beschreibung:** Proxy: Aktuellen QR-Code als Base64 Data-URL abrufen.
**Response:** `{"qr": "data:image/png;base64,..."}` oder `{"status": "connected"}`

### POST /api/whatsapp-logout
**Beschreibung:** Proxy: WhatsApp-Session trennen.
**Response:** `{"ok": true}`

---

## User-Management

### GET /api/users
**Beschreibung:** User-Liste mit Agent-Status (container_status).
**Response:** `[{"id": "alice", "display_name": "Alice", "role": "admin", "container_status": "running", ...}]`

### POST /api/users
**Beschreibung:** Neuen User anlegen (ID-Validierung, Port-Vergabe, CLAUDE.md aus Template, Agent-Start).
**Body:**
```json
{
  "id": "max",
  "display_name": "Max",
  "role": "user",
  "primary_llm": "claude-primary",
  "fallback_llm": "",
  "ha_user": "max",
  "claude_md_template": "user"
}
```
**Response:** `{"ok": true, "user": {...}, "container": {"ok": true}}`
**Fehler:** 400 (ID ungueltig), 409 (ID existiert/reserviert)

### PATCH /api/users/{user_id}
**Beschreibung:** User-Felder aktualisieren. Container wird neu gestartet wenn relevante Felder geaendert (primary_llm, fallback_llm, ha_user, role, claude_md_template).
**Body:** `{"display_name": "Max M.", "primary_llm": "claude-primary"}`
**Response:** `{"ok": true, "user": {...}, "restarted": true, "container": {...}}`

### DELETE /api/users/{user_id}
**Beschreibung:** User loeschen (Agent stoppen + entfernen, CLAUDE.md-Dir loeschen, Config speichern).
**Parameter:** `user_id` (Path)
**Response:** `{"ok": true, "container_removed": true}`
**Fehler:** 403 (System-Instanzen nicht loeschbar)

### POST /api/users/{user_id}/restart
**Beschreibung:** Agent fuer einen User neu starten.
**Response:** `{"ok": true, "container": {...}}`

### POST /api/users/{user_id}/stop
**Beschreibung:** Agent fuer einen User stoppen.
**Response:** `{"ok": true}`

---

## Claude OAuth

### GET /api/claude-auth/status
**Beschreibung:** Prueft ob gueltige Claude OAuth-Credentials vorliegen (globaler Pfad).
**Response:** `{"ok": true, "status": "valid", "detail": "Token gueltig (noch 3.5h)", "expires_in_hours": 3.5}`

### POST /api/claude-auth/refresh
**Beschreibung:** Versucht den OAuth-Token zu erneuern (nur Standalone-Modus mit Docker).
**Response:** `{"ok": true, "detail": "Bereits eingeloggt"}`

### POST /api/claude-auth/upload
**Beschreibung:** Credentials-Datei hochladen (JSON mit claudeAiOauth).
**Body:** `{"credentials": {"claudeAiOauth": {"accessToken": "...", "refreshToken": "...", "expiresAt": ...}}}`
**Response:** `{"ok": true, "detail": "Credentials gespeichert."}`

### POST /api/claude-auth/login/start
**Beschreibung:** Start OAuth Login: spawnt `claude auth login`, gibt die Auth-URL zurueck.
**Response:** `{"ok": true, "url": "https://claude.ai/oauth/authorize?...", "state": "..."}`

### POST /api/claude-auth/login/complete
**Beschreibung:** OAuth Login abschliessen: Authorization Code an lokalen Callback senden.
**Body:** `{"code": "..."}`
**Response:** `{"ok": true, "detail": "Login successful."}`

### GET /api/claude-auth/status/{provider_id}
**Beschreibung:** OAuth-Status fuer einen spezifischen Provider pruefen.
**Parameter:** `provider_id` (Path)
**Response:** Wie `/api/claude-auth/status`

### POST /api/claude-auth/login/start/{provider_id}
**Beschreibung:** OAuth Login fuer einen spezifischen Provider starten.
**Response:** Wie `/api/claude-auth/login/start`

### POST /api/claude-auth/login/complete/{provider_id}
**Beschreibung:** OAuth Login fuer einen spezifischen Provider abschliessen. Credentials werden in Provider-spezifisches Verzeichnis kopiert.
**Body:** `{"code": "..."}`
**Response:** `{"ok": true, "detail": "Login successful."}`

### POST /api/claude-auth/upload/{provider_id}
**Beschreibung:** Credentials fuer einen spezifischen Provider hochladen.
**Body:** `{"credentials": {"claudeAiOauth": {...}}}`
**Response:** `{"ok": true, "detail": "Credentials gespeichert."}`

---

## LLM-Modelle

### POST /api/fetch-models
**Beschreibung:** Fragt verfuegbare Modelle eines LLM-Providers ab.
**Body:** `{"type": "anthropic"|"ollama"|"minimax"|"openai"|"gemini"|"custom", "url": "...", "key": "..."}`
**Response:** `{"models": ["claude-sonnet-4-6", ...], "fallback": false}`

### POST /api/fetch-embedding-models
**Beschreibung:** Gibt Embedding-Modelle fuer einen Provider zurueck.
**Body:** `{"type": "ollama"|"openai"|"gemini", "url": "...", "key": "..."}`
**Response:** `{"models": [{"id": "bge-m3", "dims": 1024, "is_embed": true}, ...]}`

### POST /api/test-embedding
**Beschreibung:** Testet ein Embedding-Modell mit einem kurzen Text.
**Body:** `{"type": "ollama"|"openai"|"gemini", "url": "...", "key": "...", "model": "bge-m3"}`
**Response:** `{"ok": true, "dims": 1024, "time_ms": 45}`

---

## SSE Events

### GET /api/events/{instance}
**Beschreibung:** Server-Sent Events: streamt neue Konversationszeilen sobald sie erscheinen (Polling alle 2s).
**Parameter:** `instance` (Path)
**Response:** SSE-Stream mit Events:
- Connect: `{"type": "connected", "instance": "alice"}`
- Neue Nachricht: `{"type": "conversation", "record": {...}}`

---

## Ollama-kompatible Endpunkte

Diese werden vom `ollama_compat`-Router bereitgestellt (fuer HA Voice Integration):

### GET /api/tags
**Beschreibung:** Listet exponierte Modelle (Ollama-kompatibel).

### POST /api/chat
**Beschreibung:** Chat-Completion (Ollama-kompatibel, NDJSON Streaming).

### POST /api/show
**Beschreibung:** Modell-Info (Ollama-kompatibel).

### GET /api/version
**Beschreibung:** Ollama-Version (fake).

### GET /api/ps
**Beschreibung:** Laufende Modelle (Ollama-kompatibel).
