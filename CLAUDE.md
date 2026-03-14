## Entwicklungsphilosophie: 4-Augen-Prinzip (ABSOLUT VERBINDLICH)

Claude Code ist Gesprächspartner und Orchestrator — er hat keine Hände.
Lesen, planen, mit Benni besprechen, Freigabe abwarten, dann Agenten beauftragen.
Das gilt ohne Ausnahme — auch für 1-Zeilen-Änderungen.

Was im Live-System funktioniert, muss im Code funktionieren.
Claude Code behebt NIEMALS etwas direkt im laufenden System (kein SSH-Neustart,
kein direktes Konfigurieren, kein "kurz testen"). Was er per SSH oder in Logs
als Problem findet, fließt in einen Plan — der dann durch Agenten korrekt umgesetzt wird.

Claude Code läuft IMMER im Plan-Modus. Keine Ausnahmen.

### Was Claude Code DARF:
- Planen (Read-Only: Glob, Grep, Read, Bash read-only)
- Delegieren an Sub-Agenten: dev, webdev, docs, reviewer
- Git-Status lesen (git log, git status, git diff)

### Debugging (lesend erlaubt):
Claude Code darf per SSH auf dem HAANA-LXC (10.83.1.12) und auf Home Assistant
Logs lesen und Dienst-Status prüfen — ausschließlich lesend.
Niemals live ändern, neustarten, Dienste stoppen oder etwas "kurz testen".

### HA Debugging (Lesend)

Für Home Assistant Logs und Entity-States statt SSH:

HA URL und Token aus config.json lesen:
  python3 -c "import json; c=json.load(open('/data/config/config.json')); print(c['services']['ha_url'], c['services']['ha_token'])"

Verfügbare Endpunkte (alle GET, read-only):
- Logs:        {ha_url}/api/error_log
- Alle States: {ha_url}/api/states
- Ein State:   {ha_url}/api/states/{entity_id}
- HA Version:  {ha_url}/api/config

Header immer: Authorization: Bearer {ha_token}

Beispiel:
  curl -s -H "Authorization: Bearer TOKEN" \
    {ha_url}/api/error_log | tail -50

Niemals schreibende HA-API-Calls ohne explizite Benutzer-Freigabe.

### Was der Orchestrator (Haupt-Claude-Code) NIEMALS darf — auch nicht bei "kleinen" Fixes:
- Dateien direkt editieren oder schreiben (Edit, Write) — außer Meta-Dateien wie CLAUDE.md, dev.md
- Schreibende Bash-Befehle ausführen
- Docker-Befehle ausführen → delegiere an `dev`-Agent (der `dev`-Agent darf Docker-Befehle)
- Commits erstellen oder deployen

### Workflow (ohne Ausnahme):
1. Benni beschreibt was er will
2. Claude Code liest aktuellen Stand (ausschließlich lesend)
3. Claude Code erstellt Plan, erklärt ihn Benni
4. Benni gibt Freigabe
5. Sub-Agenten setzen um (dev / webdev)
6. reviewer-Agent prüft (Score ≥ 7/10 erforderlich)
7. Bei Findings: Agenten fixen — NICHT Claude Code direkt
8. docs-Agent: Logbuch + commit + push zu origin UND public

### Warum keine Ausnahmen?
Jeder direkte Fix — auch ein Ein-Zeiler — untergräbt das Vertrauen in den
Reviewer als Qualitätskontrolle. Der User will wissen: Jede Änderung wurde
gereviewed. Das gilt für Import-Pfade genauso wie für neue Features.

---

# HAANA — Claude Code Kontext

## Projekt

HAANA ist ein KI-Assistenten-Stack fuer Smart Home (Home Assistant), bestehend aus:
- **Admin-Interface** (FastAPI + Vanilla JS SPA) zur Verwaltung von Agenten, Providern, Memory
- **Core-Agenten** (Claude Agent SDK, Fallback-LLM-Kaskade, Qdrant-Memory)
- **WhatsApp-Bridge** (yowsjs)
- **HA Add-on** (laeuft als Home Assistant Addon)

## Wichtige Pfade

```
/opt/haana/
  core/               # Backend-Agenten-Code (Python)
  admin-interface/    # Admin-UI (FastAPI + HTML/CSS/JS)
  docker-compose.yml  # Service-Definitionen
  scripts/validate.sh # Test + Lint + Secrets-Check
  docs/               # Projektdokumentation
  .claude/agents/     # Sub-Agenten-Definitionen
```

## Sub-Agenten

| Agent        | Zweck                                      | Wann einsetzen                                  |
|--------------|--------------------------------------------|-------------------------------------------------|
| `dev`        | Backend-Entwicklung (Python, Docker, API)  | Uebergreifende Backend-Aenderungen              |
| `core-dev`   | Spezialist core/ (Agent, Memory, API)      | Aenderungen ausschliesslich in core/            |
| `channel-dev`| Spezialist channels/ + skills/             | Channel- oder Skill-Aenderungen                 |
| `ui-dev`     | Spezialist admin-interface/ Frontend       | Frontend-Aenderungen mit strikter Regeldurchsetzung |
| `webdev`     | Frontend-Entwicklung (HTML/CSS/JS, i18n)   | Alle UI-Aenderungen (generell)                  |
| `docs`       | Dokumentation, Logbuch, UI-Hilfen          | Nach Meilensteinen, neue Features               |
| `reviewer`   | Code-Review, Score, Findings               | Nach jeder Implementierung vor Deploy           |
| `memory`     | Architekturentscheidungen dokumentieren    | Wenn Entscheidung getroffen oder nachgeschlagen wird |

## Stack

- Python 3.13, FastAPI, Docker Compose
- Claude Agent SDK (claude-code-sdk)
- Qdrant (Vector DB fuer Memory), Ollama (lokale LLMs)
- Vanilla JS (kein Framework), Jinja2 Templates
- i18n: de.json + en.json (Paritaet Pflicht)

## Coding-Regeln (ABSOLUT VERBINDLICH)

### Keine userspezifischen Daten im Code
- **NIEMALS** Usernamen (z.B. "alice", "bob") hardcodieren — weder als Default, Fallback, Kommentar-Beispiel noch in Listen
- User-Instanzen kommen IMMER aus `config.json` (`cfg["users"]`), nie aus dem Code
- Memory-Scopes sind dynamisch: `{instance}_memory` — kein hardcodiertes `alice_memory` etc.
- IP-Adressen, Tokens, Passwörter gehoeren in `.env` (nie in Code oder Tests)
- Default-Werte fuer Instanz-Namen: leer (`""`) oder aus Config — nie ein echter Username

### Keine Dateien über 400 Zeilen
- **Jede Datei: max 400 Zeilen**. Ausnahmen nur wenn Logik wirklich nicht trennbar ist (dokumentieren warum).
- Neue Dateien sofort mit dieser Grenze im Kopf schreiben
- Bei Überschreitung im Review: Finding (Warnung), ab 600 Zeilen: Finding (Kritisch)

---

## Bekannte Fallstricke (PFLICHT zu kennen)

Aus echten Bugs dieser Installation — jeder Sub-Agent und Reviewer muss diese kennen.

### Dateigröße
- Keine Datei über 400 Zeilen (JS, Python, Shell)
- Reviewer meldet bei ≥400 Zeilen Warnung, bei ≥600 Zeilen Kritisch
- Gegenmaßnahme: aufteilen in Module/Router

### mem0 / Memory
- mem0 Config MUSS `"version": "v1.1"` enthalten (ohne v1.1: zwei LLM-Calls, MiniMax schlägt still fehl)
- Memory-Scopes nie hardcoden — immer aus config.json ableiten
- `/data/context/` braucht `haana:haana` Ownership (Permission denied Bug)
- `save_context()` nach JEDER `/chat` Anfrage aufrufen, nicht nur beim Shutdown

### Pfade
- Immer absolute Pfade: `"/data"` nicht `"data"` (relativer Pfad landet in `/app/data` statt `/data` Volume)
- `/data` gehört root — Unterverzeichnisse für haana-User explizit mit `chown` anlegen

### Docker / Container
- `update.sh` muss `--profile agents` nutzen damit whatsapp-bridge mitgestartet wird
- Auto-Start im Standalone-Modus: `_autostart_agents()` für `HAANA_MODE == "standalone"` UND `"addon"` aufrufen
- Nach Code-Änderungen in `core/`: Agent-Container neu starten (laufen sonst mit altem Image weiter)
- `restart: unless-stopped` setzt voraus dass Container einmal gestartet wurde — neu erstellte Container brauchen expliziten Start

### WhatsApp / Bridge
- LID-Cache (`_lidToPhone`) überlebt Container-Neustart nicht — `lid_mappings` aus Backend beim `refreshConfig` vorbelegen
- WA-Bridge startet vor Admin-Interface bereit ist → Routing-Refresh schlägt fehl → Bridge neu starten nach `update.sh`
- Mode `"self"` erfordert Prefix (`!h `) — für Endnutzer verwirrend, `"separate"` bevorzugen

### Auth / Session
- bcrypt für Passwörter, niemals Plaintext-Token loggen
- Session nach Passwort-Änderung invalidieren (gestohlener Cookie sonst weiter gültig)
- `companion_token` ≠ `admin_password` (verschiedene Konzepte, nie verwechseln)

### Frontend
- `JSON.stringify` in `onclick`-Attributen → XSS-Risiko — immer `escAttr()` verwenden
- Cache-Buster (`?v=X`) bei JEDER JS/CSS-Änderung erhöhen (sonst sieht Browser alte Version)
- `switchTab()` vs `showTab()` — falsche Funktion führt zu silent fail
- DOM-Elemente aus dynamisch geladenem HTML existieren erst nach dem Render — `setTimeout(..., 0)` als Fix

### i18n
- `de.json` und `en.json` müssen IMMER exakt gleich viele Keys haben (Parität)
- Tote Keys nach Entfernen von Features sofort aufräumen

### install.sh / update.sh
- Passwörter/Keys nie als Prozessargument übergeben (sichtbar in `ps aux`) — immer via `pct push` + temp-Datei
- Heredoc-Quoting: `'EOF'` (quoted) verhindert Variablen-Expansion im generierten File
- `update.sh` selbst prüft ob es sich aktualisieren muss bevor es weiterläuft (`HAANA_SELF_UPDATED` Guard)

### Sub-Agenten
- docs-Agent: nach `git commit` IMMER `git status` prüfen ob wirklich alles committed wurde
- dev-Agent: Docker-Befehle delegieren, nie direkt ausführen (CLAUDE.md Regel)
- reviewer-Agent: findet er einen Bug, gleich fixen lassen — nicht als "akzeptabel" durchwinken
