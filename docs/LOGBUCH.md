# HAANA Entwicklungs-Logbuch (DE)

Chronologische Dokumentation aller Aenderungen mit Rollback-Anweisungen.
Dieses Logbuch wird vom `docs`-Agenten gepflegt.

---

## 2026-03-15 — Code-Audit

**Scope:** Vollständiges Projekt-Audit (core/, admin-interface/, tests/, channels/, skills/)
**Ergebnis:** 0 Fehler in validate.sh. 1 kritischer Sicherheitsfund, 15 Dateien über 400 Zeilen.
**Kritisch:** `/api/wa-proxy/` ohne Auth — Bridge-Token-Check fehlt in `wa_proxy_chat`
**Offen:** host_claude_config Bug (bekannt), fehlende Tests für channels/whatsapp/ und system.py
**Dokument:** [REVIEW-2026-03-15.md](REVIEW-2026-03-15.md)

---

## 2026-03-15 — status.js und test_dream.py aufgeteilt (400-Zeilen-Regel)

**Aenderungen:**
- `admin-interface/static/js/status.js` (413 Z.) aufgeteilt in:
  - `status.js` (213 Z.) — Kern-Initialisierung, Metriken, Charts
  - `status-dream.js` (139 Z.) — Dream-Prozess-UI (Status, Fortschritt, Logs)
  - `status-agents.js` (64 Z.) — Agenten-Status-Anzeige
- `admin-interface/templates/index.html`: Cache-Buster status.js v17 → v18, neue Script-Tags fuer status-dream.js + status-agents.js
- `tests/test_dream.py` (476 Z.) aufgeteilt in:
  - `tests/test_dream_process.py` (264 Z.) — Dream-Prozess-Tests
  - `tests/test_dream_utils.py` (221 Z.) — Utility-Funktionen-Tests
- Toter Import `core.dream` aus `test_dream_utils.py` entfernt

**Entscheidungen:**
- Aufteilung strikt nach 400-Zeilen-Regel aus CLAUDE.md
- Logische Trennung: Dream-UI separat, Agenten-UI separat, Core separat
- Commit: `c8fc2af`

**Offene Punkte:**
- Keine

**Rollback:** `git revert c8fc2af`

---

## 2026-03-15 — haana-plan-v7-final.md vollstaendig aktualisiert

**Aenderungen:**
- `haana-plan-v7-final.md`: Vollstaendige Ueberarbeitung (Stand 2026-03-15)
  - Phasen-Status aktualisiert: Phase 2 als ✅ Abgeschlossen markiert
  - Alle abgeschlossenen Features aus LOGBUCH.md, MEMORY.md und Code-Review in Phase 2 eingetragen
  - Neue offene Punkte in "Fuer spaeter" eingetragen: SOUL.md, HA-Entity-Index, Hybrid Search, Inter-Agenten-Kommunikation, WA Notification, Update-Button, WS-Handler save_context, Onboarding-Flow, HA-Auth, Telegram vollstaendig, Kalender vollstaendig, zweite User-Instanz
  - HA Add-on Abschnitt als ❄️ Auf Eis markiert (LXC-Variante ist primaer), haana-addons/haana/ als DEPRECATED gekennzeichnet
  - Infrastruktur aktualisiert: zwei LXC-Container (Dev + Prod), keine echten IPs
  - Companion App v2.0.0 (SSO + Admin-Check) dokumentiert
  - 8 Sub-Agenten Tabelle ergaenzt
  - Technische Schuld aus Code-Review 2026-03-14 in "Fuer spaeter" eingetragen
  - Docker-Stack Hinweis auf `--profile agents` ergaenzt
  - "Zuletzt aktualisiert: 2026-03-15" als erstes Element

**Entscheidungen:**
- Plan-Datei ist Single-Source-of-Truth fuer Projekt-Status — daher vollstaendige Ueberarbeitung statt inkrementeller Updates
- alice/bob als Privacy-Platzhalter beibehalten (keine echten Namen auf GitHub)
- Technische Schuld aus Code-Review explizit als eigene Kategorie in "Fuer spaeter" — sichtbar aber nicht blockierend

**Offene Punkte:**
- Keine

**Rollback:**
- `git revert <hash>` (nach Commit)

---

## 2026-03-14 — Spezialisierte Sub-Agenten + HA-Debugging + Fallstricke in CLAUDE.md

**Aenderungen:**
- `CLAUDE.md`: Neuer Abschnitt "HA Debugging (Lesend)" mit curl-Beispielen fuer HA-Logs und Entity-States; Sub-Agenten-Tabelle um `core-dev`, `channel-dev`, `ui-dev` erweitert; neuer Abschnitt "Bekannte Fallstricke" mit Lessons Learned aus echten Bugs (SDK Tool-Namen, i18n-Paritaet, Cache-Buster, XSS, 400-Zeilen-Limit)
- `.claude/agents/core-dev.md`: Neuer Spezialist fuer `core/` — zustaendig fuer Agent-Logik, Memory, LLM-Provider; Impact-Report-Pflicht bei jeder Aenderung
- `.claude/agents/channel-dev.md`: Neuer Spezialist fuer `channels/` und `skills/` — MODULE.md-Pflicht fuer jedes neue Modul
- `.claude/agents/ui-dev.md`: Neuer Spezialist fuer `admin-interface/` — harte Regeln zu i18n-Paritaet, Cache-Buster-Pflicht und XSS-Schutz
- `.claude/agents/reviewer.md`: Impact-Check-Checkliste ergaenzt; Lessons-Learned Pflicht-Checks hinzugefuegt
- `.claude/agents/docs.md`: Post-Commit-Pflichten hinzugefuegt (git status nach commit, Verifikation)
- `.claude/agents/dev.md`: Hinweis auf Spezialisten-Agenten (`core-dev`, `channel-dev`, `ui-dev`) hinzugefuegt

**Entscheidungen:**
- Generischer `dev`-Agent war zu breit — spezialisierte Agenten kennen die genauen Invarianten ihres Bereichs (i18n-Paritaet, Impact-Report, MODULE.md) und koennen diese durchsetzen
- Fallstricke in CLAUDE.md dokumentiert damit kuenftige Agenten nicht dieselben Fehler wiederholen (PascalCase Tool-Namen, stale DOM, Cache-Buster vergessen)
- HA-Debugging-Befehle direkt in CLAUDE.md reduzieren Recherche-Zeit bei Live-Debugging

**Offene Punkte:**
- Keine

**Rollback:** `git revert da3aeb6`

---

## 2026-03-14 — save_context nach jeder HTTP /chat Anfrage

**Aenderungen:**
- `core/api.py`: Nach `run_async()` im `/chat`-Handler wird `agent.memory.save_context(agent._context_path)` aufgerufen

**Entscheidungen:**
- Context-Fenster wurde bisher nach HTTP-Anfragen nicht persistiert — bei Neustart ging das Sliding-Window verloren
- Konsistentes Verhalten mit dem WebSocket-Handler und dem REPL hergestellt

**Offene Punkte:**
- Keine

**Rollback:** `git revert 41cc0f6`

---

## 2026-03-14 — HA-Tab Timing-Bug + einheitlicher Channel-Status-Block

**Aenderungen:**
- `channels/base.py`: `get_connection_status()` als optionale Methode mit Default `None` eingefuehrt
- `channels/ha_voice/channel.py`: `get_connection_status()` implementiert — gibt `connected`, `error` oder `unconfigured` zurueck
- `channels/whatsapp/channel.py`: `get_connection_status()` gibt `None` zurueck (WhatsApp hat eigenen Status-Block in `custom_tab_html`)
- `admin-interface/routers/modules.py`: `connection_status` Feld in `GET /api/modules` Response ergaenzt
- `admin-interface/static/js/modules.js`: `setTimeout` nach DOM-Einfuegung fuer ha-voice behebt leere Felder beim ersten Oeffnen (Timing-Bug); `_renderChannelStatusBar()` rendert kompakten Status-Bar vor Custom-HTML
- `admin-interface/static/css/admin.css`: neue Klassen `.channel-status-bar` und `.status-dot-sm` (v11)
- `admin-interface/templates/index.html`: Cache-Buster auf v11/v3 angehoben

**Entscheidungen:**
- HA-Tab lud Felder beim ersten Oeffnen leer, weil DOM noch nicht fertig gerendert war — `setTimeout(0)` reicht als Fix
- Status-Block wird jetzt einheitlich via `_renderChannelStatusBar()` generiert statt je Channel individuell

**Offene Punkte:**
- Keine

**Rollback:** `git revert 637e1b4`

---

## 2026-03-14 — Companion v2.0.0: SSO-Gateway-Only

**Aenderungen:**
- `admin-interface/routers/companion.py`: Endpunkte `/api/companion/register`, `/api/companion/refresh-persons`, `/api/companion/ha-mcp-status`, `/api/ha-mcp-status` entfernt; Version in ping-Response auf `2.0.0` angehoben; Modulbeschreibung aktualisiert
- `haana-addons/haana-companion/run.py`: `_detect_ha_url()`, `_fetch_ha_persons()`, `_check_ha_mcp_addon()`, `_ws_person_watcher()`, `_do_handshake()` und zugehoerige Import (`urlparse`) entfernt; Companion reduziert auf SSO-Gateway + HA-Admin-Check
- `haana-addons/haana-companion/config.yaml`: Version auf `2.0.0` angehoben; `ha_url` Konfigurationsfeld entfernt
- `haana-addons/haana-companion/CHANGELOG.md`: v2.0.0 Eintrag ergaenzt
- haana-companion v2.0.0 auf `github.com/bennizone/haana-companion` (Commit 60aad04) gepusht

**Entscheidungen:**
- Companion hat zu viele HA-Interna selbst abgefragt (Personen, MCP, URL-Erkennung) — das fuehrt zu Doppelpflege und fragiler Supervisor-Abhaengigkeit
- Neues Modell: HAANA LXC holt HA-Daten direkt via konfigurierter HA URL + Long-Lived Token
- Companion ist nur noch SSO-Gateway (Ingress-Proxy + Einmal-Token-Ausstellung) — minimal, stabil, wartungsarm
- validate.sh: 261/261 Tests gruen; Reviewer-Score: 9/10

**Offene Punkte:**
- Keine

**Rollback:** `git revert a60c340`

---

## 2026-03-14 — Passwort-Aendern-Formular vereinfacht

**Aenderungen:**
- `admin-interface/routers/auth_routes.py`: `current_password`-Feld aus dem Passwort-Aendern-Endpunkt entfernt — Session-Auth reicht als Authentifizierungsnachweis
- `admin-interface/static/js/security.js`: Client-seitiger Match-Check fuer neues Passwort + Bestaetigung vor Submit; API-Body sendet nur noch `new_password`
- `admin-interface/templates/index.html`: `current-password`-Feld entfernt, neues `sec-confirm-password`-Feld hinzugefuegt
- `admin-interface/static/i18n/de.json`: 2 neue Keys `auth.confirm_password`, `auth.password_mismatch`
- `admin-interface/static/i18n/en.json`: 2 neue Keys `auth.confirm_password`, `auth.password_mismatch`

**Entscheidungen:**
- `current_password` ist redundant: Wer eingeloggt ist, hat sich bereits authentifiziert — doppelte Eingabe bietet keinen Sicherheitsvorteil in dieser Architektur
- Passwort-Bestaetigung (`sec-confirm-password`) verhindert Tippfehler clientseitig ohne Server-Round-Trip

**Offene Punkte:**
- Keine

**Rollback:** `git revert 9608649`

---

## 2026-03-14 — Autostart-Fix + update.sh Container-Management

**Problem:** Im Standalone-Modus (Docker) wurden Agents nach Neustart/Update nicht automatisch gestartet. WA-Bridge wurde von update.sh nicht mitgestartet.

**Aenderungen:**
- `admin-interface/main.py`: `_autostart_agents()` jetzt auch bei `HAANA_MODE == "standalone"` aufgerufen (Bedingung von `== "addon"` auf `in ("addon", "standalone")` erweitert)
- `update.sh`: `docker compose --profile agents up -d --build` — WA-Bridge wird mitgestartet
- `update.sh`: Neuer Block nach compose-Start: wartet auf `/health`, liest `admin_session` aus config.json, ruft `/api/instances/restart-all` auf

**Entscheidungen:**
- Standalone-Modus und Addon-Modus sollen identisches Autostart-Verhalten haben — kein Grund fuer Unterschiede
- update.sh verwaltet Agents aktiv (restart-all via API) statt nur Container hochzufahren — stellt sicher dass Instanzen nach Updates frischen State laden

**Offene Punkte:**
- Keine bekannten offenen Punkte

**Review:** Score 8/10 — keine kritischen Findings, validate.sh gruen (261 Tests)

**Rollback:**
- `git revert 0efec6a`

---

## 2026-03-13 — Dream-Log ohne Summary, Status-Polling, report-Felder

**Aenderungen:**
- `admin-interface/routers/dream.py`: `_run_dream()` — `log_dream_summary` wird jetzt auch aufgerufen wenn kein textuelles Summary vorhanden, aber `total_consolidated > 0` oder `total_cleaned > 0`
- `admin-interface/static/js/status.js`: `runDreamNow()` — Status-Polling alle 3s nach Dream-Start (max. 10 Versuche / 30s); Button wird erst nach Abschluss reaktiviert; `loadDreamStatus()` — Felder korrekt aus `d.report?.consolidated`, `d.report?.contradictions`, `d.report?.duration_s` gelesen statt flacher `d.*`-Felder
- `admin-interface/templates/index.html`: Cache-Buster `status.js?v=14`

**Entscheidungen:**
- Log-Eintrag auch ohne LLM-Summary sinnvoll, sobald Konsolidierungen oder Bereinigungen stattgefunden haben — verhindert stille Dream-Laeufe ohne Spur im Tagebuch
- Polling-Mechanismus noetig, da Dream asynchron laeuft und der Button sonst dauerhaft disabled bleibt
- API liefert `report` als verschachteltes Objekt — Flat-Field-Zugriffe im Frontend waren fehlerhaft (immer `null`)

**Offene Punkte:**
- Keine

**Rollback:** `git revert 32b37f4`

---

## 2026-03-13 — Defensive Null-Checks in status.js und whatsapp.js

**Aenderungen:**
- `admin-interface/static/js/status.js`: `cfg.dream?.schedule` zu `cfg?.dream?.schedule` geaendert — verhindert TypeError wenn `cfg` noch null ist (z.B. beim ersten Tab-Laden vor der Config-Antwort)
- `admin-interface/static/js/whatsapp.js`: Early-Return Guard in `refreshWaStatus()` auf alle 6 Pflicht-Elemente erweitert (`dot`, `txt`, `offl`, `info`, `qrBox`, `logoutBtn`) — verhindert Fehler wenn WA-Sektion noch nicht im DOM ist
- `admin-interface/templates/index.html`: Cache-Buster `status.js?v=12` und `whatsapp.js?v=6` gesetzt

**Entscheidungen:**
- Optional chaining auf `cfg` selbst notwendig, da `cfg` beim initialen Tab-Render noch null sein kann
- Vollstaendiger Guard auf alle 6 WA-Elemente statt nur 3 verhindert partielle DOM-Fehler bei fruehzeitigen Polling-Aufrufen

**Offene Punkte:**
- Keine

**Rollback:** `git revert ba908da`

---

## 2026-03-13 — Status-Tab als Standard, Modal.showAlert fuer leeres Dream-Tagebuch

**Aenderungen:**
- `admin-interface/static/js/status.js`: `openDreamDiary()` — leere Eintraege zeigen jetzt `Modal.showAlert()` statt einem leeren Modal-Body; fruehzeitiger `return` verhindert unnoetige `showModal()`-Aufrufe
- `admin-interface/static/js/modal.js`: neue Funktion `showAlert(message)` implementiert und exportiert; nutzt `hideCancel: true` + leerer `onConfirm`-Handler; XSS-safe via `escHtml`
- `admin-interface/templates/index.html`: `active`-Klasse von `conversations`-Tab und `panel-conversations` auf `status`-Tab und `panel-status` verschoben — Status ist jetzt Standard-Tab beim Laden; Cache-Buster `modal.js?v=4` und `status.js?v=11` erhoht

**Entscheidungen:**
- `Modal.showAlert()` als wiederverwendbare Convenience-Funktion statt inline showModal mit hartcodiertem HTML verbessert Konsistenz und Lesbarkeit
- Status-Tab als Standard sinnvoll da er den Systemzustand auf einen Blick zeigt — Conversations werden seltener direkt beim Oeffnen des Admin-UIs benoetigt

**Offene Punkte:**
- Keine

**Rollback:** `git revert 522be8e`

---

## 2026-03-13 — Status-Tab Redesign: Modul-Integration

**Aenderungen:**
- `channels/base.py`: neue `get_status_info(self, config) -> dict` Methode mit Default-Return `{"status": "unconfigured", "label": "Nicht konfiguriert"}`
- `skills/base.py`: analoge `get_status_info()` Default-Methode
- `channels/whatsapp/channel.py`: `get_status_info()` — "connected" wenn User mit Phone konfiguriert (Details: "Bridge-Status nicht geprueft"), Metrik: Modus
- `channels/ha_voice/channel.py`: `get_status_info()` — "connected" bei URL+Token, "degraded" bei nur URL, "unconfigured" sonst; Metriken: MCP-Status, STT/TTS-Entities
- `channels/telegram/channel.py`: `get_status_info()` — "connected" wenn Bot-Token gesetzt, sonst "unconfigured"; Details: Stub-Hinweis
- `admin-interface/routers/modules.py`: neuer `GET /api/modules/status` Endpoint aggregiert `get_status_info()` aller registrierten Channels/Skills, einzeln try/except abgesichert
- `admin-interface/templates/index.html`: Fake-Ollama `.cfg-section` entfernt; zwei neue Sektionen: `.status-section-title` + `#status-channels-grid` und `#status-skills-grid`
- `admin-interface/static/js/status.js`: `loadOllamaCompatStatus()` zu no-op Stub; neue `loadModuleStatus()` rendert Channels/Skills in jeweilige Grids; `moduleAction()` Placeholder; XSS-safe via escHtml/escAttr
- `admin-interface/static/css/admin.css`: neue Klassen `.status-dot-connected/degraded/error/disabled/unconfigured`, `.status-section-title`, `.module-metrics`, `.module-metric`
- `admin-interface/static/i18n/de.json` + `en.json`: 7 neue Keys (`status.channels_title`, `status.skills_title`, `status.module_unconfigured/connected/degraded/error/disabled`); Paritaet 714 Keys

**Entscheidungen:**
- Einheitliche `get_status_info()` Methode in Base-Klassen erlaubt erweiterbare Status-Aggregation ohne Aenderung am Endpoint
- Fake-Ollama-Sektion im Status-Tab war redundant mit HA Voice Channel — Entfernung reduziert Duplizierung
- try/except pro Modul im Endpoint verhindert, dass ein fehlerhaftes Modul den gesamten Status-Abruf unterbricht

**Offene Punkte:**
- `moduleAction()` ist noch ein Placeholder — konkrete Aktionen pro Modul koennen spaeter ergaenzt werden

**Review:** Score 9/10 — keine kritischen Findings, alle Warnungen behoben

**Rollback:** `git revert a5a7b87`

---

## 2026-03-13 — HA-Tab dynamisch — custom_tab_html Pattern + config_root

**Commits:** 22de6e9

**Aenderungen:**
- `channels/ha_voice/channel.py`: `config_root = "services"`, `get_config_schema()` → `[]`, `get_custom_tab_html()` mit vollstaendigem HTML-Block (22 Element-IDs)
- `admin-interface/templates/index.html`: Hardcodierter `cfgtab-ha` Button und `cfgpanel-ha` Block entfernt
- `admin-interface/static/js/modules.js`: Condition erweitert — Tabs werden auch bei leerem `config_schema` erstellt wenn `custom_tab_html` vorhanden; `_renderModuleConfigFields` wird uebersprungen wenn Schema leer
- `admin-interface/static/js/app.js`: `showCfgTab('mod-ha_voice')` → `resetSectionHa()` Callback
- `admin-interface/static/i18n/{de,en}.json`: Toter Key `config.sub_tabs.home_assistant` entfernt
- Pattern etabliert: Channels mit komplexer UI koennen `config_schema=[]` + `get_custom_tab_html()` nutzen

**Entscheidungen:**
- Vollstaendig dynamischer Tab vermeidet Synchronisierungsprobleme zwischen hardcodiertem HTML und Python-Channel-Klasse
- `config_root = "services"` stellt sicher dass save/load den richtigen Config-Bereich adressieren

**Offene Punkte:**
- Keine

**Rollback:** `git revert 22de6e9`

---

## 2026-03-13 — Fix: VALID_SCOPES-Check entfernt — User-Memory-Scopes werden nicht mehr blockiert

**Aenderungen:**
- `core/memory.py`: `VALID_SCOPES`-Konstante (`{"household_memory", "admin_memory"}`) entfernt
- `core/memory.py`: `if scope not in VALID_SCOPES`-Check in `add()` (ehemals Zeilen 1019–1021) entfernt

**Entscheidungen:**
- Der Check blockierte faelschlicherweise alle dynamischen User-spezifischen Scopes (`{instance}_memory`) mit dem Fehler "Ungültiger Scope"
- Der nachgelagerte `self.write_scopes`-Check ist das korrekte und ausreichende Sicherheitsnetz
- Review: Score 9/10, validate.sh 261/261 Tests bestanden

**Offene Punkte:**
- Keine

**Rollback:** `git revert bef9835`

---

## 2026-03-13 — Fix: channels/skills/common im Admin-Interface Container

**Aenderungen:**
- `docker-compose.yml`: drei Read-Only Volume-Mounts beim `admin-interface` Service ergaenzt:
  - `./channels:/app/channels:ro`
  - `./skills:/app/skills:ro`
  - `./common:/app/common:ro`
- Analog zum bestehenden `./core:/app/core:ro` Mount

**Entscheidungen:**
- `module_registry.py` importiert channels/skills/common beim Start; ohne diese Mounts war `ModuleNotFoundError: No module named 'channels'` die Folge
- Read-Only-Mount genuegt, da admin-interface diese Verzeichnisse nur liest

**Offene Punkte:**
- Keine

**Rollback:** `git revert 8039f61`

---

## 2026-03-13 — Phase 3: Dynamisches Admin-Interface

**Aenderungen:**
- `admin-interface/main.py`: `GET /api/modules` gibt vollstaendige `config_schema` + `user_config_schema` zurueck; `GET /api/modules/config` liest Modul-Konfiguration aus `config.services.{id}.*`; `POST /api/modules/config` speichert Modul-Konfiguration
- `admin-interface/static/js/modules.js` (neu): `loadModuleConfigTabs`, `saveModuleConfig`, `loadSkillsTab`, `loadModuleUserFields`
- Config-Tab: neue Channel/Skill-Sub-Tabs erscheinen automatisch per JS
- Skills-Haupttab: sichtbar wenn mindestens ein Skill registriert
- User-Karten: dynamische Modul-Felder werden beim Ausklappen nachgeladen
- `channels/telegram/channel.py`: `is_enabled()` liest jetzt aus `config.services.telegram.*`
- `admin-interface/static/i18n/de.json` + `en.json`: `skills.*`-Block (6 Keys) + `tabs.skills` ergaenzt — Paritaet gewahrt (708 Keys)
- XSS-Fix: `JSON.stringify(u)` in `onclick` jetzt korrekt durch `escAttr()` escaped

**Entscheidungen:**
- Ein neues Modul erscheint automatisch in der UI nach: (1) `channel.py`/`skill.py` schreiben, (2) in `module_registry.py` registrieren, (3) Admin-Interface neu starten — kein HTML/JS-Anfassen noetig
- Konfigurationswerte unter `config.services.{id}.*` gespeichert: klar separiert von bestehenden Top-Level-Config-Feldern

**Offene Punkte:**
- Keine

**Rollback:** `git revert 31030fc`

---

## 2026-03-13 — Dream-Status in Status-Tab migriert

**Commits:** 1ffeaae

**Aenderungen:**
- `admin-interface/static/js/status.js`: Dream-Funktionen (`loadDreamStatus`, `_dreamTimeAgo`, `runDreamNow`, `openDreamDiary`) migriert; zeigt alle Instanzen mit Status-Dot, letztem Lauf, Statistiken und Buttons; `loadStatus()` ruft `loadDreamStatus()` auf; Fix: `switchTab` → `showTab` in `loadModuleStatus()`
- `admin-interface/static/js/config.js`: Dream-Funktionen + `loadDreamStatus()`-Aufruf aus `renderConfig()` entfernt
- `admin-interface/templates/index.html`: Dream-Karte (`#status-dream-grid`) im Status-Tab nach Skills-Grid eingefuegt; "Status + Aktionen"-Block (Dream-Buttons + Status-Span) aus Config Memory-Tab entfernt

**Entscheidungen:**
- Dream-Status gehoert zum Status-Tab (Betriebsuebersicht), nicht zum Config Memory-Tab (Einstellungen) — klarere UX-Trennung
- Alle Instanzen werden im Status-Tab gemeinsam angezeigt statt pro Instanz im Config-Tab — konsistent mit Channel/Skill-Status-Pattern
- `switchTab` → `showTab` Fix: `loadModuleStatus()` verwendete nicht-existente Funktion — ohne Fix haetten Module den Status-Tab nicht oeffnen koennen

**Offene Punkte:**
- Keine bekannten offenen Punkte

**Rollback:**
- `git revert 1ffeaae`

---

## 2026-03-13 — WhatsApp-Tab dynamisch: custom_tab_html Pattern + config_root

**Commits:** 1f7f345

**Aenderungen:**
- `channels/base.py`: `config_root: str | None = None` + abstrakte `get_custom_tab_html() -> str` (gibt `""` zurueck) zu `BaseChannel` hinzugefuegt
- `channels/whatsapp/channel.py`: `config_root = "whatsapp"` (liest/schreibt `cfg.whatsapp.*` statt `cfg.services.whatsapp.*`); Schema-Keys auf `mode`, `self_prefix`, `bridge_url` vereinfacht; `get_custom_tab_html()` liefert vollstaendiges Tab-HTML (Status-Dot, QR-Code, Account-Info, Offline-Div, Bridge-Buttons) mit exakt gleichen Element-IDs wie bisher
- `admin-interface/routers/modules.py`: `GET /api/modules` gibt `custom_tab_html` zurueck; GET/POST Config-Endpunkte beruecksichtigen `config_root` beim Lesen und Schreiben
- `admin-interface/static/js/modules.js`: `loadModuleConfigTabs()` prepended `custom_tab_html` vor dynamisch generierten Config-Feldern
- `admin-interface/templates/index.html`: hardcodierter `cfgtab-whatsapp` + `cfgpanel-whatsapp` Block entfernt
- `admin-interface/static/js/app.js`: `showCfgTab` triggert `refreshWaStatus()` bei `mod-whatsapp` (nicht mehr bei hardcodiertem `whatsapp` Tab-ID)
- `channels/whatsapp/MODULE.md`: `config_root`-Pattern, neue Schema-Keys und `custom_tab_html`-Abschnitt dokumentiert

**Entscheidungen:**
- `get_custom_tab_html()` Pattern eingefuehrt: Channels mit komplexer UI (Status-Dots, Live-Daten, interaktive Buttons) koennen ihr Tab-HTML selbst liefern, ohne `index.html` anzufassen — erweiterbar fuer kuenftige Channels
- `config_root` ermoeglicht Channel-spezifische Config-Pfade ohne Spezialfall-Logik im Router
- Element-IDs unveraendert: bestehende JS-Funktionen (`refreshWaStatus`, `waBridgeStart`, `waBridgeStop`) funktionieren ohne Anpassung weiter
- Hardcodierte Tab-Bloecke aus `index.html` entfernt: WhatsApp ist kein Sonderfall mehr im Template

**Offene Punkte:**
- Kuenftige Channels (z.B. Telegram) koennen dasselbe Pattern nutzen sobald sie eine eigene UI benoetigen

**validate.sh:** 261 Tests gruen

**Reviewer Score:** 8/10

**Rollback:**
- `git revert 1f7f345`

---

## 2026-03-13 — Phase 2: Channel/Skill Framework Module eingebunden

**Commits:** cab91b1

**Aenderungen:**
- `common/types.py`: `ConfigField` als gemeinsamer Datentyp (Single-Source-of-Truth) — kein Zirkularimport zwischen `channels/base.py` und `skills/base.py` mehr
- `channels/base.py`: re-exportiert `ConfigField` aus `common/types.py` fuer Rueckwaertskompatibilitaet
- `channels/whatsapp/channel.py`: vollstaendige `WhatsAppChannel`-Implementierung mit globalem Schema (mode, self_prefix, bridge_url) und User-Schema (phone, lid)
- `channels/whatsapp/MODULE.md`: Dokumentation mit JID-Handling und LID-Eigenheiten
- `channels/ha_voice/channel.py`: vollstaendige `HAVoiceChannel`-Implementierung (Fake-Ollama-Channel, 3-Tier-Architektur) mit globalem Schema (enabled, ha_url, ha_token, stt/tts entities) und User-Schema (ha_person_entity)
- `channels/ha_voice/MODULE.md`: Dokumentation mit 3-Tier-Architektur-Erklaerung
- `channels/telegram/channel.py`: Import auf `common/types.py` aktualisiert
- `skills/base.py`: Import auf `common/types.py` aktualisiert
- `skills/kalender/skill.py`: Import auf `common/types.py` aktualisiert
- `admin-interface/module_registry.py`: automatische Registrierung aller bekannten Module (try/except pro Modul) — 3 Channels + 1 Skill beim Start geladen
- `admin-interface/main.py`: Registry-Initialisierung beim Start mit Log-Ausgabe; `modules_router` eingebunden
- `admin-interface/routers/modules.py`: neuer Endpunkt `GET /api/modules` liefert Channel/Skill-Metadaten (id, display_name, enabled, config_fields, user_config_fields) fuer Phase-3-UI-Integration

**Entscheidungen:**
- `ConfigField` nach `common/types.py` verschoben: Phase-1-Design-Hinweis umgesetzt — Skills und Channels teilen denselben Typ ohne zirkulaere Abhaengigkeit
- try/except pro Modul in der Registry: ein defektes Modul blockiert nicht den Stack-Start
- Leerer Default fuer `bridge_url` (statt hartcodierter URL): Review-Finding behoben, kein ungewollter Default im Schema
- channel_id-Konvention explizit dokumentiert (kebab-case): Review-Finding behoben

**Offene Punkte:**
- Phase 3: Admin-UI nutzt `/api/modules` um Channels/Skills dynamisch darzustellen

**Status:**
- 3 Channels registriert: WhatsApp, HA Voice, Telegram (Stub)
- 1 Skill registriert: Kalender (Stub)
- validate.sh: 0 Fehler
- Reviewer Score: 9/10 — keine kritischen Findings

**Rollback:**
- `git revert cab91b1`

---

## 2026-03-13 — Phase 1: Channel/Skill Framework Fundament

**Aenderungen:**
- `channels/base.py`: `BaseChannel` Abstrakt-Klasse + `ConfigField` Dataclass (55 Zeilen) — definiert Interface fuer alle kuenftigen Channel-Implementierungen
- `skills/base.py`: `BaseSkill` Abstrakt-Klasse (43 Zeilen) — definiert Interface fuer alle kuenftigen Skill-Implementierungen
- `admin-interface/module_registry.py`: `ModuleRegistry` mit globaler `registry`-Instanz (116 Zeilen) — auto-discovery und Verwaltung aller registrierten Module
- `channels/telegram/channel.py`: Vollstaendiger Telegram-Channel-Stub (Referenz-Implementierung)
- `channels/telegram/MODULE.md`: Entwickler-Doku fuer Telegram-Channel
- `skills/kalender/skill.py`: CalDAV-Kalender-Skill-Stub mit 3 Tool-Definitionen
- `skills/kalender/MODULE.md`: Entwickler-Doku fuer Kalender-Skill
- `MODULE.md` (Root): Entwickler-Anleitung fuer neue Channels/Skills
- `.gitkeep`-Dateien in: `channels/`, `channels/whatsapp/`, `channels/ha-voice/`, `channels/telegram/`, `skills/kalender/`

**Entscheidungen:**
- `ConfigField` in `channels/base.py` platziert (pragmatisch fuer Phase 1) — Design-Hinweis fuer Phase 2: ggf. nach `common/types.py` verschieben wenn Skills ebenfalls ConfigFields benoetigen
- `sys.path`-Hack in `module_registry.py` akzeptiert — pragmatische Loesung fuer aktuelles Projekt-Layout ohne Refactoring bestehender Import-Struktur
- Ausschliesslich neue Dateien in Phase 1 — kein bestehender Code veraendert (Zero-Risk fuer laufenden Stack)
- Reviewer-Score: 8/10 (kritischer Fund: falscher Import-Pfad in MODULE.md — behoben vor Commit)

**Offene Punkte:**
- Phase 2: `module_registry.py` in `main.py` einbinden (Auto-Discovery beim Start)
- Phase 3: Admin-UI fuer Modul-Verwaltung

**Rollback:**
- `git revert a2b2c01`

---

## 2026-03-13 — install.sh: --build Flag bei Erstinstallation

**Aenderungen:**
- `install.sh`: `docker compose up -d` auf `docker compose up -d --build` geaendert — Image wurde bei Erstinstallation ohne Build-Schritt nicht korrekt erstellt

**Rollback:**
- `git revert 5d961a5`

---

## 2026-03-13 — Claude Session-Loeschen im Entwicklung-Tab

**Aenderungen:**
- `admin-interface/routers/system.py`: Neuer Endpunkt `POST /api/dev/clear-sessions` loescht alle `*.jsonl` Dateien in `/claude-auth/projects/-opt-haana/`
- `admin-interface/static/js/dev.js`: Button "Claude Sessions loeschen" mit Disabled-State waehrend Fetch und r.ok-Check
- `admin-interface/static/js/utils.js`: `toast()` HTML-Parameter explizit opt-in (`html=false` Default), kein Auto-Detect mehr
- `admin-interface/templates/index.html`: Button-Element im Entwicklung-Tab ergaenzt
- `admin-interface/static/i18n/de.json` + `en.json`: Neue i18n-Keys fuer Session-Loeschen-Feature

**Entscheidungen:**
- Warnung beim Provider-Wechsel mit direktem "Jetzt loeschen"-Link verbessert UX beim Umstellen auf neuen Claude-Provider
- `html=false` Default in `toast()` verhindert versehentliche XSS-Luecken durch implizites HTML-Rendering

**Rollback:**
- `git revert 8666afe`

---

## 2026-03-13 — su - haana Credential-Fix fuer Entwicklung-Tab

**Aenderungen:**
- `admin-interface/routers/system.py`: Beim Speichern eines OAuth-Anthropic-Providers im Entwicklung-Tab werden Credentials jetzt aktiv von `{oauth_dir}/.credentials.json` nach `/claude-auth/.credentials.json` (= `/home/haana/.claude/.credentials.json` auf dem Host) kopiert
- `admin-interface/routers/system.py`: `CLAUDE_CONFIG_DIR` wird nicht mehr gesetzt — der Default `~/.claude` ist korrekt und fuer `su - haana` erreichbar
- `admin-interface/routers/system.py`: `oauth_dir` Pfad-Validierung — wird nur akzeptiert wenn unter `/data/claude-auth/` (verhindert Path-Traversal)
- `admin-interface/routers/system.py`: Copy-Fehler werden als `credentials_warning` in der API-Response zurueckgegeben statt still verschluckt

**Entscheidungen:**
- Docker-Volume-Pfad `/data/claude-auth/{id}` ist auf dem Host nicht direkt erreichbar (`/var/lib/docker/` hat `drwx--x---` Permissions) — Credentials muessen explizit in den Host-Pfad kopiert werden
- `CLAUDE_CONFIG_DIR` zu entfernen ist die sauberere Loesung als den Volume-Pfad durchzureichen: der Default `~/.claude` funktioniert ueberall ohne Env-Var-Setup
- `credentials_warning` statt harter Fehler: der Provider wird trotzdem gespeichert, Copy-Fehler ist diagnostisch, nicht kritisch

**Offene Punkte:**
- Keine

**Rollback:**
- `git revert 4c85be6` (Pfad-Validierung + Warning)
- `git revert 57b194c` (Credentials-Copy + CLAUDE_CONFIG_DIR-Entfernung)

---

## 2026-03-13 — install.sh: haana-User-Shell-Setup vervollstaendigt

**Aenderungen:**
- `install.sh`: `.bash_profile` Heredoc-Quoting korrigiert (`'BPEOF'` statt `BPEOF` — verhindert Variablen-Expansion im generierten File)
- `install.sh`: `.bash_profile` sourcet jetzt `.bashrc` am Anfang (damit `claude_provider.env` Env-Vars beim `su - haana` Login verfuegbar sind)
- `install.sh`: `.bashrc` PATH-Eintrag ergaenzt: `/home/haana/.local/bin:/usr/local/bin` (idempotent via grep-Guard) — keine root-Pfade mehr
- `install.sh`: `.claude_provider.env` Template-Erstellung ergaenzt (Guard: `[ ! -f ]`, Permissions 600, Owner haana:haana)
- `install.sh`: `chown haana:haana /home/haana/.bashrc` nach Appends ergaenzt (sichert Ownership bei Frisch-Installs ohne /etc/skel)

**Entscheidungen:**
- Heredoc-Quoting (`'BPEOF'`) verhindert ungewollte Shell-Expansion beim Schreiben des generierten `.bash_profile` — kritisch fuer `$PATH`-Variablen im Template
- `.bash_profile` sourcet `.bashrc` explizit, weil Login-Shells `.bashrc` nicht automatisch laden — ohne dies fehlen Env-Vars bei `su - haana`
- PATH ohne root-Pfade haelt das Prinzip minimaler Privilegien aufrecht

**Offene Punkte:**
- Keine

**Auswirkung:** Frisch installierte HAANA-LXC (via install.sh) haben ab sofort vollstaendiges haana-User-Setup. `su - haana` -> cd /opt/haana + claude_provider.env geladen + Claude Code im PATH.

**validate.sh:** 261 Tests gruen

**Reviewer Score:** 9/10

**Rollback:**
- `git revert e5f6ed7`

---

## 2026-03-13 — CLAUDE.md + Sub-Agenten-Definitionen ueberarbeitet, memory-Agent eingefuehrt

**Aenderungen:**
- `CLAUDE.md`: Kernprinzip geschaerft ("Orchestrator hat keine Haende"), Workflow auf 8 Schritte erweitert (Benni als expliziter Freigeber), Debugging-Erlaubnis (SSH lesend auf .12 + HA), memory-Agent in Tabelle, 400-Zeilen-Coding-Regel
- `.claude/agents/dev.md`: Projektstruktur aktualisiert (cascade.py entfernt, routers/ ergaenzt), 400-Zeilen-Regel, benni/domi
- `.claude/agents/webdev.md`: i18n-Paritaet explizit, 400-Zeilen-Regel
- `.claude/agents/reviewer.md`: Dateigroessen-Checkliste (Warnung >= 400 Z., Kritisch >= 600 Z.)
- `.claude/agents/docs.md`: benni/domi statt Alice/Bob, decisions.md-Abschnitt
- `.claude/agents/memory.md`: **Neu** — pflegt docs/decisions.md als durchsuchbares Entscheidungsregister
- `docs/decisions.md`: **Neu** — 12 rueckwirkende Architekturentscheidungen aus LOGBUCH.md rekonstruiert

**Entscheidungen:**
- Orchestrator-Prinzip explizit schriftlich verankert: jede Codeaenderung laeuft ueber Sub-Agenten
- memory-Agent als dedizierte Rolle eingefuehrt, damit ADRs nicht im Logbuch vergraben bleiben
- decisions.md als durchsuchbares Register ermoeglicht schnelle Architektur-Recherche ohne Logbuch-Lesen

**Offene Punkte:**
- Keine

**validate.sh:** 261 Tests gruen

**Reviewer Score:** 9/10

**Rollback:**
- `git revert 6e86e46`

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

## 2026-03-12 — Ollama-Compat-Endpoints aus Auth-Middleware ausgenommen

**Aenderungen:**
- `admin-interface/main.py`: `/api/tags`, `/api/chat`, `/api/version`, `/api/ps`, `/api/show` zu `_AUTH_EXEMPT_EXACT` hinzugefuegt

**Entscheidungen:**
- HA Voice Pipeline spricht den Fake-Ollama-Proxy ohne Auth-Header an — alle fuenf Ollama-kompatiblen Endpunkte muessen auth-frei sein, damit der Proxy erreichbar ist
- Authentifizierung bleibt fuer alle anderen Endpunkte unveraendert aktiv

**Offene Punkte:**
- Keine

**Rollback:** `git revert 5856cf5`

---

## 2026-03-12 — System-Prompts auf direkte Nutzeransprache umgestellt

**Aenderungen:**
- `instanzen/templates/user.md`: Identity-Sektion auf direkte Ansprache umgestellt ("You are currently speaking with {{DISPLAY_NAME}}"); Memory-Warnung als eigener Block in `## Memory Behavior`
- `instanzen/templates/admin.md`: Time & Timezone und Web Search Sektionen ergaenzt (Paritaet mit user.md)
- `instanzen/ha-assist/CLAUDE.md`, `instanzen/ha-advanced/CLAUDE.md`, `instanzen/haana-admin/CLAUDE.md`: Aus aktualisierten Templates regeneriert

**Entscheidungen:**
- "You are currently speaking with X" statt "You are HAANA's instance for X": direktere Formulierung vermeidet Dritte-Person-Selbstbeschreibung, wirkt natuerlicher in Konversationen
- "I'm your HAANA assistant" statt Dritte-Person bei Model-Identity-Antworten: konsistenter Ich-Stil
- Memory-Warnung als eigener Block: hoehere Sichtbarkeit, verhindert versehentliche Tool-Nutzung fuer Memory-Writes
- admin.md Paritaet mit user.md: Admin-Instanz hat jetzt dieselben Zeitzone- und Web-Search-Instruktionen

**Offene Punkte:**
- Keine

**Rollback:** `git revert 359380c`

---

## 2026-03-12 — Log-Verzeichnisse beim Startup anlegen

**Commits:** 0afa2b4

**Aenderungen:**
- `admin-interface/main.py`: Im `lifespan`-Handler werden beim Start automatisch die Verzeichnisse `logs/conversations`, `logs/memory-ops`, `logs/dream` und `logs/errors` unterhalb von `HAANA_MEDIA_DIR` (Default `/media/haana`) angelegt. Eigentuemerschaft wird per `os.chown` auf `HAANA_UID` (Default `1000`) gesetzt. Fehler werden als WARNING geloggt, nicht als Exception.

**Entscheidungen:**
- Verhindert Permission-Fehler bei Neuinstallation und neuen Usern ohne manuelle Vorbereitung der Verzeichnisstruktur
- `HAANA_UID` als Env-Variable statt Hardcoding, damit der Container flexibel auf unterschiedliche Host-UIDs reagiert

**Offene Punkte:**
- Kein offener Punkt.

**Rollback:** `git revert 0afa2b4`

---

## 2026-03-12 — Embedding-Refactoring, HA Users Sync, UI-Fixes

**Commits:** b6967f8

**Aenderungen:**
- `admin-interface/main.py`: Embedding-Config als benannte Liste (`embeddings[]`) statt einzelner Inline-Config; `process_manager.py` liest benanntes Embedding aus der Liste; HA-Companion-Registrierung gibt Personen-Liste zurueck und wird gecacht
- `admin-interface/static/js/config.js`: Memory-Tab auf Dropdown-Auswahl des konfigurierten Embeddings vereinfacht; LLM/Provider Unsaved-State-Fix (DOM wird vor Re-Render synchronisiert); stale-DOM-Fix in `saveSectionLlms`; `resetSectionMemory` laed Embeddings neu vom Server
- `admin-interface/static/js/users.js`: User-Formular: HA-Selector an Anfang verschoben, fuellt Anzeigename + ID automatisch aus; `claude.md`-Template-Feld entfernt (wird aus Rolle abgeleitet)
- `admin-interface/templates/index.html`: HTML fuer neues Embedding-Dropdown + HA-User-Selector
- `haana-addons/haana-companion/run.py`: Supervisor-Proxy-Call zum Abrufen der Personen-Liste bei Registrierung; Liste wird an HAANA uebergeben
- `core/process_manager.py`: Liest benanntes Embedding aus `embeddings[]`-Liste; keine Inline-Config mehr
- `admin-interface/static/i18n/de.json` + `en.json`: i18n-Keys fuer Embedding-Dropdown + HA-User-Selector ergaenzt
- `tests/test_config.py`: Tests fuer neue Embedding-Listen-Struktur angepasst

**Entscheidungen:**
- Embedding als benannte Liste statt Inline-Config: ermoeglicht mehrere Embeddings (z.B. lokal + cloud), einfachere Auswahl im UI per Dropdown
- Empty Default (kein vorkonfiguriertes fastembed): verhindert unbeabsichtigte Modell-Downloads bei Erstinstallation
- HA-Personen-Liste vom Companion gecacht: HAANA kennt HA-Entitaeten ohne separaten API-Call; bleibt aktuell bei jedem Companion-Neustart
- `claude.md`-Template aus User-Formular entfernt: Template wird vollstaendig aus der Rolle abgeleitet — weniger Redundanz, weniger Fehlerquellen

**Offene Punkte:**
- Keine

**Rollback:** `git revert b6967f8`

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
