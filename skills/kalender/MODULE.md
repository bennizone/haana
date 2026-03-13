# Kalender Skill (CalDAV)

Dieser Skill gibt HAANA-Agenten Zugriff auf Kalendereinträge via CalDAV.
Agenten können Termine abfragen, neue Einträge erstellen und bestehende löschen.
Die Konfiguration erfolgt pro User (jeder User hat seine eigene CalDAV-URL
und Zugangsdaten) — es gibt keine globalen Felder.

## Status: Stub

Die Tool-Definitionen (`get_calendar_events`, `create_event`, `delete_event`)
sind im Anthropic tool_use Schema vorhanden, aber folgende Teile fehlen noch:

- **caldav Python-Bibliothek**: `pip install caldav` — noch nicht in
  `requirements.txt` eingetragen
- **Tool-Handler-Funktionen**: Die eigentliche CalDAV-Logik die aufgerufen
  wird wenn der Agent ein Tool nutzt (in `core/agent.py` oder als
  separates `skills/kalender/handler.py`)
- **MCP-Integration**: Optional — CalDAV via MCP-Server statt nativer Tool-
  Handler (würde Flexibilität erhöhen, z.B. via `caldav-mcp`)
- **Error-Handling**: Netzwerkfehler, ungültige Credentials, fehlende Kalender

## Produktiv machen — Stichpunkte

1. `caldav` zu `requirements.txt` hinzufügen
2. `skills/kalender/handler.py` anlegen mit:
   - `async def get_events(url, user, password, start, end, calendar_name) -> list[dict]`
   - `async def create_event(url, user, password, ...) -> str` (gibt event_id zurück)
   - `async def delete_event(url, user, password, event_id) -> bool`
3. In `core/agent.py` Tool-Aufruf-Dispatch erweitern:
   - Bei `tool_name == "get_calendar_events"` → Handler aufrufen
   - User-Credentials aus Config laden (nie hardcoden)
4. Skill in `admin-interface/main.py` registrieren:
   ```python
   from skills.kalender.skill import KalenderSkill
   registry.register_skill(KalenderSkill())
   ```
5. `get_claude_md_snippet()` wird automatisch in den System-Prompt eingefügt

## Getestete / empfohlene CalDAV-Server

- **Nextcloud**: Vollständige CalDAV-Unterstützung, weit verbreitet,
  URL-Format: `https://nextcloud.example.com/remote.php/dav/calendars/user/`
- **Radicale**: Leichtgewichtig, selbst gehostet, Python-nativ,
  ideal für HAANA-eigene Kalender-Infrastruktur
- **Baikal**: PHP-basiert, einfache Web-UI für Kalender-Verwaltung,
  gute CalDAV-Kompatibilität
- **Apple iCloud** und **Google Calendar**: Prinzipiell möglich via CalDAV,
  aber App-spezifische Passwörter und komplexere Auth erforderlich
