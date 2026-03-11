# HAANA Entwicklungs-Logbuch

Chronologische Dokumentation der wichtigsten Aenderungen am HAANA-Projekt.

---

## 2026-03-11 — Pre-Release Code Quality Fixes (Commit 9348fa6)

**Aenderungen:**
- `core/agent.py`: `asyncio.create_task` fuer Feedback-Nachrichten mit `done_callback` gesichert — verhindert silent GC bei unbehandelten Exceptions
- `whatsapp-bridge/index.js`: `sentVoice`-Bedingung vereinfacht (`!wasVoice` genuegt), toter Logikzweig entfernt
- `admin-interface/main.py`: FastAPI `@app.on_event("startup")` (deprecated) auf `lifespan`-Pattern mit `asynccontextmanager` migriert

**Entscheidungen:**
- Lifespan-Pattern ist ab FastAPI 0.93 der empfohlene Weg; `on_event` wird in kuenftigen Versionen entfernt
- `done_callback` auf Tasks ist Best Practice damit Exceptions nicht lautlos verschluckt werden

**Offene Punkte:**
- Keine

**Rollback:** `git revert 9348fa6`

---

## 2026-03-11 — Voice Text-First, Timezone-Fix, Minimax MCP (Web-Suche + Bildanalyse)

**Aenderungen:**
- `whatsapp-bridge/index.js`: Text bei Voice-Nachrichten wird immer sofort gesendet, bevor TTS-Audio generiert wird — `tts_also_text` entfernt (Text-First ist jetzt Standard). Fallback-Log angepasst ("Text wurde bereits gesendet")
- `docker-compose.yml`: `TZ: Europe/Berlin` fuer alle Services (haana-alice, haana-bob, admin-interface)
- `core/agent.py`: `McpStdioServerConfig` importiert; Minimax-MCP-Block registriert `uvx minimax-coding-plan-mcp` mit Env-Vars (`MINIMAX_MCP_ENABLED`, `MINIMAX_API_KEY`, `MINIMAX_API_HOST`, `MINIMAX_MCP_WEB_SEARCH`, `MINIMAX_MCP_IMAGE_ANALYSIS`)
- `core/process_manager.py`: `_build_agent_env()` liest `mcp_web_search` + `mcp_image_analysis` aus Minimax-Provider-Config und setzt Env-Vars fuer Agent
- `instanzen/templates/user.md` + `haana-admin.md`: `{{TIMEZONE}}` Platzhalter im System-Prompt ergaenzt (Zeitzone-Kontext fuer Datum-/Zeit-Abfragen)
- `admin-interface/main.py`: `{{TIMEZONE}}` Platzhalter wird beim Starten der Agenten aus Config oder TZ-Env aufgeloest
- `admin-interface/static/js/config.js`: Minimax-Provider-Formular um Checkboxen `mcp_web_search` + `mcp_image_analysis` erweitert
- `admin-interface/templates/index.html`: Checkbox-HTML fuer Minimax-MCP-Optionen
- `admin-interface/static/i18n/de.json` + `en.json`: i18n-Keys fuer Minimax-MCP-Checkboxen ergaenzt
- `Dockerfile`: `uv` via pip installiert (benoetigt fuer `uvx` im Container)
- `tests/test_agent.py`: Tests fuer Minimax-MCP-Env-Vars + Timezone-Platzhalter ergaenzt

**Entscheidungen:**
- Text-First statt `tts_also_text`-Flag: Vereinfacht das Verhalten (Text ist immer sofort sichtbar), reduziert Config-Komplexitaet, verbessert UX bei langsamer TTS-Generierung
- `TZ` per Env-Var statt Dockerfile: Erlaubt Container-spezifische Zeitzonen ohne Rebuild; docker-compose.yml ist die Single Source of Truth
- `{{TIMEZONE}}` im System-Prompt: Agent kann Zeitzone-bewusst antworten ohne hardcoded Werte; erweiterbar auf multi-timezone
- Minimax MCP als optionale Provider-Checkboxen: Nur aktiv wenn explizit aktiviert, kein Einfluss auf bestehende Minimax-LLM-Nutzung
- `uvx` statt pip-install: Minimax-MCP laeuft isoliert in eigenem venv, keine Abhaengigkeitskonflikte mit dem Haupt-Container

**Offene Punkte:**
- `haana-addons/haana/` Sync: geaenderte Dateien muessen ins Addon-Verzeichnis uebertragen werden
- Timezone-Config-Feld im Admin-Interface noch nicht implementiert (derzeit nur via TZ-Env-Var)

**Rollback:**
`git revert 288fdbb`

---

## 2026-03-11 — Fallback-Embedding Modell-Sync + Validierung

**Aenderungen:**
- `haana-addons/haana/admin-interface/static/js/config.js`: `_syncFallbackModel()` hinzugefuegt — waehlt Fallback-Modell automatisch passend zum Primary-Modell aus
- `updateEmbedDims()`: ruft `_syncFallbackModel()` nach Primary-Modell-Aenderung auf
- `_updateFallbackLocalUI()`: ruft `_syncFallbackModel()` nach Modell-Laden auf
- `saveSectionMemory()`: Warnung per Toast wenn Fallback-Modell vom Primary abweicht (kein Blocker)

**Entscheidungen:**
- Auto-Sync vermeidet typischen Konfigurationsfehler: Primary und Fallback-Modell muessen gleich sein
- Toast-Warnung beim Speichern statt hartem Block — gibt User Kontrolle, verhindert Datenverlust
- Commit: ec458e4

**Offene Punkte:**
- i18n-Key `config_memory.embedding_model_mismatch_warn` muss in de.json + en.json gepflegt sein (pruefen)

---

## 2026-03-10 — Admin-Modus via WhatsApp + Terminal-Fixes

**Features:**
- `core/whatsapp_router.py` (neu): Mode-State pro Telefonnummer, Slash-Commands (/admin, /user, /exit), 30-Min-Inaktivitaets-Timeout, `resolve_instance()`, `build_message()`
- `instanzen/templates/haana-admin.md` (neu): Generisches Admin-Prompt-Template, Multi-Admin via `[Name]:`-Prefix
- `instanzen/templates/user.md`: HA-Identity-Sektion mit `person.{{HA_USER}}` (verhindert Entity-Verwechslung)
- `core/memory.py`: `admin_memory` Scope, haana-admin write-only in admin_memory / read in household
- `admin-interface/main.py`: haana-admin als Systeminstanz (Port 8005), `/api/wa-proxy/{id}/chat`, whatsapp-config Proxy-Routing, `haana_admin_llm` Config-Feld
- Neue Standalone-Seite `/terminal` + `templates/terminal.html` (Terminal im eigenen Fenster)

**Fixes:**
- `/api/whatsapp-config` auth-exempt gesetzt (Bridge erhielt 401, 0 Routes konfiguriert)
- Bridge-Secret `HAANA_BRIDGE_SECRET` als opt-in Schutz fuer ha_token
- haana-admin INST_DIR + CLAUDE.md werden bei Startup automatisch erstellt
- `update_user`: `mkdir` vor `write_text` (verhindert 500 bei neuen System-Usern)
- Terminal: nur im Entwicklungs-Tab sichtbar (`display:none` + `.active`)
- Terminal: `TERM=xterm-256color` behebt "does not support clear"-Fehler
- Vollbild-Button durch Detach-Button ersetzt (oeffnet `/terminal` in eigenem Fenster)
- Redundante Admin-Instanz-Sektion im Config-Tab entfernt (war doppelt mit User-Management)

**Entscheidungen:**
- Mode-State im RAM: kein persistenter Store, Timeout loescht automatisch, Verlust bei Neustart akzeptabel
- Geteilte Systeminstanz statt pro-Admin-Instanzen: einfacher Betrieb, Identifikation via Nachrichtenprefix

**Offene Punkte:**
- Rate-Limiting fuer /admin Command (Brute-Force-Schutz) nicht implementiert
- Audit-Log fuer Admin-Modus-Aktivierungen fehlt
- `haana-addons/haana/` Sync ausstehend: neue Dateien (terminal.py, admin-interface/*.py, core/, instanzen/, skills/) noch nicht ins Addon-Verzeichnis uebertragen

**Commits:** c0ac05b, d069865, a90678f, b46c7f6, de6f131, b526ec0, 3b40dfb

**Rollback:**
`git revert 3b40dfb b526ec0 de6f131 b46c7f6 a90678f d069865 c0ac05b`

---

## 2026-03-09 — Traumprozess (Dream Process)

**Aenderungen:**
- `admin-interface/main.py`: `_dream_state` (globaler Laufzustand), `_dream_scheduler()` (APScheduler-Job, configurabler Zeitplan), `_run_dream()` (Memory-Konsolidierung + Tages-Zusammenfassung), `_build_dream_config()` (Konfigurationsaufbau aus config.json)
- 4 neue API-Endpunkte: `GET /api/dream/status`, `POST /api/dream/trigger`, `GET /api/dream/config`, `POST /api/dream/config`
- `core/agent.py`: `_extract_date_references()` (erkennt "gestern", "vorgestern", "yesterday", DD.MM.YYYY), `_load_dream_summaries()` (laedt Tages-Zusammenfassungen aus JSONL), Einbindung als Context in `run_async()`
- `core/logger.py`: `log_dream_summary()` schreibt Tages-Zusammenfassungen nach `/data/logs/dream/{instance}/YYYY-MM-DD.jsonl`
- `admin-interface/static/js/config.js`: Dream-UI-Funktionen (LLM-Dropdown, Zeitplan, Enable/Disable, "Dream Now"-Button)
- `admin-interface/templates/index.html`: Dream-Konfigurationsbereich im Admin-Interface

**Entscheidungen:**
- Tages-Zusammenfassungen als JSONL-Tagebuch (ein File pro Tag pro Instanz): suchbar, inkrementell erweiterbar, kompakt
- Datums-Referenz-Extraktion im Agent (nicht als MCP-Tool): keine Tool-Runde noetig, reagiert transparent auf natuerliche Sprache
- "Dream Now"-Button: ermoeglicht sofortigen Trigger ohne Warten auf Scheduler — wichtig fuer Entwicklung und manuelle Konsolidierung
- LLM konfigurierbar (nicht hardcoded): Traumprozess kann eigenes Modell nutzen (z.B. lokales Ollama), unabhaengig vom Chat-LLM

**Offene Punkte:**
- HA Schlaf-Focus-Entity als automatischer Trigger (Beide schlafen > 30min) noch nicht implementiert
- Dream-Protokoll-Anzeige im Admin-Interface (aufklappbar) noch nicht gebaut

---

## 2026-03-09 — Explicit Memory Write

**Aenderungen:**
- `_is_explicit_memory_request()` in `core/agent.py`: erkennt explizite Speicher-Befehle ("merke dir", "vergiss nicht", "remember that" etc.) per Keyword-Matching
- Bei Treffer: `memory.add_immediate()` schreibt sofort direkt in Mem0/Qdrant (kein Sliding-Window-Delay)
- Danach: `memory.add_conversation_async(already_extracted=True)` legt den Eintrag ins Window, ohne ihn erneut zu extrahieren (Doppel-Extraktion verhindert)
- Log-Eintrag erhaelt `"memory_extracted": true` Flag (`core/logger.py`, Feld optional — nur gesetzt wenn `True`)
- `_should_extract_memory()` bleibt unveraendert: steuert ob ueberhaupt extrahiert wird (ha_voice: nur bei Trigger-Keywords; alle anderen Channels: immer)
- Natuerliche Bestaetigung erfolgt durch den Agenten via normales CLAUDE.md-Verhalten (kein Code-seitiges Forced-Response)

**Entscheidungen:**
- `add_immediate()` statt Window: Explizite Befehle sollen ohne Wartezeit auf Window-Flush wirksam sein
- `already_extracted=True` verhindert doppelte LLM-Extraktion; das Ergebnis liegt bereits in Qdrant
- `memory_extracted` Flag im Log: ermoeooglicht spaetere Analyse (wie oft wird explizit gespeichert?) und UI-Anzeige ohne erneutes Parsen des Nachrichtentexts
- `memory_extracted` wird von `/rebuild-entry` (Agent-API) ignoriert — Rebuild fuehrt immer volle Mem0-Extraktion durch, unabhaengig vom Original-Flag

**Offene Punkte:**
- Fallback-Pfad (Zeile 476 `core/agent.py`): `_is_explicit_memory_request()` wird dort nicht geprueft; explizite Befehle bei Fallback-LLM landen nur im Window, nicht sofort in Mem0

---

## 2026-03-09 — Sprach-Feature: users[].language, CLAUDE.md auf Englisch, Sprach-Dropdown

**Aenderungen:**
- `users[].language` Feld in Config-Struktur ergaenzt (String, Default `"de"`, Werte: `de/en/tr/fr/es/it`)
- CLAUDE.md Templates auf Englisch umgestellt (Sprache des System-Prompts entkoppelt von UI-Sprache)
- `{{RESPONSE_LANGUAGE}}` Platzhalter in CLAUDE.md Templates: wird beim Agent-Start mit dem konfigurierten Sprachcode ersetzt
- Sprach-Dropdown im Users-Tab des Admin-Interface: Benutzersprache pro User waehlen
- i18n-Key `users.language` und `users.language_hint` ergaenzt (de.json + en.json)

**Entscheidungen:**
- Sprache pro User statt global: Bob kann z.B. Englisch, Alice Deutsch bekommen — unabhaengig voneinander
- CLAUDE.md auf Englisch: Claude-Modelle verarbeiten englische System-Prompts effizienter; `{{RESPONSE_LANGUAGE}}` steuert die Antwortsprache des Agents separat
- Unterstuetzte Sprachen auf 6 beschraenkt (de/en/tr/fr/es/it): deckt alle aktuellen Haushaltsmitglieder ab; erweiterbar

**Offene Punkte:**
- `{{RESPONSE_LANGUAGE}}` Platzhalter noch nicht in allen CLAUDE.md-Varianten vorhanden (ggf. nachrüsten)
- Sprach-Umschaltung benoetigt Agent-Neustart (kein Hot-Reload)

## 2026-03-09 — OAuth setup-token, Credential-Watcher, zentraler Token-Store

**Aenderungen:**
- OAuth Login Flow auf `claude setup-token` umgestellt (`admin-interface/main.py`): erzeugt langlebigen Token (~1 Jahr) statt kurzlebigem Session-Token
- PTY-Spawn mit `TERM=dumb` und `NO_COLOR=1` um TUI-Modus zu deaktivieren, 500-Zeichen-Terminal-Breite gegen URL-Umbruch
- Fallback: `setup-token` schreibt Token manchmal als String nach stdout statt als Datei — Regex `sk-ant-[...]` extrahiert Token aus PTY-Output
- `expiresAt: 0` signalisiert langlebigen Token; `GET /api/claude-auth/status/{provider_id}` zeigt "Token gueltig (langlebig)" statt abgelaufener Stunden-Rechnung
- Credential-Watcher in `core/agent.py` (`_ensure_connected`): prueft `mtime` der Credentials-Datei bei jedem Request; bei Aenderung wird Fallback automatisch zurueckgesetzt und Symlink neu gesetzt — kein Container-Restart noetig
- Docker-Mount Fix in `docker-compose.yml`: `/home/haana/.claude` (statt `/root/.claude`) wird als `/claude-auth` ins admin-interface gemountet
- Zentraler Token-Store: `/data/claude-auth/{provider-id}/.credentials.json`; Agenten symlinken `~/.claude/.credentials.json` auf diesen Pfad; bei Read-Only-Filesystem wird kopiert

**Entscheidungen:**
- `setup-token` statt `auth login`: auth login erzeugt kurzlebige Session-Tokens (~8h), setup-token erzeugt langlebige Tokens ohne Ablaufdatum — ideal fuer headless/Container-Betrieb
- `TERM=dumb` verhindert dass Claude CLI in interaktiven TUI-Modus wechselt, der kein programmatisches stdin akzeptiert
- mtime-Polling statt inotify: kein zusaetzlicher Kernel-Subsystem-Zugriff noetig, reicht fuer die erwartete Aenderungsfrequenz (selten)
- `/home/haana/.claude` statt `/root/.claude`: admin-interface laeuft als User 1000 (haana), nicht als root

**Offene Punkte:**
- Token-Status-Anzeige in der UI zeigt bei `expiresAt=0` noch "langlebig" als Rohtext — i18n-Key fehlt noch
- Automatisches Symlink-Update bei Credential-Aenderung nur bei aktivem Fallback; normaler Betrieb ohne Fallback bemerkt Credential-Rotation nicht aktiv (kein Problem, da Token langlebig)

## 2026-03-09 — Sub-Agenten, Log-Management, Fake-Ollama Delegation

- Sub-Agenten fuer Review, Webinterface-Entwicklung und Dokumentation eingerichtet (`.claude/agents/`)
- Log-Download als ZIP und Loesch-Funktion im Admin-Interface implementiert (`/api/logs-download`, `/api/logs-delete`)
- `ha_voice`-Instruktionen auch in CLAUDE.md Templates ergaenzt
- User-Agents werden automatisch als Ollama-Modelle exponiert (Agent-Routing in `ollama_compat.py`)
- `ha_voice` Memory: Extraktion nur noch bei expliziten Speicher-Befehlen ("merke dir", "vergiss nicht" etc.)
- Delegation ha-assist nach ha-advanced via `[DELEGATE]`-Marker (Agent-API statt direktem LLM-Call)
- Universeller LLM-Proxy (Fake-Ollama-API) mit Tool-Calling-Support fuer alle Provider

## 2026-03-08 — Memory-Extraktion Multi-Provider, Context Enrichment, Rebuild

- Konfigurierbares Kontext-Fenster fuer Memory-Extraktion (`context_before`/`context_after`)
- Ollama Thinking-Support (Monkeypatch `client.chat`, `num_predict=8192`)
- Rebuild-Fortschritt: Pause/Resume mit persistentem Progress, Verwerfen-Button
- Review-Fixes: Persoenliche Daten entfernt, Tests erweitert, Code-Qualitaet verbessert
- MiniMax ThinkingBlock-Workaround (`_call_anthropic_direct()`), Anthropic `base_url`-Patch
- Rate-Limiter pro LLM (Token-Bucket, shared Registry), OAuth-Extraction via Claude CLI
- Gemini als Extraction-LLM und Scope-Klassifikation unterstuetzt
- Extraction-LLM nur noch global (nicht mehr per User)
- Multi-Provider Embeddings (Ollama/OpenAI/Gemini), Gemini Embedding `models/gemini-embedding-001`
- Mem0 LLM-Antworten sanitizen (MiniMax Dict/String Kompatibilitaet)
- Smart Memory Rebuild (Pre-Filtering trivialer Eintraege, Rate-Limiting, Pause/Resume)
- Multi-Provider Memory Extraction + Context Enrichment
- Env-Isolation fuer InProcess-Modus (agent.py + memory.py Env-Snapshots)
- Embedding-Mismatch-Detection (`_check_collection_dims()`, loescht Collection bei Mismatch)

## 2026-03-07 — Provider-Redesign, AgentManager, HA Add-on, OAuth

- LLM-Provider-Routing korrigiert (Env-Var-Kette fuer alle Provider-Typen)
- OAuth-Credentials-Fix, i18n-Init-Fix, Chat-UI-Details
- core/ Volume in admin-interface Container gemountet
- Restart-Feedback bei LLM-Aenderung im Users-Tab
- Plan v7 aktualisiert nach HA Add-on Architektur
- HA Add-on Repository mit 3 Add-ons (haana, haana-ollama-cpu, haana-whatsapp)
- AgentManager-Abstraktion: DockerAgentManager + InProcessAgentManager (Dual-Mode)
- Provider/LLM-Trennung: `providers[]` + `llms[]` statt `llm_providers[]`
- Typspezifische Provider-Formulare (Anthropic, Ollama, MiniMax, OpenAI, Gemini, Custom)
- OAuth pro Provider mit eigenen Credential-Pfaden
- Provider-Umbenennung: Live-Sync in `cfg.providers`
- Review-Findings adressiert (XSS, URL Injection, Permissions, Path Traversal)
- OAuth Login Flow im Admin-Interface (PTY-basiert, /proc/net/tcp Port-Detection)
- Vollstaendige i18n fuer chat/config JS, API-Key Auth Option
- Docker Image von 10.5 GB auf 327 MB reduziert (sentence-transformers entfernt, CPU-only)
- Claude OAuth Management im Admin-Interface

## 2026-03-06 — Admin-Interface Modernisierung, STT/TTS, Config Tabs

- Tests fuer Agent MCP, Config Management, i18n Paritaet
- Config-Tabs umstrukturiert, HA Auto-Backup Setting
- MCP Typ-Auswahl (builtin vs extended ha-mcp)
- ~1700 Zeilen inline JS in 10 separate Module extrahiert
- Admin UI Design modernisiert (Glassmorphism, Dark Theme, Responsive)
- `confirm()` Dialoge durch Modal-System ersetzt
- CSS/JS/i18n aus monolithischer index.html extrahiert
- Restart-Detection: Erkennt config-aenderungen die Container-Neustart erfordern
- Fuehrende/trailing Leerzeilen aus Agent-Antworten entfernen
- Sprachoptimierter Prompt + Text zusaetzlich zu Voice
- TTS Audio zu OGG Opus konvertieren + Voice-Auswahl im Admin-Interface

---

## Legende

- **feat:** Neues Feature
- **fix:** Bugfix
- **refactor:** Code-Umstrukturierung ohne Funktionsaenderung
- **perf:** Performance-Verbesserung
- **test:** Tests hinzugefuegt/erweitert
- **docs:** Dokumentation
- **chore:** Wartungsarbeiten
