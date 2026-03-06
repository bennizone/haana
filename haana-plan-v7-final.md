# HAANA – Implementierungsplan v7
## Home Assistant Advanced Nano Assistant

---

## Vision

Ein selbst-gehosteter, persönlicher AI-Assistent für Haushalte. Inspiriert von NanoClaw's Philosophie: minimaler Code, Container-Isolation, jede Zeile hat einen Grund. Von Claude Code entwickelt und gewartet. Community-teilbar, sofort lauffähig ohne GPU, optional erweiterbar.

Langfristiges Ziel: Home Assistant Add-on das jeder mit ein paar Klicks installieren kann.

---

## Kernprinzipien

- **Claude Code SDK** – jede Instanz ist ein Claude Code SDK Agent, wie bei NanoClaw. Kein eigenes Agent-Framework, kein LangChain, kein n8n. Claude Code ist Framework und Ausführungsumgebung in einem.
- **NanoClaw-Philosophie** – minimaler Code, transparent, auditierbar, jede Zeile hat einen Grund
- **HA als zentraler Hub** – HA ist der zuverlässige Kern. HAANA ist der intelligente Assistent drumherum. Steuerung, Automationen, TTS, STT, Timer – alles bleibt bei HA.
- **Alles in Docker** – portabel, isoliert, HA Add-on-fähig
- **Sofort lauffähig** – nur Anthropic API-Key nötig, alles andere optional
- **Multi-User von Anfang an** – skaliert von 1 bis n Personen
- **Claude Code entwickelt** – Alice beschreibt, Claude Code baut und wartet
- **Community-first** – fork, setup.sh, fertig
- **Privacy by design** – sensible Daten verlassen das Heimnetz nie (optional)
- **Logs sind Source of Truth** – rohe Konversationen bleiben erhalten, Qdrant ist der Index

---

## Aktuelle Infrastruktur

### HAANA-Container (läuft)

| Parameter | Wert |
|---|---|
| Proxmox Node | pve2 |
| LXC ID | 1011 |
| Hostname | haana |
| IP | 10.83.1.11/23 |
| OS | Debian 13 |
| Docker | 29.2.1 |
| RAM | 8 GB |
| Disk | 16 GB |
| CPU | 3 Cores |

### GPU-Server (läuft, Ollama bereit)

**Hardware:** Lenovo Tiny, Intel i5 8th Gen (T), 32 GB RAM, GTX 1080Ti (11 GB VRAM), Ubuntu 24.04 LTS, IP: 10.83.1.110/23


| Modell | VRAM | Aufgabe | Ladestrategie |
|---|---|---|---|
| bge-m3 | ~1.2 GB | Embeddings (Deutsch + Englisch) | KEEP_ALIVE=-1 (dauerhaft) |
| ministral-3-32k:3b | ~7.7 GB | Voice Backend + Memory-Extraktion + Traumprozess | KEEP_ALIVE=-1 (dauerhaft) |
| ministral-3:8b | ~6.0 GB | Vision + komplexe Traumprozess-Läufe | on-demand (nicht parallel zu ministral-3-32k:3b) |
| qwen3-vl:8b | ~6.1 GB | Vision-Alternative (Evaluation im Betrieb) | on-demand (nicht parallel zu ministral-3-32k:3b) |

> **ministral-3-32k:3b** ist das gewählte unified Modell: Voice Backend, Memory-Extraktion (infer=True), Traumprozess. Benchmark: 10/10 Tests, 276ms TTFT, 98–104 t/s, 32k Kontext. Erstellt via Ollama Modelfile aus ministral-3b-32k:latest.

> **VRAM-Budget:** bge-m3 (1.2 GB) + ministral-3-32k:3b (7.7 GB) = 9.1 GB von 11 GB. Kein Headroom für ein zweites großes Modell gleichzeitig – ministral-3:8b und qwen3-vl:8b werden on-demand geladen und ersetzen dabei ministral-3-32k:3b temporär im VRAM.

> **Ollama-Konfiguration:** KEEP_ALIVE=-1, NUM_PARALLEL=1, MAX_LOADED_MODELS=2, FLASH_ATTENTION=1. Preload-Service lädt beide Dauermodelle nach jedem Boot automatisch.

> **Energieverbrauch:** ~11W idle (GPU P8-State), bis 280W unter Last. NVIDIA Persistence Mode aktiv.

### Bestehende Infrastruktur

| Service | Status | Details |
|---|---|---|
| Proxmox Cluster | ✅ Läuft | 2 Nodes |
| OPNsense | ✅ Läuft | Firewall / Router |
| TrueNAS | ✅ Läuft | Storage + Backup-Ziel (SMB/CIFS) |
| Home Assistant | ✅ Läuft | Smart Home Hub, 2026.3 Beta |
| Nabu Casa | ✅ Läuft | STT/TTS primär (bereits bezahlt) |
| Wyoming Whisper | ⏳ Noch nicht eingerichtet | HA Fallback STT – für HAANA irrelevant, HAANA steuert nur die HA Assist Pipeline an |
| Piper | ⏳ Noch nicht eingerichtet | HA Fallback TTS – für HAANA irrelevant |
| Trilium Next | ✅ Läuft | LXC + Caddy (Platzhalter, siehe Phase 6) |
| GPU-Server | ✅ Läuft | Bare Metal, GTX 1080Ti, Ollama bereit |
| Pangolin (Hetzner VPS) | ✅ Läuft | Externer Zugang, eigene Auth |
| HAANA LXC | ✅ Phase 1 abgeschlossen | Memory, Scope-Erkennung, Extraktion laufen |

---

## Wie die Agenten funktionieren (Claude Code SDK)

Jede Chat-Instanz (Alice, Bob) ist ein eigenständiger Claude Code SDK Agent:

```python
# Vereinfachtes Beispiel – so sieht eine Instanz aus
from anthropic import Anthropic
import claude_code_sdk

agent = claude_code_sdk.Agent(
    system_prompt=open("instanzen/alice/CLAUDE.md").read(),
    tools=[memory_tool, calendar_tool, ha_tool, shopping_tool, ...],
    model="claude-sonnet-4-5",  # konfigurierbar
)

# Nachricht eingehend (WhatsApp, Webchat, HA App, ...)
response = agent.run(message, context=memory.get_relevant(message))
```

**Was das bedeutet:**
- Kein eigenes Routing-Framework – Claude entscheidet selbst welches Tool wann aufgerufen wird
- Tools sind einfache Python-Funktionen die der Agent aufrufen kann
- CLAUDE.md ist der System-Prompt der Instanz – definiert Persönlichkeit, Berechtigungen, Verhalten
- Skills = Sammlungen von Tools + zugehörigem System-Prompt-Kontext
- Neue Skills: CLAUDE.md erweitern + neue Tool-Funktionen → Git Pull → sofort aktiv

**Warum kein n8n, kein LangChain:**
- n8n hat seinen Platz für Automationen, aber Agent-Logik gehört nicht in Workflow-Tools
- LangChain ist Overhead – Claude Code SDK ist direkter, transparenter, einfacher zu debuggen
- NanoClaw hat bewiesen: SDK direkt reicht, der Rest ist Komplexität um der Komplexität willen

---

## Architektur: Zwei Chat-Instanzen + HA Voice Backend

### Übersicht

| Instanz | Modell | Kanal | Zugriff | Memory |
|---|---|---|---|---|
| Alice (Admin) | Sonnet / Haiku | WhatsApp + Webchat + HA App | Voll + Skill-Management + Konfigurator | alice_memory + household_memory |
| Bob (User) | Sonnet / Haiku | WhatsApp + HA App | Eingeschränkt, kein System-Zugriff | bob_memory + household_memory |
| HA Voice Backend | ministral-3-32k:3b lokal | HA Assist Pipeline | Schlanker Endpunkt, kein Agent | household_memory lesen (Qdrant) |

### Warum diese Aufteilung?

**Alice + Bob** kommunizieren per WhatsApp oder HA App. Latenz spielt keine Rolle – das LLM entscheidet vollständig selbst was zu tun ist. Kein separates Routing nötig.

**HA Voice Backend** ist kein eigenständiger HAANA-Agent. Es ist ein schlanker Endpunkt in der HA Assist Pipeline. Einfache HA-Befehle beantwortet es direkt mit Kontext aus household_memory. Alles darüber hinaus – Kalender, Einkaufsliste, Wetter, komplexe Fragen – delegiert es an die Chat-Instanz der Person die gerade spricht.

---

## HA Voice Pipeline (3-Tier)

HAANA stellt für HA **drei Fake-Modelle** bereit. HA sieht sie wie normale LLM-Endpunkte – in der HA App oder am Voice Satellite wählt man das passende Modell, HAANA weiß sofort welche Instanz und welches Memory aktiv ist:

```
HAANA-Alice   → Anfragen von Alicees Geräten → alice_memory + household_memory
HAANA-Bob    → Anfragen von Bobs Geräten   → bob_memory + household_memory
HAANA-HA      → generische HA-Anfragen       → nur household_memory
```

**3-Tier Ablauf:**

```
Tier 1: HA interner Parser
        → vordefinierte Sätze ("Licht an", "Timer 5 Minuten")
        → null Latenz, kein LLM-Call
        → Timer bleiben bei HA (zuverlässig, kein HAANA-Involvement)
        │
        ▼ (wenn kein Match)

Tier 2: HAANA Voice Backend (ministral-3-32k:3b)
        → HA schickt Anfrage + alle verfügbaren Entities + Status + Presence mit
        → HAANA holt top 3–5 household_memory Einträge aus Qdrant (~50ms, lokal)
        → ministral-3:3b kennt Entities + Vorlieben → antwortet im HA-Format
        → HA führt selbst aus (HAANA berührt nie die HA API zur Steuerung)
        │
        ├── HA-Steuerung erkannt → strukturierte Antwort → HA führt aus
        │
        └── Kein HA-Befehl ("haben wir heute was vor?", "Milch auf die Liste")
                │
                ▼

Tier 3: HAANA Chat-Instanz (Alice oder Bob, async)
        → sofortige TTS-Zwischenantwort: "Moment, ich schaue nach..."
        → vollständiger Agent mit allen Skills: Kalender, Einkaufsliste, Memory, ...
        → TTS-Antwort zurück via HA
```

**Presence kommt von HA:** HA schickt `person.alice` und `person.bob` Status direkt in der Anfrage mit – HAANA muss nichts abonnieren oder abfragen.

**Voice Beta-Status (HA 2026.3):** Wakeword-Loop (Fenster bleibt nach Antwort offen) und Timer-Unterstützung über externe Conversation Agents noch nicht stabil. Handy-App mit manuellem Trigger funktioniert bereits. Voice Satellites werden erst in Phase 5 ausgerollt wenn HA das gelöst hat.

---

## Memory-System (Qdrant + Mem0)

### Memory-Scopes

```
Instanz Alice          Instanz Bob         HA Voice Backend
     │                      │                      │
     ├──► alice_memory       ├──► bob_memory        │
     ├──► household_memory ◄───────┤                      │
     └──────────────────────────────── lesen ───────┘
```

Vier Qdrant-Collections:
- `alice_memory` – Alices persönliche Erinnerungen, Vorlieben, Kontext
- `bob_memory` – Bobs persönliche Erinnerungen, Vorlieben, Kontext
- `household_memory` – gemeinsamer Haushaltskontext, geteilte Vorlieben, Haushaltswissen
- `wissensbasis_docs` – Embeddings der Wissensbasis (Phase 6)

### Kalender-Scopes

```
household_memory:    Familien-Kalender (Bobs iCloud, geteilt)
alice_memory:  Alices persönlicher Kalender
bob_memory:   Bobs persönlicher Kalender
```

### Mem0 Inference-Strategie

**`infer=True` mit ministral-3-32k:3b + Custom Prompt (aktiv seit Phase 1):** ministral-3-32k:3b analysiert die Konversation und extrahiert strukturierte Fakten. Läuft async nach der Antwort an den User, blockiert nichts. Custom Extraction Prompt ersetzt Mem0-Default und berücksichtigt beide Gesprächsseiten (User + Assistant).

```
mem.add(text, infer=True, llm=ministral-3-32k:3b)
    → Custom Prompt (User+Assistant) → Faktenextraktion → bge-m3 Embedding → Qdrant
    → Scope-Klassifikation: LLM entscheidet personal vs. household
```

### Sliding Window + Async Extraktion

Der Kontext-Window ist konfigurierbar. Es gibt keine harte Zeitgrenze – die Nachrichten bleiben solange im Context bis sie sicher embedded sind:

```
Context Window (immer aktiv):
    → letzte N Nachrichten (konfigurierbar, Standard: 20)
    → ODER letzte M Minuten (konfigurierbar, Standard: 60min)
    → mindestens aber die letzten 5 Nachrichten, egal wie alt

Async Extraktion (im Hintergrund):
    → Nachrichten die über das Window hinausgehen → Extraktion via ministral
    → bge-m3 embedded → Qdrant schreibt "OK"
    → erst dann: Nachricht fällt aus dem aktiven Context
    → schlägt Extraktion fehl: Nachricht bleibt im Context (kein Datenverlust)

Beim Embedden gleichzeitig:
    → Anonymisierer-Wörterbuch aktualisieren
      (neue Namen, Orte, Personen erkannt → Liste automatisch ergänzen)
```

### Wann wird wo geschrieben?

```
"Ich mag morgens keinen Kaffee"      → alice_memory
"Bob schläft gerne lange"           → alice_memory (Alicees Aussage über Bob)
"Wir wollen abends warmweißes Licht" → household_memory
"Unser WLAN-Passwort ist..."         → household_memory
"Meine Mutter heißt..."              → alice_memory
```

Bei Unklarheit fragt der Agent nach und gibt Feedback wenn er gespeichert hat. Korrektur jederzeit möglich.

### Traumprozess

HAANA "träumt" wenn beide schlafen – Memory aufräumen, Muster erkennen, Wissen verdichten.

**Trigger (HA Subscription):**
```
person.alice focus mode = "Schlafen"
UND person.bob focus mode = "Schlafen"
UND beide Bedingungen > 30 Minuten aktiv
→ Webhook an HAANA: Traumprozess starten

Fallback: täglich um 03:00 Uhr (auch wenn Subscription nicht ausgelöst hat)
```

**Ablauf (Chunked Processing):**
```
1. Qdrant liefert thematische Cluster (ähnliche Einträge gruppiert)
2. Pro Cluster (~20–50 Einträge):
   → ministral-3-32k:3b (oder konfiguriertes LLM) analysiert
   → Duplikate zusammenführen
     ("Alice mag keinen Kaffee" + "morgens kein Kaffee für Alice" → ein Eintrag)
   → Muster benennen
     ("Alice bestellt freitags oft Pizza" → neuer Fakt)
   → Widersprüche markieren
     ("mag Kaffee" vs "mag keinen Kaffee" → Flag für manuelle Klärung)
   → Anonymisierer-Wörterbuch mit neuen Erkenntnissen ergänzen
3. Ergebnisse zurück in Qdrant, veraltete/doppelte Einträge archiviert
4. Protokoll im Admin-Interface
```

**LLM-Auswahl:** ministral-3-32k:3b reicht für Deduplizierung und einfache Muster. Für komplexe Widerspruchsauflösung kann im Admin-Interface temporär auf ministral-3:8b oder Sonnet umgeschaltet werden – Ollama lädt das Modell automatisch.

---

## Logging – Logs als Source of Truth

Alles wird protokolliert. Logs sind die Grundlage – Qdrant ist nur der Index und kann jederzeit neu aufgebaut werden.

```
/opt/haana/data/logs/
├── conversations/
│   ├── alice/
│   │   ├── 2026-03-01.jsonl   ← jede Nachricht: Timestamp, Kanal, Inhalt
│   │   └── 2026-03-02.jsonl
│   └── bob/
├── llm-calls/                 ← jeder LLM-Call: Prompt + Response + Modell + Latenz
├── memory-ops/                ← jede Write/Read-Operation: Scope, Inhalt, Ergebnis
├── tool-calls/                ← jeder Tool-Aufruf: Parameter + Ergebnis + Dauer
└── dream-process/             ← Traumprozess-Protokolle: was zusammengeführt, was markiert
```

**Warum Logs nie löschen:**
- Wenn bge-m3 gegen ein besseres Embedding-Modell getauscht wird → Qdrant neu aufbauen aus Logs
- Wenn Qdrant korrupt wird → vollständige Rekonstruktion möglich
- Wenn ein neuer Memory-Scope eingeführt wird → Logs rückwirkend neu embedden

**Speicherbedarf:** Textdateien, minimal. Archivierung (zip) auf TrueNAS täglich. Logs selbst werden nicht automatisch gelöscht, nur komprimiert.

---

## Multi-Agent Kommunikation (Alice ↔ Bob)

```
Bob: "Sag Alice er soll Samstag freihalten"
    │
    ▼
Bobs Instanz erkennt: Delegation an Alice
    │
    ▼
POST /api/instanzen/alice/message
    {"from": "bob", "message": "Bob bittet dich Samstag freizuhalten"}
    │
    ▼
Alices Instanz: prüft Kalender → trägt Blocker ein → bestätigt
    │
    ┌──────────────────────────────────────────────┐
    ▼                                              ▼
Bobs Instanz → WhatsApp Bob:           Alices Instanz → WhatsApp Alice:
"Erledigt, Samstag ist bei              "Bob hat Samstag in deinem
Alice blockiert."                        Kalender blockiert."
```

Beide werden informiert – keine stummen Aktionen im Hintergrund.

---

## HA als zuverlässiger Kern – Proaktive Benachrichtigungen

HA ist die erste und zuverlässige Schicht für alle Alarme und Benachrichtigungen. HAANA ist der zusätzliche intelligente Layer – aber nie die einzige Schicht.

```
Ereignis (Wassersensor, Haustür offen, Waschmaschine fertig, ...)
        │
        ▼
HA Automation (immer zuverlässig, auch ohne HAANA / Internet)
        ├── TTS auf Lautsprechern sofort
        ├── HA App Push-Notification
        └── Webhook an HAANA (zusätzlich, wenn erreichbar)
                │
                ▼
           HAANA wertet Kontext aus:
           - WhatsApp an Alice + Bob
           - Presence: nur wer home ist benachrichtigen
           - Memory: "Alice schläft normalerweise bis 9" → kein Alert vor 9
           - Rückfrage wenn sinnvoll ("Soll ich die Heizung runterregeln?")
```

**Fällt HAANA aus oder WhatsApp streikt:** HA hat bereits reagiert. Nichts geht unter.

**HAANA erstellt HA-Automationen per Chat** (Phase 4): Alice beschreibt was er will, HAANA schreibt die YAML-Automation und legt sie in HA an. HA macht automatisch ein Backup vorher. Die Automation gehört danach HA – nicht HAANA.

### HA Entity Subscriptions

Subscriptions ausschließlich für **proaktive Szenarien** – Dinge die HAANA von sich aus anstößt:

```
Sinnvoll:                                   Nicht nötig:
──────────────────────────────────          ─────────────────────────────────
Waschmaschine fertig → WhatsApp             Presence → kommt mit HA-Anfrage mit
Haustür offen > 10min → WhatsApp            Entity-Status → HA schickt mit
Wassersensor → sofortiger Alert             Vorlieben → kommen aus household_memory
person.X home → personalisierte Begrüßung
Alarm aktiv → TTS + WhatsApp
Beide schlafen > 30min → Traumprozess
```

---

## LLM-System

### Chat-Instanzen (Alice/Bob)

Kein separates Routing-LLM. Sonnet/Haiku entscheidet vollständig selbst. Kein einfach/komplex Split.

### LLM-Auswahl pro Use Case

Dropdowns dynamisch befüllt – Ollama API beim Start abgefragt, kombiniert mit bekannten Cloud-Modellen.

| Use Case | Standard | Fallback |
|---|---|---|
| Chat WhatsApp / Webchat | Sonnet | Haiku |
| HA Voice Tier 2 | ministral-3-32k:3b lokal | ministral-3:8b lokal |
| HA Voice Tier 3 (Delegation) | Haiku | Sonnet |
| Vision (Rezept-Fotos) | ministral-3:8b oder qwen3-vl:8b (wählbar) | Sonnet |
| Memory-Extraktion (infer=True) | ministral-3:8b lokal | – |
| Traumprozess | ministral-3-32k:3b lokal | ministral-3:8b / Sonnet (konfigurierbar) |
| Embeddings | bge-m3 lokal | OpenAI text-embedding-3-small |
| Daily Brief | Haiku | ministral-3-32k:3b lokal |

### LLM-Kaskade (= Failover, kein Routing)

```
Anfrage eingehend
    │
    ├── Anonymisierer aktiv? → sensible Daten ersetzen (nur Cloud-Calls)
    │
    ├── Lokal konfiguriert + verfügbar? → Ollama (GPU-Server)
    └── Sonst → Cloud primär (Anthropic API)
                    │
                    └── Fehler / Timeout? → Cloud Fallback (MiniMax)
                                                │
                                                └── Fehler? → Ollama / Fehlermeldung
    │
    └── Antwort → Anonymisierer: Platzhalter zurücksetzen
```

### Provider-Konfiguration

```
Slot 1 – Primär:   Anthropic claude-sonnet-4-6 (OAuth via Claude Code CLI)
Slot 2 – Fallback: Anthropic claude-haiku-4-5 (OAuth)
Slot 3 – Lokal:    Ollama ministral-3-32k:3b (GPU-Server, openai-kompatibel)
Slot 4 – Custom:   MiniMax MiniMax-M2.5 (anthropic-kompatibel, custom URL + Key)
```

Jeder Slot: Typ / Base URL / API-Key / Modell (Freitextfeld, überschreibbar). "Teste Verbindung" Button pro Slot.

---

## STT / TTS über Home Assistant

```
WhatsApp Sprachnachricht (.ogg)       HA App / Voice Satellite
        │                                      │
        ▼                                      ▼
  POST /api/stt an HA               HA Assist Pipeline
        │                                      │
        ▼                                      ▼
  Nabu Casa STT (primär)            Nabu Casa STT (primär)
  Wyoming als HA-Fallback*          Wyoming als HA-Fallback*
        │                                      │
        ▼                                      ▼
  Transkription → HAANA Agent       Transkription → HAANA Voice Backend

TTS: Text → POST /api/tts_proxy an HA → Audio → WhatsApp / Lautsprecher

* Wyoming + Piper noch nicht eingerichtet – für HAANA irrelevant solange Nabu Casa läuft
```

---

## Skills

```
haana/
├── skills/
│   ├── kalender/              ← CalDAV, user-spezifisch (3 Kalender)
│   ├── [home-assistant/]       ← via MCP (89 Tools): Entities, Automationen, Shopping, Backup
│   ├── ha-subscriptions/      ← Entity-Abonnements, Webhooks, proaktive Reaktionen
│   ├── morning-brief/         ← Daily Brief (Termine, Wetter, Erinnerungen)
│   ├── monitoring/            ← Proxmox, TrueNAS, OPNsense-Status
│   ├── rezepte/               ← Foto → Vision → Wissensbasis (Phase 6)
│   ├── wissensbasis/          ← Lesen/Schreiben/Suchen (Phase 6, Backend offen)
│   └── [weitere per Skill-File hinzufügbar]
├── instanzen/
│   ├── alice/CLAUDE.md        ← Admin: voller Zugriff, Skill-Management, Konfigurator
│   └── bob/CLAUDE.md         ← User: eingeschränkt, kein System-Zugriff
├── voice-backend/
│   └── main.py                ← Schlanker Endpunkt, drei Fake-Modelle, kein Agent
├── core/
│   ├── agent.py               ← Claude Code SDK Agent Basis
│   ├── memory.py              ← Mem0 + Qdrant Wrapper + Sliding Window
│   ├── channels.py            ← WhatsApp, Webchat, HA App
│   ├── cascade.py             ← LLM-Failover Logik
│   ├── dream.py               ← Traumprozess: Chunked Processing, Clustering
│   └── logger.py              ← Strukturiertes Logging aller Operationen
└── docker-compose.yml
```

**Berechtigungen stehen in CLAUDE.md, nicht im Skill-Code.** Neue Skills: Ordner anlegen + CLAUDE.md erweitern + Git Pull → sofort aktiv.

### User-spezifische Dienste

| Dienst | Scope | Beispiel |
|---|---|---|
| CalDAV | Pro User + Haushalt | Familien-iCloud (geteilt), Alices CalDAV, Bobs iCloud |
| IMAP / SMTP | Pro User | Alices Mailbox |
| WhatsApp-Nummer | Pro User | Alices +49..., Bobs +49... |
| HA Person-Entity | Pro User | `person.alice`, `person.bob` |
| HA Focus Mode Entity | Pro User | für Schlaf-Trigger Traumprozess |

---

## Admin-Webinterface

Erreichbar unter `http://10.83.1.11:8080`. Nur im LAN. Kein externer Zugang über Pangolin geplant. Simple Auth (Username/Password) oder zunächst offen – beides akzeptabel.

### Chat-Tab

Echter gemeinsamer Chatverlauf über alle Kanäle. Eine Session, mehrere Eingabekanäle.

**User-Dropdown:** Alice (Admin) / Bob (simuliert für Tests)

**Kanalindikator:** 📱 WhatsApp / 🖥️ Webchat / 🏠 HA App

**Jede Nachricht aufklappbar:**
```
► [10:34] "Mach das Licht im Wohnzimmer warm"    📱 WhatsApp
   ▼ aufklappen:
   [Memory geladen]     3 Treffer aus household_memory: "Wohnzimmer-Vorlieben", ...
   [Tool aufgerufen]    ha_control(entity="light.wohnzimmer", color_temp=2700K)
   [HA Antwort]         OK, Zustand: an, 2700K, 80%
   [Memory gespeichert] household_memory: "Abends warmweißes Licht Wohnzimmer"
   [Antwort]            "Wohnzimmer auf warmweiß gedimmt."
```

### Config-Tab

**Nutzer:**
- Hinzufügen, bearbeiten, Memory zurücksetzen, löschen
- Pro User: Name, WhatsApp-Nummer, Typ (Admin/User), HA Person-Entity (Dropdown aus HA API), HA Focus Mode Entity
- Persönliche Dienste: CalDAV, IMAP, SMTP

**CLAUDE.md:** Direkt im Browser editieren, Syntax-Highlighting, sofort aktiv ohne Neustart

**Skills:** Aktivieren/Deaktivieren pro Instanz, Status + letzter Fehler

**LLM-Konfiguration:**
- Provider-Slots (4x): Typ / URL / Key / Modell
- Pro Use Case: Primärmodell + Fallback (Dropdowns)
- "Teste Verbindung" Button pro Slot

**Memory + Sliding Window:**
- Anzahl Nachrichten im Context Window (Standard: 20, Minimum: 5)
- Zeitfenster (Standard: 60 Minuten)
- Async Extraktion: Status, letzte Ausführung, Fehlerzähler

**Traumprozess:**
- LLM: Dropdown (ministral-3:3b / ministral-3:8b / Sonnet / ...)
- Cluster-Größe: 10–100 Einträge pro Batch
- Trigger: HA Subscription (Schlaf-Focus) + Fallback-Zeit (Standard: 03:00)
- Manuell auslösen: [Button]
- Letzter Lauf: Zeitstempel + Zusammenfassung (was zusammengeführt, was markiert)
- Protokoll: aufklappbar

**Dienste global:** HA URL + Token, Ollama URL

**Backup:** SMB/CIFS Ziel, Credentials, Zeitplan, Retention, manuell auslösen

**Anonymisierer:** Aktivieren/Deaktivieren, bekannte Namen verwalten, automatisch erkannte anzeigen

**HA Subscriptions:** Aktive Abonnements mit Entity / Bedingung / Aktion, pausieren / löschen

**Logs:** Übersicht letzte Einträge pro Kategorie, Download, Archivstatus

---

## Datenhaltung + Zugangsdaten

```
/opt/haana/data/
├── qdrant/          ← alle Memory-Collections (Index, rekonstruierbar aus Logs)
├── config/          ← API-Keys, User-Settings, Credentials (Plaintext, nur LAN)
├── claude-md/       ← CLAUDE.md aller Instanzen (versioniert via Git)
└── logs/
    ├── conversations/alice/     ← täglich rotiert, nie gelöscht
    ├── conversations/bob/
    ├── llm-calls/
    ├── memory-ops/
    ├── tool-calls/
    └── dream-process/

Backup: täglich → SMB/CIFS → TrueNAS
    → Logs: komprimiert (zip), unbegrenzt aufbewahren
    → Qdrant + Config: komprimiert, 7 Tage Retention
    → Restore: /data zurückkopieren → docker compose up -d → fertig
```

**Zugangsdaten:** Plaintext in `config/`, nur auf dem LXC, kein externer Zugang. Authentik/Vault kommt auf die "für später"-Liste wenn sowieso ein einheitliches Auth-System für alle Self-Hosted-Dienste kommt.

---

## Anonymisierer (optional)

Im Setup und Konfigurator aktivierbar. Gilt **nur** für Cloud-LLMs, **nie** für lokales Ollama.

```
Original:  "Bob hat Termin bei Dr. Müller in der Musterstraße"
An Cloud:  "[USER_2] hat Termin bei [PERSON_1] in [ADDR_1]"
Antwort:   "Termin für [USER_2] bei [PERSON_1] eingetragen"
Zurück:    "Termin für Bob bei Dr. Müller eingetragen"
```

**Wörterbuch-Pflege:** Wird beim Embedding automatisch erweitert – neue Namen und Orte die erkannt werden kommen automatisch in die Liste. Manuell ergänzbar im Admin-Interface.

API-Keys und Passwörter gehen grundsätzlich nie ans LLM – separate, immer aktive Sicherheitsschicht, unabhängig vom Anonymisierer.

---

## Docker-Stack

```
docker-compose.yml
├── instanz-alice          (Python, Claude Code SDK Agent, Admin)
├── instanz-bob           (Python, Claude Code SDK Agent, User)
├── haana-voice-backend    (Python, schlanker Endpunkt, drei Fake-Modelle)
├── admin-interface        (Web-UI, Port 8080, nur LAN)
├── whatsapp-bridge        (Baileys, Node.js)
├── qdrant                 (Vector Store, Port 6333)
├── mem0                   (Memory Layer)
└── ollama                 (optional – wenn kein externer GPU-Server)

Nicht im Stack (extern, bereits laufend):
├── Ollama GPU-Server      (GTX 1080Ti, alle Modelle geladen)
└── Trilium                (eigener LXC + Caddy)
```

---

## Setup-Wizard

```
Schritt 1: Nutzer anlegen
→ Pro Nutzer: Name, Typ (Admin/User), WhatsApp-Nummer (optional)
→ HA Person-Entity: Dropdown aus HA Persons API (live abgefragt)
→ HA Focus Mode Entity: für Schlaf-Trigger (optional)
→ CalDAV URL + Credentials pro User (optional)
→ IMAP / SMTP pro User (optional)

Schritt 2: Dienste (global)
→ Ollama: bestehender Server im Netzwerk / lokaler Container / kein Ollama
→ Wissensbasis: bestehende Instanz / Docker / überspringen

Schritt 3: LLM-Provider
→ Primär: Anthropic API-Key (empfohlen) oder Claude.ai Subscription
          (⚠ nur privat, nicht für exzessiven Betrieb)
→ Fallback: MiniMax oder Custom (Typ + URL + Key + Modell)
→ Lokale Modelle: automatisch von Ollama API abgefragt

Schritt 4: LLM pro Use Case
→ Dropdowns mit verfügbaren Modellen (Cloud + Ollama kombiniert)

Schritt 5: Home Assistant
→ HA URL + Long-Lived Access Token
→ Verbindung testen → Entities + Persons abrufen
→ Nabu Casa vorhanden? (STT/TTS)

Schritt 6: Backup
→ SMB/CIFS Ziel, Credentials, Zeitplan, Retention

Schritt 7: Privacy
→ Anonymisierer aktivieren?

→ Fertig: docker-compose.yml generiert, docker compose up -d
→ Admin-Interface: http://10.83.1.11:8080
```

**Als HA Add-on (zukünftig):** Schritt 5 entfällt.

---

## Phasenplan

### Phase 1 – Fundament ✅ Abgeschlossen

**Core Agent (`core/agent.py`):**
- `HaanaAgent` auf Basis Claude Code SDK – persistenter Subprocess (kein ~5s Startup-Overhead pro Nachricht)
- Session-Kontinuität, Lazy-Init, Graceful Shutdown mit flush → persist → close
- REPL-Modus für lokale Tests, API-Modus wenn `HAANA_API_PORT` gesetzt (Docker-kompatibel)
- Memory-Kontext wird dem Prompt vorangestellt (`<relevante_erinnerungen>`)

**Memory-Layer (`core/memory.py`):**
- Mem0 + Qdrant, Collections: `alice_memory`, `bob_memory`, `household_memory`
- Embeddings: bge-m3 via Ollama (1024 dims)
- Extraktion: ministral-3-32k:3b mit `infer=True`, async nach Antwort, blockiert nichts
- Sliding Window (20 Nachrichten / 60 min): non-blocking async Extraktion im Hintergrund
- `flush_all()` beim Shutdown: alle Window-Einträge zu Qdrant extrahieren (kein Datenverlust)
- Context-File (`data/context/alice.json`): Window-State überlebt Container-Restarts
- Pending-Extraktion beim Startup: unfertige Einträge aus letzter Session werden nachgeholt
- Scope-Erkennung: 1) Regex aus Agent-Antwort → 2) LLM-Klassifikation via Ollama (personal vs. household) → 3) Fallback persönlicher Scope
- Custom Fact Extraction Prompt für Mem0: berücksichtigt User- UND Assistant-Nachrichten (Mem0 Default ignoriert Assistant)
- Memory Rebuild aus Konversations-Logs im Admin-Interface (mit Scope-Klassifikation pro Eintrag)

**Agent HTTP-API (`core/api.py`):**
- FastAPI pro Agent-Instanz
- `POST /chat` → `{"message": "...", "channel": "webchat|whatsapp|..."}` → `{"response": "..."}`
- `WS /ws` → WebSocket bidirektional
- `GET /health` → Instanz-Status

**Logging (`core/logger.py`):**
- 4 JSONL-Kategorien mit Daily Rotation, nie gelöscht:
  - `conversations/{instance}/YYYY-MM-DD.jsonl`
  - `memory-ops/YYYY-MM-DD.jsonl`
  - `tool-calls/YYYY-MM-DD.jsonl`
  - `llm-calls/YYYY-MM-DD.jsonl`

**Admin-Interface (`admin-interface/`):**
- FastAPI + Jinja2 + Vanilla JS, Port 8080
- Tabs: Chat, Logs (inkl. Log-Dateien), Config (Sub-Tabs: LLMs / Memory / Services / Retention / CLAUDE.md), Users, Status
- Config → LLMs: 4 Provider-Slots als Akkordeon, LLM-Zuordnung per User (nicht global)
- Config → Services: HA REST API + Test-Button, HA MCP-Konfiguration + Test, WhatsApp Bridge, STT/TTS, Infrastruktur
- Config → Retention: Log-Aufbewahrungsfristen konfigurierbar
- Users-Tab: Expandierbare Karten, CLAUDE.md Inline-Editor pro User, Dropdown HA Person-Entity
- Chat-Tab: kanalübergreifend, SSE Live-Updates, Agent-Online/Offline-Status
- i18n: Key-basiertes Übersetzungssystem (de.json + en.json, ~220 Keys), `t()` Funktion, `data-i18n` Attribute, Sprachauswahl im Header
- Design: Modernisiert mit Glassmorphism, Gradient-Buttons, CSS Custom Properties, Dark Theme
- Responsive: Mobile-first CSS, Breakpoints bei 640px und 1024px
- Modular: CSS extrahiert (admin.css), JS-Utilities extrahiert (i18n.js, utils.js, modal.js)
- Modal-System: Callback-basiert, ersetzt alle `confirm()`-Dialoge
- Restart-Detection: Erkennt welche Config-Änderungen Container-Neustarts erfordern, bietet Restart an

**Docker Compose:**
- `qdrant`, `admin-interface` immer aktiv
- `instanz-alice` (Port 8001), `instanz-bob` (Port 8002), `whatsapp-bridge` unter Profil `agents`
- `instanz-ha-assist`, `instanz-ha-advanced` vorbereitet (System-Instanzen, nicht user-erstellbar)

**WhatsApp-Bridge (`whatsapp-bridge/`):**
- Baileys + Node.js, Routing via Admin-Interface `/api/whatsapp-config`
- JID-Allowlist: Bridge ignoriert Nachrichten von unbekannten Nummern stillschweigend
- Routing-Tabelle: Bridge pollt `/api/whatsapp-config` alle 5 Min. → kein Neustart bei neuem User
- WhatsApp-Modus global konfiguriert (Separate Nummer / An mich selbst + Prefix)
- HTTP-API (Port 3001): `/status`, `/qr` (Base64-PNG), `/logout`
- LID-Handling: Neuere WhatsApp-Versionen senden LID statt Phone-JID → `translateJid()` mit lokalem Cache + `signalRepository`-Fallback (nach NanoClaw-Strategie), pro User optionales `whatsapp_lid` Feld als Routing-Fallback
- QR-Code Linking/Unlinking im Admin-Interface (Dienste-Tab): Status-Anzeige, QR-Code scanbar, Trennen-Button, Auto-Polling
- `makeCacheableSignalKeyStore` für besseres Key-Caching (NanoClaw-Strategie)

---

### Phase 2 – Erster Alltagskanal

**Ziel:** Alice hört auf SSH. Erster echter Alltagskanal.

**Bereits in Phase 1 vorgezogen ✅:**
- Sliding Window + Async Extraktion
- Logging-Infrastruktur (alle 4 Kategorien)
- Admin-Interface inkl. Config-Tab, Users-Tab, CLAUDE.md-Editor
- LLM-Provider-Slots (4x Akkordeon), LLM-Zuordnung per User
- WhatsApp-Bridge komplett inkl. JID-Allowlist, Config-Polling, LID-Handling, QR-Code im Admin-Interface

**Bereits in Phase 2 erledigt ✅:**
- WhatsApp-Bridge: QR-Code Linking/Unlinking im Admin-Interface
- WhatsApp-Bridge: Inbetriebnahme, Alice chattet per WhatsApp mit Agent
- LID→Phone-Auflösung (NanoClaw-Strategie), Dual-Routing (Phone-JID + LID)
- STT: WhatsApp Sprachnachrichten (.ogg) → Baileys `downloadMediaMessage` → `POST /api/stt/stt.home_assistant_cloud` an HA (Nabu Casa) → Transkription → `[Sprachnachricht: ...]` an Agent
- STT-Konfiguration (Entity, Sprache) dynamisch via `/api/whatsapp-config` aus Admin-Interface
- Memory Scope-Klassifikation: LLM-basiert (Ollama) für automatische personal/household Zuordnung
- Custom Mem0 Extraction Prompt: berücksichtigt beide Gesprächsseiten (User + Assistant)
- TTS: Antwort → `POST /api/tts_proxy` an HA → OGG Opus Audio → WhatsApp, Voice-Auswahl im Admin-Interface, sprachoptimierter Prompt
- TTS auch als Text: Antwort wahlweise zusätzlich als Textnachricht (neben Sprachnachricht)
- Admin-Interface modernisiert: CSS/JS extrahiert, i18n-System, Modal-System, Responsive Design, Design-Modernisierung, Restart-Detection

**Weitere erledigte Aufgaben ✅:**
- JS-Extraktion: ~1700 Zeilen inline JS in 7 separate Module extrahiert (app.js, chat.js, config.js, users.js, status.js, logs.js, whatsapp.js)
- HA MCP Integration: Dual-Support für Built-in (6 Tools, SSE) und Extended ha-mcp Add-on (89 Tools, HTTP). Typ-Auswahl im Admin-Interface
- Config-Tabs umstrukturiert: Services → Home Assistant / WhatsApp / Infra (logische Gruppierung)
- HA Auto-Backup: Konfigurierbar im Admin-Interface, Agent erstellt HA-Backup vor Automations-/Script-Änderungen
- MCP-Typ-Auswahl: Admin kann zwischen Built-in (SSE, 6 Tools) und Extended (HTTP, 89 Tools) MCP wählen
- Test-Suite: 44 Unit-Tests (test_agent, test_config, test_i18n, test_memory)
- Integration-Test: Automatisierter End-to-End-Test (User-CRUD, Chat, MiniMax, MCP, Memory, User-Setup-Verifizierung)
- Multi-Agent Development: 4 spezialisierte Agenten (Webinterface, Review, Test, Docs) mit Briefing-Dokumenten

**Noch offen:**
- Admin-Interface: Restliche hardcoded deutsche Strings in dynamischem JS durch `t()`-Aufrufe ersetzen
- Admin-Interface: Claude Code OAuth-Login im Webinterface ermöglichen (Token-Refresh ohne SSH)
- Backup auf TrueNAS: SMB/CIFS, täglich, Logs unbegrenzt / Qdrant 7 Tage
- Docker Image Optimierung: Agent-Images 10.5 GB wegen PyTorch/CUDA (sentence-transformers). CPU-only oder entfernen → ~1-2 GB

**Ergebnis:** Alice chattet per WhatsApp (Text + Sprache, bidirektional). Agent kennt ihn bereits (Phase 1 Memory). STT + TTS via Nabu Casa. Admin-Interface unter `http://10.83.1.11:8080` zugänglich, responsiv, mehrsprachig vorbereitet.

---

### Phase 3 – Kalender + Bob einladen

**Ziel:** Kalender integriert. Bob bekommt Zugang mit echtem Mehrwert gegenüber ChatGPT.

**Aufgaben:**
- CalDAV-Skill: Familien-Kalender (geteilt), Alices Kalender, Bobs Kalender
- Termine lesen, eintragen, Kalender-Übersicht
- Daily Brief Skill: morgens automatisch, Termine des Tages + Wetter
- Bob-Instanz freischalten: WhatsApp + HA App
- Multi-Agent Kommunikation: interne `/message` API, beide werden benachrichtigt
- household_memory Feedback-Loop für Kalender
- Admin-Interface: Nutzer-Verwaltung, Bob anlegen, Memory-Einstellungen

**Ergebnis:** Bob hat vom ersten Tag Kalender + Memory + gemeinsamer Kontext. Kein Voice-Zwang – tippen reicht.

---

### Phase 4 – Home Assistant Integration

**Ziel:** HA-Steuerung per Chat, HAANA in Voice Pipeline, proaktive Benachrichtigungen.

**HA Chat-Steuerung (großteils durch MCP abgedeckt ✅):**
- ~~HA-Skill: Entities steuern, Status abfragen, Szenen aktivieren~~ → MCP Tools (89 Tools via ha-mcp Add-on)
- ~~HA-Skill: Automationen per Chat erstellen~~ → MCP Tools + Auto-Backup (konfigurierbar im Admin-Interface)
- ~~Einkaufsliste-Skill: HA Shopping List~~ → MCP Tools (todo/shopping list)
- Monitoring-Skill: Proxmox, TrueNAS, OPNsense Uptime (nicht HA, separater Skill nötig)

**HAANA Voice Backend:**
- Drei Fake-Modelle: HAANA-Alice, HAANA-Bob, HAANA-HA
- Qdrant-Lookup household_memory (~50ms) vor jedem Tier-2-Call
- 3-Tier: HA Parser → HAANA Voice Backend → Chat-Instanz (async mit Zwischenantwort)
- In HA Assist Pipeline einbinden als externer Conversation Agent

**Proaktive Benachrichtigungen:**
- HA Subscriptions Skill: Entities abonnieren, Webhooks empfangen
- HA Automation immer erste Schicht (TTS + Push, auch ohne HAANA)
- HAANA zweite Schicht: WhatsApp + Kontext aus Memory
- Admin-Interface: Subscriptions-Tab

**Traumprozess:**
- Schlaf-Subscription: beide Focus Mode "Schlafen" > 30min → Trigger
- Fallback: täglich 03:00 Uhr
- Admin-Interface: Traumprozess-Konfiguration, Protokoll

**Ergebnis:** "Alexa kann weg." Chat-Steuerung, Voice per Hand-Trigger, proaktive Alerts, HA bleibt zuverlässiger Kern.

---

### Phase 5 – Voice Satellites

**Ziel:** Hands-free Sprachsteuerung wenn HA Beta-Probleme gelöst sind.

**Voraussetzungen (HA-seitig):**
- Wakeword-Loop fix (Fenster bleibt nach Antwort aktiv)
- Timer-Unterstützung über externe Conversation Agents stabil
- HA 2026.x produktionsreif

**Aufgaben:**
- Dedicated Voice Satellite Hardware aufsetzen
- Pro Satellite richtiges Fake-Modell in HA Pipeline wählen (HAANA-Alice / HAANA-Bob)
- HAANA Voice Backend bereits bereit aus Phase 4

**Ergebnis:** Hands-free "Hey HAANA, mach das Licht warm" → direkt mit Vorlieben.

---

### Phase 6 – Wissensbasis

**Ziel:** Gemeinsame durchsuchbare Wissensbasis für Rezepte, Dokumente, Haushaltswissen.

**Status:** Trilium läuft, Single-User, API gut. Bleibt Platzhalter bis Multi-User-Lösung sinnvoll. Entscheidung offen – Outline (braucht Auth-Provider), AppFlowy (API noch jung). Wenn Auth-System (Authentik o.ä.) sowieso kommt, wird gleichzeitig Wissensbasis evaluiert.

**Aufgaben wenn bereit:**
- Wissensbasis-Skill: Lesen, Schreiben, Suchen per API
- Embedding-Sync: Dokumente → bge-m3 → Qdrant `wissensbasis_docs`
- Webhook oder periodischer Sync für geänderte Dokumente
- Rezept-Pipeline: WhatsApp-Foto → Vision-Modell → strukturiertes Rezept → Wissensbasis

---

### Phase 7 – Optimierung + Community

- OLLAMA_KEEP_ALIVE und OLLAMA_NUM_PARALLEL tunen
- Vision-Modell evaluieren: ministral-3-32k:3b vs ministral-3:8b vs qwen3-vl:8b im echten Betrieb
- Daily Brief persönlicher, kontextsensitiver
- Setup-Wizard polieren, README für Community
- GitHub Repo public
- HA Add-on Paketierung (HAOS-kompatibel, Schritt 5 im Setup-Wizard entfällt)

---

## Für später – Offene Punkte

**Features:**
- Bring! Integration: Rezepte → konsolidierte Zutatenliste → Bring! API → Abgleich mit Vorrat
- Kamera-Skill: "Zeig mir die Haustür" per WhatsApp (Vision-Modell bereit, Kamera fehlt noch)
- Paperless-NGX Integration: Dokumente ablegen, Assistent kann darin nachschlagen
- Telegram als Fallback-Kanal bei WhatsApp-Sperre
- Radarr/Sonarr Skills
- Graph-Memory (Neo4j) für komplexere Zusammenhänge zwischen Erinnerungen
- Wyoming Whisper + Piper einrichten als HA-Fallback STT/TTS

**Infrastruktur:**
- LLM-Fallback für Memory-Operationen: Scope-Klassifikation + Extraktion nutzen konfigurierte Provider-Slots (Primär → Fallback, z.B. Ollama → MiniMax). cascade.py aktivieren, analog zur geplanten Chat-Kaskade
- Authentik oder Keycloak als einheitliches Auth-System für alle Self-Hosted-Dienste
- Multi-User-Wissensbasis (Outline/AppFlowy) wenn Auth-System steht
- MariaDB direkter HA-Zugriff (fragil wegen undokumentiertem Schema, vorerst Webhook-Weg)
- HA Add-on Store Veröffentlichung (Phase 7)

**Evaluation:**
- bge-m3 + ministral-3-32k:3b als lokaler Stack: Extraktion und Voice bestätigt, Vision noch zu evaluieren
- Vision-Qualität: ministral-3-32k:3b vs ministral-3:8b vs qwen3-vl:8b im echten Betrieb
- Traumprozess-Qualität: ministral-3-32k:3b ausreichend oder größeres Modell nötig?
- HA MCP vs REST API: ✅ Evaluiert – Extended ha-mcp Add-on (89 Tools) als Standard, Built-in (6 Tools) als Fallback. MCP macht viele geplante Skills obsolet (ha-automations, einkaufsliste, HA-Steuerung)

---

## Technische Referenzen

| Projekt/Tool | Zweck | URL |
|---|---|---|
| NanoClaw | Philosophie + Ausgangspunkt | github.com/qwibitai/nanoclaw |
| Anthropic SDK / Claude Code | Agent-Basis, SDK | github.com/anthropics/anthropic-sdk-python |
| Baileys | WhatsApp Bridge (Node.js) | github.com/WhiskeySockets/Baileys |
| Mem0 | Memory Layer | github.com/mem0ai/mem0 |
| Qdrant | Vector Store | qdrant.tech |
| Anthropic API | Primäres LLM | api.anthropic.com |
| MiniMax | Cloud Fallback LLM | api.minimaxi.chat |
| Ollama | Lokale Modelle (GPU-Server) | ollama.ai |
| HA REST API | STT, TTS, Steuerung, Presence, Webhooks | developers.home-assistant.io |
| Nabu Casa | STT/TTS primär (bereits vorhanden) | nabucasa.com |
| Pangolin | Externer Zugang (Hetzner VPS) | github.com/fosrl/pangolin |
| Trilium Next | Wissensbasis Platzhalter | github.com/TriliumNext/Notes |

---

## Hinweise für Claude Code

- **Kein eigenes Agent-Framework bauen** – direkt Claude Code SDK verwenden wie NanoClaw
- **CLAUDE.md ist der System-Prompt** – Berechtigungen und Persönlichkeit gehören dorthin
- **Tools sind einfache Python-Funktionen** – keine Klassen-Hierarchien
- **HA Voice Backend ist kein Agent** – schlanker Proxy, drei Fake-Modelle, kein Tool-Loop, kein CLAUDE.md
- **HA steuert, HAANA instruiert** – Voice Backend gibt HA Antwort im erwarteten Format, HA führt aus
- **Logs sind Source of Truth** – Qdrant ist der Index, Logs ermöglichen Rekonstruktion
- **Async first** – Extraktion, Embedding, Traumprozess nie blockierend
- **Fehler immer an den User zurückgeben** – kein stilles Scheitern
- **Memory-Scope beim Speichern immer explizit** – Scope immer loggen
- **LLM-Kaskade ist Failover** – nicht für Routing nach Komplexität missbrauchen
- **Kein Vendor-Lock-in** – Provider-Abstraktion von Anfang an, API-Keys nie hardcoden
- **Docker-first** – alles im Container, Ports dokumentiert
- **Git für alles** – CLAUDE.md, Skills, Konfiguration versioniert
