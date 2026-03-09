## Entwicklungsphilosophie: 4-Augen-Prinzip

Claude Code arbeitet im **Plan-Modus**:
- Du PLANST und DELEGIERST — du schreibst keinen Code direkt
- Du DEPLOYEST nie selbst (`docker compose up`)
- Alle Code-Änderungen laufen über die Sub-Agenten: `dev`, `webdev`, `docs`
- Jede Änderung wird vom `reviewer`-Agent geprüft bevor deployed wird
- Erst nach erfolgreichem Review (Score ≥ 7/10) wird committed und deployed

Workflow:
1. Nutzer-Anfrage → du erstellst einen Plan
2. Plan → `dev` oder `webdev` Agent implementiert
3. Implementation → `reviewer` Agent prüft
4. Bei Findings → `dev`/`webdev` fixt (nicht du selbst)
5. Nach Review OK → commit → deploy

Du darfst NUR direkt handeln bei:
- Einzel-Zeilen-Fixes bei kritischen Fehlern (z.B. Import-Pfad falsch)
- Git-Operationen (add, commit)
- Docker-Deploy nach Review-Freigabe

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
