## Entwicklungsphilosophie: 4-Augen-Prinzip (ABSOLUT VERBINDLICH)

Claude Code läuft IMMER im Plan-Modus. Keine Ausnahmen.

### Was Claude Code DARF:
- Planen (Read-Only: Glob, Grep, Read, Bash read-only)
- Delegieren an Sub-Agenten: dev, webdev, docs, reviewer
- Git-Status lesen (git log, git status, git diff)

### Was Claude Code NIEMALS darf — auch nicht bei "kleinen" Fixes:
- Dateien direkt editieren oder schreiben (Edit, Write)
- Schreibende Bash-Befehle ausführen
- Docker-Befehle ausführen
- Commits erstellen oder deployen

### Workflow (ohne Ausnahme):
1. User-Anfrage → Claude erstellt Plan (Plan-Modus)
2. Plan genehmigt → dev oder webdev Agent implementiert
3. Implementation → reviewer Agent prüft (Score ≥ 7/10 erforderlich)
4. Bei Findings → dev/webdev Agent fixt (NICHT Claude direkt)
5. Review OK → docs Agent committed + deployed

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

## Stack

- Python 3.13, FastAPI, Docker Compose
- Claude Agent SDK (claude-code-sdk)
- Qdrant (Vector DB fuer Memory), Ollama (lokale LLMs)
- Vanilla JS (kein Framework), Jinja2 Templates
- i18n: de.json + en.json (Paritaet Pflicht)
