# HAANA Modul-System

Dieses Dokument erklärt wie Channels und Skills in HAANA funktionieren und
wie neue Module hinzugefügt werden.

---

## Was sind Channels?

Channels definieren **wie Nachrichten in HAANA reinkommen**. Jeder Channel
repräsentiert einen Kommunikationsweg: WhatsApp, Telegram, HA Voice oder
Web-Chat. Ein Channel bringt seine eigene globale Konfiguration (z.B. Bot-Token)
und seine pro-User-Felder (z.B. Chat-ID) mit und beschreibt optional einen
eigenen Docker-Service (z.B. eine Telegram-Bridge).

## Was sind Skills?

Skills definieren **was ein Agent tun kann**. Sie stellen Tools für den
Claude-Agenten bereit (z.B. Kalender lesen, Einkaufsliste schreiben,
HA-Geräte steuern) und liefern den zugehörigen System-Prompt-Kontext.
Ein Skill kann globale Konfiguration und pro-User-Zugangsdaten haben
(z.B. CalDAV-URL und Passwort pro User).

---

## Neuen Channel hinzufügen

1. Verzeichnis anlegen: `channels/<channel-id>/`
2. `channel.py` erstellen und `BaseChannel` implementieren:
   - `channel_id` und `display_name` setzen
   - `get_config_schema()` — globale Felder zurückgeben
   - `get_user_config_schema()` — pro-User-Felder zurückgeben
   - `is_enabled(config)` — True wenn Channel aktiv ist
3. Optional: `get_docker_service()` für eigene Bridge-Services
4. Channel in `admin-interface/main.py` beim Start registrieren:
   ```python
   from channels.telegram.channel import TelegramChannel
   # In admin-interface/main.py oder ähnlichen Admin-Interface-Dateien:
   from module_registry import registry
   registry.register_channel(TelegramChannel())
   ```
5. `MODULE.md` im Channel-Verzeichnis anlegen (kurze Doku für Entwickler)

## Neuen Skill hinzufügen

1. Verzeichnis anlegen: `skills/<skill-id>/`
2. `skill.py` erstellen und `BaseSkill` implementieren:
   - `skill_id` und `display_name` setzen
   - `get_tools()` — Anthropic tool_use Schema zurückgeben
   - `get_config_schema()` — globale Felder (oder leere Liste)
   - `get_user_config_schema()` — pro-User-Felder zurückgeben
   - `get_claude_md_snippet()` — System-Prompt-Ergänzung
   - `is_enabled(config)` — True wenn Skill aktiv ist
3. Skill in `admin-interface/main.py` beim Start registrieren:
   ```python
   from skills.kalender.skill import KalenderSkill
   # In admin-interface/main.py oder ähnlichen Admin-Interface-Dateien:
   from module_registry import registry
   registry.register_skill(KalenderSkill())
   ```
4. `MODULE.md` im Skill-Verzeichnis anlegen

---

## Beispiel: minimaler Channel-Stub (Telegram)

```python
# channels/telegram/channel.py
from channels.base import BaseChannel, ConfigField

class TelegramChannel(BaseChannel):
    channel_id = "telegram"
    display_name = "Telegram"

    def get_config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="telegram_bot_token",
                label="Bot Token",
                label_de="Bot-Token",
                field_type="password",
                required=True,
                secret=True,
            ),
        ]

    def get_user_config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="telegram_chat_id",
                label="Telegram Chat ID",
                label_de="Telegram Chat-ID",
                field_type="text",
            ),
        ]

    def is_enabled(self, config: dict) -> bool:
        return bool(config.get("telegram_bot_token", "").strip())
```

## Beispiel: minimaler Skill-Stub (Kalender)

```python
# skills/kalender/skill.py
from skills.base import BaseSkill
from channels.base import ConfigField

class KalenderSkill(BaseSkill):
    skill_id = "kalender"
    display_name = "Kalender (CalDAV)"

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "get_calendar_events",
                "description": "Liest Kalendereinträge für einen Zeitraum.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["start_date", "end_date"],
                },
            }
        ]

    def get_config_schema(self) -> list[ConfigField]:
        return []  # Keine globalen Felder

    def get_user_config_schema(self) -> list[ConfigField]:
        return [
            ConfigField(
                key="caldav_url",
                label="CalDAV URL",
                label_de="CalDAV-URL",
                field_type="text",
                required=True,
            ),
        ]

    def is_enabled(self, config: dict) -> bool:
        users = config.get("users", [])
        return any(u.get("caldav_url", "").strip() for u in users)
```

---

## Wo landen globale Felder in der UI?

`get_config_schema()` — sowohl bei Channels als auch bei Skills — liefert
Felder die im Admin-Interface unter **Config → Channels** bzw. **Config → Skills**
als eigener Sub-Tab erscheinen. Diese Felder werden in `config.json` auf
oberster Ebene gespeichert (z.B. `config["telegram_bot_token"]`).

## Wo landen pro-User-Felder in der UI?

`get_user_config_schema()` liefert Felder die automatisch in **jeder User-Karte**
im Users-Tab erscheinen. Die `ModuleRegistry.get_user_config_schema()` führt
alle aktiven Module zusammen. Diese Felder werden in `config.json` unter
`users[].{key}` gespeichert (z.B. `user["telegram_chat_id"]`).

---

## Admin-Interface Integration (Phase 3)

Sobald ein Channel oder Skill registriert ist, erscheint er **automatisch** in der Admin-UI.
Kein Anfassen von HTML oder JavaScript nötig.

### Config-Tab: neue Modul-Sub-Tabs

`get_config_schema()` liefert die globalen Felder eines Moduls. Das Admin-Interface lädt
via `GET /api/modules` alle registrierten Module und erstellt automatisch einen Sub-Tab
im Config-Bereich — sofern mindestens ein Feld vorhanden ist.

**Schritte um einen neuen Channel/Skill in der UI erscheinen zu lassen:**
1. `channel.py` (oder `skill.py`) schreiben mit `get_config_schema()`
2. In `module_registry.py` registrieren
3. Admin-Interface neu starten → Sub-Tab erscheint automatisch

Die Konfigurationswerte werden unter `config.services.{id}.*` gespeichert.

### Skills-Tab

Ein eigener Haupttab "Skills" erscheint automatisch in der Navigationsleiste,
sobald mindestens ein Skill registriert ist. Er zeigt Status (aktiv/inaktiv),
Anzahl konfigurierter Felder und Hinweis bei fehlender Konfiguration.

### User-Karten: dynamische Felder

`get_user_config_schema()` liefert pro-User-Felder. Diese erscheinen automatisch
am Ende jeder User-Karte, gruppiert nach Modul-Name, mit Trennlinie zu bestehenden Feldern.
Werte werden in `config.users[].{key}` gespeichert.

### API-Endpunkte

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/modules` | GET | Alle registrierten Module mit vollständigen Feld-Schemas |
| `/api/modules/config` | GET | Aktuelle Config-Werte aller Module (`services.{id}.*`) |
| `/api/modules/config` | POST | Speichert Config-Werte für Module |
