# HAANA Projekt-Memory

## Workflow (ab 2026-03-09)

**Rollenverteilung:**
- User (Alice) = Product Owner / Architekt
- Hauptagent (ich) = Tech Lead / Orchestrator — plant, koordiniert, bewertet
- Sub-Agenten arbeiten im Hintergrund:
  - `dev` = Backend-Entwicklung (Python, Docker, APIs)
  - `webdev` = Frontend (HTML, JS, CSS, i18n)
  - `reviewer` = Code-Review nach jeder Aenderung
  - `docs` = Dokumentation, Plan, Logbuch

**Regel: Hauptagent programmiert NICHT selbst.** Alle Code-Aenderungen gehen ueber Sub-Agenten.

**Pipeline:** Plan -> dev/webdev (parallel, Hintergrund) -> reviewer -> fixes -> docs -> commit -> deploy

**Deployment:** Nach erfolgreichem Review+Commit immer `docker compose up -d --build <service>` ausfuehren.

## Projekt-Architektur

- Siehe [details](architecture.md) fuer Dateistruktur und Patterns
- Config: `/data/config/config.json` (immer gesichert)
- OAuth Store: `/data/claude-auth/{provider-id}/.credentials.json` (immer gesichert)
- Logs + Qdrant: `/media/haana/` (nur bei "Media"-Backup, Fallback auf `/data/` in Dev)
- Agenten symlinken auf OAuth Store (kein Kopieren)
- Credential-Watcher in agent.py erkennt Token-Aenderungen automatisch

## Abgeschlossene Features (Stand 2026-03-11, nach MS7)

- Voice Text-First: `whatsapp-bridge/index.js` sendet Text bei Voice-Nachrichten sofort, TTS-Audio folgt danach — `tts_also_text` Config-Option entfernt (Commit 288fdbb)
- Timezone-Fix: `TZ=Europe/Berlin` in allen Containern (`docker-compose.yml`), `{{TIMEZONE}}` Platzhalter in System-Prompts (`user.md`, `haana-admin.md`), wird in `main.py` aufgeloest
- Minimax MCP: Web-Suche + Bildanalyse als optionale Checkboxen im Admin-Interface (`mcp_web_search`, `mcp_image_analysis`), `uvx minimax-coding-plan-mcp` via `McpStdioServerConfig` in `core/agent.py`, `uv` in Dockerfile installiert
- Admin-Modus via WhatsApp (/admin Command): `core/whatsapp_router.py` (Mode-State pro Phone, 30-Min-Timeout), `instanzen/templates/haana-admin.md` (geteilte Systeminstanz), haana-admin in main.py registriert, `haana_admin_llm` Config-Feld, Admin-Instanz-Sektion im UI
- Traumprozess (Dream Process): Memory-Konsolidierung, Tages-Tagebuch in `/data/logs/dream/{instance}/YYYY-MM-DD.jsonl`, "Dream Now"-Button, konfigurierbarer LLM + Zeitplan, Agent beantwortet Datums-Fragen via `_extract_date_references()` + `_load_dream_summaries()`
- Proaktive Benachrichtigungen via Webhook
- Fallback-LLM Kaskade bei Auth-/Connection-Fehlern
- Explicit Memory Write (`_is_explicit_memory_request()`, `add_immediate()`)
- Sprache pro User (`users[].language`, `{{RESPONSE_LANGUAGE}}` in CLAUDE.md)
- OAuth setup-token, Credential-Watcher, zentraler Token-Store
- Universeller LLM-Proxy (Fake-Ollama-API) mit Tool-Calling, Agent-Routing, Delegation
- Multi-Provider Memory Extraction + Context Enrichment, Smart Rebuild
- Sub-Agenten (review, webdev, docs), Log-Management, initiale Dokumentation
- MS6 UX: Web-Suche-Praeferenz in user.md + ha-advanced.md, Fortschritts-Feedback ("Moment, ich suche...") via `_send_feedback()` + `/internal/feedback` Endpunkt in WA-Bridge, Nachrichten-Debounce 500ms + AbortController in index.js, Delegation-Feedback (Transition-Satz vor [DELEGATE])
- MS7 Proxmox Installer + HA Companion Addon (Commit 5cf6e4e):
  - `install.sh`: interaktiver Proxmox LXC Installer (Community-Scripts-Stil), erstellt Debian LXC mit Docker + haana-User, generiert companion_token
  - `update.sh`: System + Stack Update-Script fuer den HAANA-LXC
  - `haana-addons/haana-companion/`: minimales HA Addon (~5MB, Alpine+Python+aiohttp) mit Ingress-Proxy zu HAANA Admin UI, Token-Auth (secrets.compare_digest), automatischer HAANA-Handshake
  - `admin-interface/main.py`: `/api/companion/ping|register|token|token/regenerate` Endpunkte
  - Token in `config.json` als `companion_token` Feld; `ha_url` + `ha_token` werden vom Companion via `/api/companion/register` uebermittelt

## HA Addon — Strategie (MS7)

- **Neues Modell:** `haana-companion` (minimales Addon, ~5MB) statt vollstaendigem HAANA-Stack als Addon
- Companion verbindet HA mit externem HAANA-LXC via Token-Auth + Ingress-Proxy
- Altes `haana-addons/haana/` Addon als DEPRECATED markiert
- `haana-addons/repository.yaml`: haana-companion als primaerer Eintrag
- SSH-Zugang zu HA: `root@haos` mit Key von haana-lxc (`ssh-ed25519 AAAAC3...GmAVN haana-lxc`)

## Bekannte Probleme

- `setup-token` schreibt manchmal Token nur nach stdout statt .credentials.json
- Globaler OAuth-Status-Endpunkt hat Bug bei expiresAt=0 (provider-scoped ist korrekt)
- Alte globale OAuth-JS-Funktionen in config.js sind toter Code (UI nutzt provider-scoped)
- `host_claude_config` in process_manager.py zeigt noch auf `/root/.claude` (Zeile 307)

## Validierung

- `bash scripts/validate.sh` — 261 Tests, Syntax, Secrets, Imports
- i18n: 449 Keys in de.json und en.json (muss paritaetisch bleiben)

## Wichtige Learnings MS6

- Claude Agent SDK Tool-Namen sind PascalCase: `WebSearch`, nicht `web_search` → immer `.lower()` beim Vergleich
- node-fetch v2 auf WA-Bridge: AbortController funktioniert (Abort wirkt), aber kein HTTP-Level-Abort bei v2 (graceful degradation)
- Docker auf HAOS speichert Images uncompressed: 5GB compressed = ~21GB auf Disk (4-5x Faktor) — ist normal
- MS7: HA Companion Addon `haana-addons/haana-companion/run.py` — HA Ingress leitet Pfade bereits bereinigt weiter, kein X-Ingress-Path-Handling noetig
