# HAANA Proaktive Benachrichtigungen

HAANA kann proaktive Nachrichten an User senden, ausgeloest durch Home Assistant Automationen.

## Architektur

```
HA-Automation  →  POST /api/notify/webhook  →  Agent (Chat)  →  WhatsApp/Webchat
```

1. Eine HA-Automation sendet einen HTTP-Request an den HAANA Webhook
2. HAANA leitet die Nachricht an den zustaendigen Agent weiter
3. Der Agent formuliert eine passende Benachrichtigung
4. Die Antwort wird an den gewuenschten Channel (WhatsApp, Webchat) zugestellt

## Webhook-API

### POST `/api/notify/webhook`

| Feld       | Typ    | Pflicht | Default     | Beschreibung                              |
|------------|--------|---------|-------------|-------------------------------------------|
| instance   | string | ja      | -           | Agent-Instanz (User-ID, z.B. "alice")     |
| message    | string | ja      | -           | Nachricht / Event-Beschreibung            |
| event      | string | nein    | "generic"   | Event-Typ (fuer Logging/Kontext)          |
| channel    | string | nein    | "whatsapp"  | Ziel-Channel: "whatsapp" oder "webchat"   |
| priority   | string | nein    | "normal"    | "low", "normal", "high", "critical"       |

### Antwort

```json
{
  "ok": true,
  "instance": "alice",
  "event": "washer_done",
  "agent_response": "Hey, die Waschmaschine ist fertig! Zeit zum Aufhaengen.",
  "delivery": {
    "sent": true,
    "channel": "whatsapp",
    "jid": "491234567890@s.whatsapp.net"
  },
  "elapsed_s": 4.2
}
```

### GET `/api/notify/health`

Prueft ob der Notify-Service und die WhatsApp-Bridge erreichbar sind.

## Setup

### 1. Router in main.py einbinden

```python
from core.notify import create_notify_router

notify_router = create_notify_router(
    get_agent_url=lambda inst: _agent_manager.agent_url(inst),
    get_config=load_config,
)
app.include_router(notify_router)
```

### 2. WhatsApp-Bridge /send Endpoint

Die WhatsApp-Bridge (`whatsapp-bridge/index.js`) benoetigt einen `/send` Endpoint
fuer ausgehende Nachrichten. Folgenden Block im HTTP-Server hinzufuegen:

```javascript
if (req.method === "POST" && url === "/send") {
  let body = "";
  req.on("data", (chunk) => body += chunk);
  req.on("end", async () => {
    try {
      const data = JSON.parse(body);
      const jid = data.jid;
      const message = data.message;

      if (!jid || !message) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "jid und message sind Pflichtfelder" }));
        return;
      }

      if (!_sock || _status !== "connected") {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "WhatsApp nicht verbunden" }));
        return;
      }

      await _sock.sendMessage(jid, { text: message });
      log.info({ jid, chars: message.length }, "Proaktive Nachricht gesendet");

      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    } catch (err) {
      log.error({ err: err.message }, "Fehler beim Senden");
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
  });
  return;
}
```

## Beispiel: HA-Automationen

### Waschmaschine fertig

```yaml
automation:
  - alias: "HAANA: Waschmaschine fertig"
    trigger:
      - platform: state
        entity_id: sensor.waschmaschine_power
        to: "idle"
        for:
          minutes: 2
    condition:
      - condition: numeric_state
        entity_id: sensor.waschmaschine_power
        below: 5
    action:
      - service: rest_command.haana_notify
        data:
          instance: "alice"
          event: "washer_done"
          message: "Die Waschmaschine ist fertig. Programm lief seit {{ states('sensor.waschmaschine_laufzeit') }} Minuten."
          priority: "normal"
```

### Haustuer laenger als 10 Minuten offen

```yaml
automation:
  - alias: "HAANA: Haustuer offen Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.haustuer
        to: "on"
        for:
          minutes: 10
    action:
      - service: rest_command.haana_notify
        data:
          instance: "alice"
          event: "door_open_long"
          message: "Die Haustuer ist seit 10 Minuten offen!"
          priority: "high"
```

### Wassersensor Alarm

```yaml
automation:
  - alias: "HAANA: Wasseralarm"
    trigger:
      - platform: state
        entity_id: binary_sensor.wassersensor_keller
        to: "on"
    action:
      - service: rest_command.haana_notify
        data:
          instance: "alice"
          event: "water_leak"
          message: "WASSERALARM: Der Wassersensor im Keller hat Wasser erkannt!"
          priority: "critical"
```

### Temperatur-Warnung

```yaml
automation:
  - alias: "HAANA: Temperatur zu hoch"
    trigger:
      - platform: numeric_state
        entity_id: sensor.serverraum_temperatur
        above: 35
    action:
      - service: rest_command.haana_notify
        data:
          instance: "alice"
          event: "temperature_high"
          message: "Serverraum-Temperatur bei {{ states('sensor.serverraum_temperatur') }}°C!"
          priority: "high"
```

## REST-Command in HA konfigurieren

In `configuration.yaml`:

```yaml
rest_command:
  haana_notify:
    url: "http://haana:8080/api/notify/webhook"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: >
      {
        "instance": "{{ instance }}",
        "event": "{{ event }}",
        "message": "{{ message }}",
        "channel": "{{ channel | default('whatsapp') }}",
        "priority": "{{ priority | default('normal') }}"
      }
    content_type: "application/json"
```

Fuer das HA Add-on wird die URL zu `http://localhost:8080/api/notify/webhook`
(da HAANA im selben Netzwerk laeuft).

## Priorities

| Priority | Verwendung                                    |
|----------|-----------------------------------------------|
| low      | Informationen, die nicht zeitkritisch sind     |
| normal   | Standard-Benachrichtigungen                    |
| high     | Wichtige Alerts (offene Tuer, Temperatur)      |
| critical | Sofortige Aufmerksamkeit noetig (Wasserschaden)|

Aktuell beeinflussen Priorities nur das Logging und werden an die Bridge
weitergegeben. Kuenftig koennten sie z.B. steuern ob eine Sprachnachricht
statt Text gesendet wird, oder ob Benachrichtigungen gebuendelt werden.
