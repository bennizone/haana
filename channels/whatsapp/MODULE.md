# WhatsApp Channel

Ermöglicht die Kommunikation zwischen Usern und HAANA-Agenten via WhatsApp.

## Wie es funktioniert

Die Baileys-basierte Node.js-Bridge (`whatsapp-bridge/`) empfängt eingehende
WhatsApp-Nachrichten und leitet sie an das Admin-Interface weiter
(`POST /api/wa-proxy/{user_id}/chat`). Das Admin-Interface routet sie an den
zuständigen Agenten weiter.

Die Implementierung der Bridge-Kommunikation liegt in
`admin-interface/routers/whatsapp.py`. Diese Channel-Klasse beschreibt
das Konfigurationsschema für die ModuleRegistry.

## Abhängigkeiten

- Node.js 20 (Alpine-Image)
- Baileys (WhatsApp Web Multi-Device API)
- Docker Service: `whatsapp-bridge` (Port 3001 intern)

## Konfigurationsfelder

### Global (`config.json["whatsapp"]`)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `whatsapp_mode` | select | `separate` (eigene Nummer) oder `self` (geteilte Nummer) |
| `whatsapp_self_prefix` | text | Prefix im Self-Modus (z.B. `!h `) |
| `whatsapp_bridge_url` | text | URL der Bridge (Standard: Docker-Servicename) |

### Pro-User (`config.json["users"][]["..."`)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `whatsapp_phone` | text | Telefonnummer (international, ohne +) |
| `whatsapp_lid` | text | LID für Multi-Device (optional, wird automatisch gesetzt) |

## Bekannte Eigenheiten

### JID-Übersetzung
WhatsApp verwendet JIDs (Jabber IDs): `{phone}@s.whatsapp.net`.
Die Bridge übersetzt Telefonnummern automatisch ins JID-Format.
Das Routing in `routers/whatsapp.py` vergleicht JIDs direkt.

### LID-Handling (Multi-Device)
Neuere WhatsApp-Versionen nutzen LIDs statt Telefonnummern für
Multi-Device-Setups. HAANA pflegt beide Routen parallel:
`{phone}@s.whatsapp.net` und `{lid}@lid`.

Die Bridge erkennt LIDs automatisch und meldet sie via
`POST /api/users/whatsapp-lid` an das Admin-Interface zurück.

### Self-Modus
Im Self-Modus (`mode: self`) werden nur Nachrichten verarbeitet die
mit dem konfigurierten Prefix beginnen. Alle anderen Nachrichten werden
ignoriert. Dies ermöglicht die Nutzung der eigenen WhatsApp-Nummer.

### Admin-Modus
Via `/admin`-Slash-Befehl können User in einen Admin-Modus wechseln.
Das Routing übernimmt `core/whatsapp_router.py`.
