# HAANA Entwicklungs-Logbuch (DE)

Chronologische Dokumentation aller Aenderungen mit Rollback-Anweisungen.
Dieses Logbuch wird vom `docs`-Agenten gepflegt.

---

## 2026-03-13 — Refactoring: admin-interface/main.py in FastAPI-Router aufgeteilt

**Aenderungen:**
- `admin-interface/main.py` (4585 Z.) in 17 Dateien aufgeteilt
- Neue Struktur: `admin-interface/routers/` mit 16 Modulen + `__init__.py`
  - `routers/defaults.py` (251 Z.) — DEFAULT_CONFIG, Migrations-Logik, System-Users
  - `routers/deps.py` (341 Z.) — Shared State, Helpers, Config-Zugriff
  - `routers/auth_routes.py` (88 Z.) — Login/Logout/SSO
  - `routers/agents.py` (100 Z.) — Agent Start/Stop/Status
  - `routers/companion.py` (138 Z.) — Companion Ping/Register/Token
  - `routers/users.py` (172 Z.) — User CRUD
  - `routers/conversations.py` (175 Z.) — Instanzen, Chat-Proxy, SSE
  - `routers/dream.py` (211 Z.) — Dream-Prozess
  - `routers/ha_services.py` (241 Z.) — HA Test, Pipeline, STT/TTS
  - `routers/setup.py` (266 Z.) — Setup-Wizard
  - `routers/whatsapp.py` (277 Z.) — WhatsApp Status/Bridge
  - `routers/config.py` (347 Z.) — Config CRUD, Provider
  - `routers/memory.py` (368 Z.) — Memory-Stats, Rebuild
  - `routers/logs.py` (420 Z.) — Log-Endpunkte
  - `routers/system.py` (428 Z.) — Status, Git, Dev-Provider
  - `routers/claude_auth.py` (452 Z.) — OAuth PTY-Flow
- `admin-interface/main.py` danach: **263 Zeilen** (App-Init, Middleware, Router-Includes)
- `tests/test_config.py`: Imports auf neue Pfade aktualisiert
- Alle 102 Endpunkte erhalten, kein Verhalten geaendert

**Entscheidungen:**
- God-File-Pattern aufgeloest: main.py war auf ~4585 Zeilen angewachsen; jede Aenderung riskierte Kontext-Overflow bei Sub-Agenten
- Router-Aufteilung nach fachlicher Zugehoerigkeit (nicht nach HTTP-Methode)
- `deps.py` als zentrales Shared-State-Modul verhindert zirkulaere Imports

**Offene Punkte:**
- `claude_auth.py` (452 Z.), `system.py` (428 Z.), `logs.py` (420 Z.) leicht ueber 400-Zeilen-Grenze — separates Ticket moeglich

**validate.sh:** 261 Tests gruen

**Reviewer Score:** 9/10

**Rollback:**
- `git revert 172ddb3`

---

## 2026-03-13 — Cleanup-Sprint: Altlasten entfernen

**Aenderungen:**
- `haana-addons/haana/` geloescht (veraltete Kopie des Hauptcodes, alle `core/*.py` divergiert)
- `haana-addons/haana-whatsapp/whatsapp-bridge/` geloescht (veraltete Bridge-Kopie)
- Terminal-Tab vollstaendig entfernt: `admin-interface/terminal.py`, `admin-interface/static/js/terminal.js`, xterm-Dateien (`xterm.min.js`, `xterm-addon-fit.min.js`, `xterm.css`), `admin-interface/templates/terminal.html`, `admin-interface/static/css/terminal.css`, Terminal-Routen aus `admin-interface/main.py`, Terminal-HTML-Sektion aus `admin-interface/templates/index.html`, `terminal.*` i18n-Keys aus `de.json` + `en.json`
- Dev-Provider-Funktionen aus `terminal.js` in neue `admin-interface/static/js/dev.js` verschoben (`loadDevProvider`, `saveDevProvider`, `_devOnProviderChange`, `_devPopulateModels`, `_devLoadOllamaModels`)
- `docker-compose.yml`: auskommentierte Services (`ollama`, `trilium`) und deren Volumes entfernt
- Tote CSS-Regeln (`.terminal-status-dot.*`) aus `admin-interface/static/css/admin.css` entfernt
- `haana-plan-v7-final.md`: veraltete Dateireferenzen korrigiert (`core/cascade.py`, `core/channels.py`, `voice-backend/main.py`), Docker-Strategie-Hinweis ergaenzt

**Befund (nicht angefasst):**
- `core/dream.py` ist aktiver Code (lazy import in `main.py` Zeile 3723 + `tests/test_dream.py`) — behalten

**Entscheidungen:**
- `haana-addons/haana/` war seit MS7 nicht mehr gepflegt und haette bei jedem Merge zu Konflikten gefuehrt
- Terminal-Tab hatte kein aktives Use-Case mehr nach Einfuehrung des Sub-Agenten-Workflows
- Auskommentierte docker-compose-Einträge erzeugten falschen Eindruck ueber den Stack-Umfang

**i18n:** Von 721 auf 693 Keys (28 `terminal.*` Keys entfernt, `dev.tab` hinzugefuegt, Paritaet gewahrt)

**validate.sh:** 261 Tests gruen

**Offene Punkte:**
- Keine

**Rollback:**
- `git revert f7f8d83`

**Reviewer Score:** 9/10

---

## 2026-03-12 — WhatsApp Auto-LID-Learning

**Aenderungen:**
- `whatsapp-bridge/index.js`: Nach erfolgreichem LID-Resolve via `signalRepository` wird `POST /api/users/whatsapp-lid` gefeuert (Fire-and-forget, timeout 5000ms)
- `admin-interface/main.py`: Neuer Endpunkt `POST /api/users/whatsapp-lid` — speichert `whatsapp_lid` in `config.json`, Auth via Bridge-Token oder Session
- `admin-interface/static/js/users.js`: LID-Feld im User-Formular als readonly mit Hinweis "Wird automatisch ermittelt"
- `admin-interface/templates/index.html`: Markup-Ergaenzung fuer LID-Anzeige im User-Formular
- `admin-interface/static/i18n/de.json` + `en.json`: Neue i18n-Keys fuer LID-Feld (703 Keys, Paritaet gewahrt)

**Entscheidungen:**
- LID wird automatisch beim ersten Eingang einer Nachricht persistiert — keine manuelle Eingabe noetig
- Fire-and-forget mit `timeout: 5000` verhindert, dass ein haengendes Admin-Interface die Bridge blockiert
- LID im UI readonly (nicht editierbar), da sie ausschliesslich vom Bridge-Prozess gesetzt wird

**Offene Punkte:**
- Keine

**Rollback:**
- `git revert bcf1698`

**Reviewer Score:** 9/10

---

## 2026-03-12 — Design-Vereinheitlichung + Bugfixes

**Aenderungen:**
- `admin-interface/static/css/admin.css`: `.status-dot-sm` (ok/err/warn/muted), `.terminal-status-dot` (connected/disconnected), `.cfg-section + h3` als vollstaendige CSS-Box-Klasse, `.tag.tag-warn` + `.tag.tag-xs` Modifier-Klassen — admin.css v9
- `admin-interface/static/js/status.js`: inline-styles durch CSS-Klassen ersetzt
- `admin-interface/templates/index.html`: Markup-Anpassungen fuer neue CSS-Klassen

**Entscheidungen:**
- Inline-Styles in JS gehoeren nicht in JS-Logik — CSS-Klassen erleichtern Theming und Wartung
- `.cfg-section` als vollstaendige Box-Klasse (inkl. h3) vermeidet Inkonsistenzen zwischen Tabs
- `.tag.tag-warn` + `.tag.tag-xs` folgen dem bestehenden Modifier-Pattern (`.tag.tag-info` etc.)

**Offene Punkte:**
- Keine

**Rollback:**
- `git revert 17245fd`

**Reviewer Scores:** 9/10 (Design-Vereinheitlichung)

---

## 2026-03-12 — Ollama-Compat Status-Sektion + Default-Fix

- `ollama_compat.enabled` Default auf `True` gesetzt (war False — frische Installs hatten Fake-Ollama deaktiviert)
- GET `/api/status/ollama-compat`: listet alle Agenten mit Verfügbarkeit als Fake-LLM
- Status-Tab: neue Sektion "Fake-Ollama-Server (HA Voice)" mit Agent-Liste + Fehlergrund
- i18n: 9 neue status.ollama_* Keys + status.no_agents (700 Keys, paritätisch)
- Reviewer Score: 8/10 (1 Finding gefixt: fehlender no_agents Key)

---

## 2026-03-12 — WhatsApp Bridge Start/Stop Buttons

**Aenderungen:**
- `admin-interface/static/js/whatsapp.js`: `waBridgeStart()` + `waBridgeStop()` mit Polling-Integration
- `admin-interface/templates/index.html`: Start-Button im Offline-Bereich, Stop-Button in der Status-Row
- `admin-interface/main.py`: `POST /api/whatsapp/start` + `POST /api/whatsapp/stop` via subprocess (shell=False)
- `admin-interface/static/i18n/de.json` + `en.json`: 5 neue `whatsapp.*` Keys (690 gesamt, paritaetisch)

**Entscheidungen:**
- Start-Button nur bei `offline`-Status sichtbar, Stop-Button bei `connected` oder `qr`
- Backend nutzt `docker compose up -d whatsapp-bridge` bzw. `docker compose stop whatsapp-bridge`
- Docker-Socket `/var/run/docker.sock` ist bereits im admin-interface Container gemountet
- Blocking subprocess akzeptabel: Start/Stop ist seltene Admin-Aktion, kein Performance-Problem

**Offene Punkte:**
- Langfristig: async subprocess fuer nicht-blockierendes Backend (technische Schuld, unkritisch)

**Score:** 8/10 (reviewer)

**Rollback:** `git revert fac0379`

---

## 2026-03-12 — Entwicklung-Tab: Claude Code Provider-Auswahl

**Aenderungen:**
- `admin-interface/templates/index.html`: Provider-UI im Entwicklung-Tab aktiv; Terminal und Git ausgegraut mit "Demnaechst verfuegbar"-Badge
- `admin-interface/static/js/terminal.js`: `loadDevProvider()` beim Tab-Init aufgerufen; Ollama-Modelle live von `/api/tags` geladen; Cache-Buster `terminal.js?v=4`
- `admin-interface/main.py`: `GET/POST /api/dev/claude-provider`, `_sanitize_env_value()` fuer Shell-Safety
- `install.sh`: `.bashrc` sourcet automatisch `.claude_provider.env`
- `admin-interface/static/i18n/de.json` + `en.json`: `dev.*` Keys (Paritaet 685 Keys)

**Entscheidungen:**
- Provider-Dropdown waehlt welcher konfigurierter Provider fuer `claude` CLI genutzt wird
- Modell-Dropdown: bei Minimax/Ollama sichtbar; Ollama-Modelle live von API geladen
- MCP-Checkboxen: sichtbar wenn Minimax-Provider konfiguriert ist
- Speichern schreibt `/opt/haana/.claude_provider.env` mit `export`-Zeilen
- Terminal + Git: komplex, spaeter ergaenzen — fokussierter Scope verhindert Overengineering

**Offene Punkte:**
- Terminal-Tab: ssh/tmux-Integration fuer spaetere MS
- Git-Tab: Status/Diff/Commit-Workflow fuer spaetere MS

**Score:** 8/10 (reviewer)

**Rollback:** `git revert aa42c76`

---

## 2026-03-12 — HA Long-Lived Token Integration

**Aenderungen:**
- `admin-interface/main.py`: `companion/register` schreibt `ha_token` nicht mehr (SUPERVISOR_TOKEN des Companions ueberschrieb manuell eingetragenen LLAT)
- `core/ha-users` (via main.py): SUPERVISOR_TOKEN env-Fallback entfernt, nur noch `services.ha_token` aus config.json genutzt
- `admin-interface/templates/index.html`: Hint-Text unter Token-Feld mit Link zur HA-Profil-Seite (i18n-ready)
- `admin-interface/static/js/config.js`: `_checkHaMcpAddon()` befuellt MCP-URL-Feld automatisch wenn Addon erkannt
- `admin-interface/static/i18n/de.json` + `en.json`: neue i18n-Keys fuer Token-Hint-Text

**Entscheidungen:**
- Companion-Addon wird optional: HAANA spricht HA direkt per Long-Lived Access Token (LLAT) an
- SUPERVISOR_TOKEN-Fallback war problematisch, da er manuell eingetragene Tokens ueberschrieb

**Offene Punkte:**
- Companion-Addon-Dokumentation aktualisieren (optional-Hinweis)

**Score:** 9/10 (reviewer), validate.sh: 261/261 gruen

**Rollback:** `git revert 7d1ac5c`

---

## 2026-03-11 — MS6: UX-Verbesserungen

**Aenderungen:**
- Web-Suche-Praeferenz: `instanzen/templates/user.md` + `instanzen/templates/ha-advanced.md` → Agent bevorzugt web_search fuer Faktenfragen
- Fortschritts-Feedback via WhatsApp: "Moment, ich suche..." bei web_search/understand_image (`core/agent.py` _send_feedback(), `core/api.py`, `whatsapp-bridge/index.js` POST /internal/feedback)
- Delegation-Feedback: Transition-Satz vor [DELEGATE] wird in HA-Antwort integriert (`core/ollama_compat.py`, `instanzen/templates/ha-assist.md`)
- Nachrichten-Debounce 500ms: Bild+Caption, Tippfehler-Korrekturen werden gebuendelt (`whatsapp-bridge/index.js` enqueueMessage() + processQueue())
- Abort laufender Anfragen bei neuer Nachricht gleichen Senders (AbortController per Sender)

**Entscheidungen:**
- Debounce 500ms als Kompromiss: schnell genug fuer normale Nutzung, langsam genug fuer Bild+Caption
- Feedback nur auf WhatsApp-Channels (nicht HTTP-API) um keine REST-Clients zu stoeren
- BRIDGE_CALLBACK_URL als Env-Var damit haana-core die Bridge zurueckrufen kann

**Offene Punkte:**
- Feedback-Texte sind noch hartcodiert in agent.py (kein i18n)

**Rollback:** `git revert 16d92cb`

---

## 2026-03-09 — MS5: Git-Integration + Beta-Readiness

**Anderungen:**
- `admin-interface/git_integration.py` (NEU): Pull, Push, Status, Connect, Log
- `admin-interface/static/js/git.js` (NEU): Git-UI im Config-Tab
- `README.md` + `BETA-GUIDE.md`: Beta-Dokumentation
- Dockerfile: `git` installiert
- Token-Maskierung in allen Git-Ausgaben

**Rollback:** `git revert HEAD~2..HEAD`

---

## 2026-03-09 — CLAUDE.md verschärft: absolutes Verbot für direkte Edits

**Änderungen:** `/opt/haana/CLAUDE.md` — Ausnahme-Klausel entfernt, strenge Trennung Plan/Delegation
**Grund:** 4-Augen-Prinzip wurde durch direkte Hotfixes unterlaufen
**Rollback:** `git revert HEAD`

---

## 2026-03-09 — Admin-Auth, Wizard-Verbesserungen, Bugfixes

**Aenderungen:**
- `admin-interface/auth.py`: Admin-Authentifizierung implementiert (Session-basiert, bcrypt-Passwort-Hashing)
- `admin-interface/main.py`: Auth-Middleware eingebunden (BaseHTTPMiddleware), Login/Logout-Endpunkte, geschuetzte Routen
- `admin-interface/main.py` / `admin-interface/templates/index.html`: Setup-Wizard wiederholbar gemacht — `extend`-Modus (bestehende Konfiguration erweitern) und `fresh`-Modus (Neustart mit leerer Config)
- `admin-interface/main.py`: Import-Pfad fuer `BaseHTTPMiddleware` korrigiert (`starlette.middleware.base` statt falschem Pfad)

**Entscheidungen:**
- Auth als Middleware statt Decorator: zentrale Absicherung aller Endpunkte ohne Annotation jeder Route
- Wizard-Modi (extend/fresh): Nutzer sollen nach erstem Setup nachtraeglich Provider/User hinzufuegen koennen ohne alles neu einzurichten
- Bugfix sofort deployed: Import-Fehler verhinderte jeden Container-Start

**Betroffene Dateien:**
- `admin-interface/auth.py`
- `admin-interface/main.py`
- `admin-interface/templates/index.html`

**Rollback:**
```bash
git revert ba6941e 2552b94
# Falls noetig: docker compose restart admin-interface
```

---

## 2026-03-09 — Konfiguration: 4-Augen-Prinzip und Safety-Rules

**Aenderungen:**
- `/opt/haana/CLAUDE.md` erstellt: Definiert Plan-Modus, Workflow, Sub-Agenten-Delegation
- `.claude/agents/reviewer.md`: Safety-Rules ergaenzt (Ingress-URLs, i18n-Paritaet, keine API-Keys, kein Self-Deploy)
- `.claude/agents/webdev.md`: HA-Addon Safety-Rules ergaenzt (relative URLs, i18n-Pflicht, Cache-Buster, CSS-Vars, kein innerHTML, HA-Theme)
- `.claude/agents/dev.md`: Safety-Rules ergaenzt (keine hardcodierten Ports/Pfade, py_compile, keine API-Keys)
- `.claude/agents/docs.md`: Logbuch-Pflicht und MEMORY.md-Aktualisierung ergaenzt
- `/opt/haana/docs/LOGBUCH.md` erstellt (diese Datei)

**Entscheidungen:**
- 4-Augen-Prinzip: Claude Code plant und delegiert, Sub-Agenten implementieren, reviewer prueft vor Deploy
- Safety-Rules direkt in Agent-Definitionen: gelten fuer jeden Aufruf des Agenten, kein separates Regelwerk noetig
- Logbuch auf Deutsch (LOGBUCH.md) zusaetzlich zum englischen LOGBOOK.md: konsistenter mit DE-primaerem Projekt

**Betroffene Dateien:**
- `/opt/haana/CLAUDE.md` (neu)
- `/opt/haana/.claude/agents/reviewer.md`
- `/opt/haana/.claude/agents/webdev.md`
- `/opt/haana/.claude/agents/dev.md`
- `/opt/haana/.claude/agents/docs.md`
- `/opt/haana/docs/LOGBUCH.md` (neu)

**Rollback:**
```bash
# CLAUDE.md loeschen falls gewuenscht:
rm /opt/haana/CLAUDE.md
# Agent-Aenderungen rueckgaengig:
git checkout HEAD -- .claude/agents/
```

---

## Legende

- **feat:** Neues Feature
- **fix:** Bugfix
- **refactor:** Code-Umstrukturierung ohne Funktionsaenderung
- **config:** Konfigurationsaenderung (kein Code)
- **docs:** Dokumentation
- **chore:** Wartungsarbeiten
