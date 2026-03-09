# HAANA Beta-Tester Guide

Danke fürs Testen! Hier findest du alles was du wissen musst.

## Was testen?

### Pflicht (bitte testen):
- [ ] Installation als HA Addon
- [ ] Setup-Wizard: Ersteinrichtung mit eigenem Provider
- [ ] Chat-Funktion: Nachricht senden, Antwort erhalten
- [ ] Wizard "Erweitern": Zweiten Provider oder User hinzufügen
- [ ] Logs-Tab: Konversationen anzeigen
- [ ] Status-Tab: Alle Checks grün?

### Optional (wenn Zeit):
- [ ] Terminal-Tab: Claude Code starten
- [ ] Voice-Pipeline verbinden
- [ ] Dream-Prozess (Speicher-Konsolidierung aktivieren)

## Bekannte Einschränkungen

- **Terminal-Auth**: Nur Anthropic-Provider für Claude Code (andere kommen noch)
- **Wizard Ollama**: Verbindungstest kann fehlschlagen wenn Ollama auf anderem Host läuft
- **Port 8080**: Kann mit anderen Addons kollidieren → `HAANA_ADMIN_PORT` in docker-compose.yml ändern

## Feedback geben

**GitHub Issues**: https://github.com/[USER]/haana/issues

Bitte angeben:
- HA Version
- Installation (Addon / Standalone)
- Provider (Anthropic / Ollama / andere)
- Schritte zum Reproduzieren

## Rollback

Falls etwas schiefläuft:
```bash
# Letzten Commit rückgängig machen
git revert HEAD

# Auf bestimmten Stand zurück
git checkout <commit-hash>

# Neustart
docker compose up -d --build admin-interface
```

## Logs prüfen

```bash
docker logs haana-admin-interface-1 --tail=50
docker logs haana-qdrant-1 --tail=20
```
