# HAANA Entwicklungs-Logbuch (DE)

Chronologische Dokumentation aller Aenderungen mit Rollback-Anweisungen.
Dieses Logbuch wird vom `docs`-Agenten gepflegt.

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
