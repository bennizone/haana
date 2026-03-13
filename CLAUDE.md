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

| Agent    | Zweck                                      | Wann einsetzen                         |
|----------|--------------------------------------------|----------------------------------------|
| `dev`    | Backend-Entwicklung (Python, Docker, API)  | Alle Backend-Aenderungen               |
| `webdev` | Frontend-Entwicklung (HTML/CSS/JS, i18n)   | Alle UI-Aenderungen                    |
| `docs`   | Dokumentation, Logbuch, UI-Hilfen          | Nach Meilensteinen, neue Features      |
| `reviewer` | Code-Review, Score, Findings             | Nach jeder Implementierung vor Deploy  |
| `memory`   | Architekturentscheidungen dokumentieren  | Wenn Entscheidung getroffen oder nachgeschlagen wird |

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
