# HAANA Architektur-Details

## Dateistruktur (Kern)

```
/opt/haana/
  core/
    agent.py              # HaanaAgent: Claude SDK, Fallback, Memory, Credential-Watcher, _extract_date_references(), _load_dream_summaries()
    api.py                # Agent-Container API (/chat, /health)
    memory.py             # Qdrant + Ollama Memory (Extraktion, Embedding, Suche)
    logger.py             # log_dream_summary() -> /data/logs/dream/{instance}/YYYY-MM-DD.jsonl
    process_manager.py    # DockerAgentManager + SubprocessAgentManager
    cascade.py            # LLM-Kaskade Stub (nicht aktiv genutzt)
  admin-interface/
    main.py               # Admin Backend FastAPI: _dream_state, _dream_scheduler(), _run_dream(), _build_dream_config(), GET/POST /api/dream/status|trigger|config
    templates/index.html  # SPA Template (inkl. Dream-Konfigurationsbereich)
    static/js/*.js        # Frontend Module (app, chat, config [+Dream-UI], users, logs, status, whatsapp, i18n, utils, modal)
    static/i18n/          # de.json, en.json
    static/css/admin.css  # Styles
  docker-compose.yml      # qdrant, instanz-alice/bob, admin-interface, whatsapp-bridge
  scripts/validate.sh     # Test-Suite
```

## Docker-Services

| Service | Profil | Port | Rolle |
|---------|--------|------|-------|
| qdrant | (immer) | 6333 | Vektor-DB |
| admin-interface | (immer) | 8080 | Web-UI + API Gateway |
| instanz-alice | agents | 8001 | Alices Agent |
| instanz-bob | agents | 8002 | Bobs Agent |
| whatsapp-bridge | agents | 3001 | WA Integration |
| ha-assist | (via ProcessManager) | dynamisch | HA Voice Agent |
| ha-advanced | (via ProcessManager) | dynamisch | HA Advanced Agent |

## Config-Struktur (/data/config/config.json)

- `providers[]`: LLM-Anbieter (anthropic, ollama, minimax, gemini, openai)
- `llms[]`: Modell-Definitionen, verweisen auf Provider
- `users[]`: Agent-Instanzen mit primary_llm, fallback_llm, api_port
- `embedding{}`: Embedding-Modell Config
- `memory{}`: Extraction, Window, Scopes
- `dream{}`: llm, schedule (cron), enabled — Traumprozess-Konfiguration
- `services{}`: qdrant_url, ollama_url

## Traumprozess (Dream Process)

**Datenpfad:** `/data/logs/dream/{instance}/YYYY-MM-DD.jsonl` — ein File pro Tag pro User-Instanz

**Admin-Interface API-Endpunkte:**

| Methode | Pfad | Funktion |
|---------|------|----------|
| GET | `/api/dream/status` | Letzter Lauf, Laufzustand, naechster geplanter Zeitpunkt |
| POST | `/api/dream/trigger` | Sofortiger manueller Start ("Dream Now") |
| GET | `/api/dream/config` | Aktuelle Konfiguration (LLM, Zeitplan, enabled) |
| POST | `/api/dream/config` | Konfiguration speichern |

**Agent-seitige Integration (`core/agent.py`):**
- `_extract_date_references(text)`: findet Datumsangaben im User-Input ("gestern", "vorgestern", "yesterday", DD.MM.YYYY)
- `_load_dream_summaries(dates, instance)`: laedt JSONL-Dateien fuer die erkannten Daten
- `run_async()`: fuegt geladene Zusammenfassungen als Context-Block ein, bevor Claude den Turn verarbeitet

**Config-Felder (`dream{}`):**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| enabled | bool | Traumprozess aktiv/inaktiv |
| llm | string | LLM-ID aus `llms[]` |
| schedule | string | Cron-Ausdruck (z.B. `"0 3 * * *"` = 03:00) |

## Auth-Flow

1. Admin-UI startet `claude setup-token` via PTY (TERM=dumb)
2. User autorisiert via OAuth PKCE auf claude.ai
3. Token wird in `/data/claude-auth/{provider-id}/.credentials.json` gespeichert
4. Agenten symlinken darauf
5. Credential-Watcher in agent.py erkennt Aenderungen -> Fallback-Reset
