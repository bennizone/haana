# Telegram Channel

Der Telegram-Channel ermöglicht es HAANA-Usern über Telegram-Bots mit ihren
Agenten zu kommunizieren. Pro User wird eine Chat-ID konfiguriert, über die
eingehende Nachrichten dem richtigen Agenten zugeordnet werden. Global wird
ein Bot-Token benötigt, der über @BotFather in Telegram erstellt wird.

## Status: Stub

Dieser Channel ist **noch nicht produktiv nutzbar**. Die Konfigurationsfelder
sind definiert und die ModuleRegistry kann ihn verwalten, aber folgende
Komponenten fehlen noch:

- **telegram-bridge Service**: Python-Prozess der Telegram Updates empfängt
  und an den HAANA-Core weiterleitet (analog zu `whatsapp-bridge/`)
- **Message-Handler**: Eingehende Telegram-Nachrichten parsen und an den
  richtigen Agenten-Endpunkt (`/chat`) weiterleiten
- **Webhook-Registrierung**: Telegram Bot-API Webhook einrichten oder
  Long-Polling implementieren
- **Outbound-Sender**: Antworten vom Agenten zurück an Telegram senden
  (Text, optional Sprach-Nachrichten via TTS)
- **Docker-Service**: `get_docker_service()` in `channel.py` befüllen

## Empfohlene Bibliothek: python-telegram-bot

`python-telegram-bot` (v20+) ist die empfohlene Wahl, weil:
- Aktiv gewartet (Stand 2025: v21.x)
- Async-native (asyncio) — passt zu FastAPI und dem HAANA-Stack
- Umfassende Abstraktion über die Telegram Bot API
- Gute Dokumentation und große Community

Alternative: `aiogram` (ebenfalls async, etwas niedrigerer Level)

## Bridge implementieren — Stichpunkte

1. `channels/telegram/bridge.py` anlegen (analog zu `whatsapp-bridge/index.js`)
2. `Application.builder().token(token).build()` mit python-telegram-bot
3. `MessageHandler` für Textnachrichten: Chat-ID auf User mappen,
   `POST /chat` am Agenten-Endpunkt aufrufen
4. Antwort des Agenten via `context.bot.send_message(chat_id, text)` senden
5. Docker-Service in `channel.py get_docker_service()` eintragen
6. `docker-compose.yml` via ModuleRegistry dynamisch erweitern (zukünftiges Feature)
