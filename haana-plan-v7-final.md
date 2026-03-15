# HAANA – Implementierungsplan v7
## Home Assistant Advanced Nano Assistant

**Zuletzt aktualisiert: 2026-03-15**

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

### HAANA-Container

Zwei LXC-Container auf Proxmox: ein Entwicklungs-LXC und ein Produktions-LXC. Keine echten IPs werden im Plan dokumentiert.

| Parameter | Wert |
|---|---|
| OS | Debian 13 |
| Docker | 29.2.1 |
| RAM | 8 GB |
| Disk | 16 GB |
| CPU | 3 Cores |

### GPU-Server (läuft, Ollama bereit)

**Hardware:** Lenovo Tiny, Intel i5 8th Gen (T), 32 GB RAM, GTX 1080Ti (11 GB VRAM), Ubuntu 24.04 LTS

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
| HAANA LXC | ✅ Phase 2 abgeschlossen | Vollbetrieb, alle Core-Features aktiv |

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
HAANA-Alice   → Anfragen von Alices Geräten → alice_memory + household_memory
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

**`infer=True` mit ministral-3-32k:3b + Custom Prompt + `"version": "v1.1"` (aktiv seit Phase 1):** ministral-3-32k:3b analysiert die Konversation und extrahiert strukturierte Fakten. Läuft async nach der Antwort an den User, blockiert nichts. Custom Extraction Prompt ersetzt Mem0-Default und berücksichtigt beide Gesprächsseiten (User + Assistant).

> **Wichtig:** mem0 Config MUSS `"version": "v1.1"` enthalten — ohne v1.1 werden zwei LLM-Calls gemacht und MiniMax schlägt still fehl.

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

Context-Persistenz:
    → /data/context/{instance}.json speichert Window-State
    → überlebt Container-Restarts
    → save_context() wird nach JEDER /chat Anfrage aufgerufen
```

### Wann wird wo geschrieben?

```
"Ich mag morgens keinen Kaffee"      → alice_memory
"Bob schläft gerne lange"           → alice_memory (Alices Aussage über Bob)
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

Config-Struktur: getrennte `providers[]` + `llms[]` Listen (nicht mehr `llm_providers[]`).

```
providers[] – Verbindungen zu LLM-Diensten:
  Anthropic Claude (OAuth via Claude Code CLI)
  Ollama GPU-Server (openai-kompatibel)
  MiniMax (anthropic-kompatibel, custom URL + Key)
  OpenAI (API-Key)
  Gemini (API-Key)
  Custom (beliebig)

llms[] – Modell-Definitionen (referenzieren Provider per Name):
  claude-sonnet → Provider "Anthropic Claude"
  claude-haiku → Provider "Anthropic Claude"
  ministral-3-32k:3b → Provider "Ollama GPU-Server"
  MiniMax-M2.5 → Provider "MiniMax"

User-Felder (String-IDs statt Integer-Slots):
  primary_llm: "claude-sonnet"
  fallback_llm: "claude-haiku"
  extraction_llm: "ministral-3-32k:3b"
```

Jeder Provider: Typ / Base URL / API-Key. Jedes LLM: Name / Modell-ID / Provider-Referenz. "Teste Verbindung" Button pro Provider.

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
│   ├── kalender/              ← CalDAV, user-spezifisch (3 Kalender) — Stub implementiert
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
│   └── (integriert in core/ollama_compat.py — drei Fake-Modelle, kein Agent)
├── channels/                  ← Channel/Skill Framework (Phase 2+3 abgeschlossen)
│   ├── base.py                ← BaseChannel Abstrakt-Klasse
│   ├── whatsapp/channel.py    ← vollständige Implementierung + custom_tab_html
│   ├── ha_voice/channel.py    ← vollständige Implementierung (3-Tier-Architektur)
│   └── telegram/channel.py   ← Stub (noch nicht produktiv)
├── common/
│   └── types.py               ← ConfigField (Single-Source-of-Truth)
├── core/
│   ├── agent.py               ← Claude Code SDK Agent Basis
│   ├── memory.py              ← Mem0 + Qdrant Wrapper + Sliding Window
│   ├── api.py                 ← FastAPI pro Agent-Instanz
│   ├── ollama_compat.py       ← WhatsApp/Webchat/HA Routing + LLM-Proxy
│   ├── whatsapp_router.py     ← WhatsApp-Routing + Admin-Modus
│   ├── dream.py               ← Traumprozess: Chunked Processing, Clustering
│   ├── process_manager.py     ← DockerAgentManager + InProcessAgentManager
│   └── logger.py              ← Strukturiertes Logging aller Operationen
├── admin-interface/
│   ├── main.py                ← App-Init, Middleware, Router-Includes (263 Z.)
│   ├── routers/               ← 16 fachliche Router-Module
│   ├── module_registry.py     ← Auto-Discovery für Channel/Skill-Module
│   └── static/js/             ← Vanilla JS Module (app, chat, config, status, ...)
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

Erreichbar im LAN. Kein externer Zugang über Pangolin geplant.

### Auth

- bcrypt-Passwort-Hashing, Session-basiert
- Session-Invalidierung nach Passwort-Änderung
- Companion-Token separat (`companion_token` ≠ `admin_password`)
- SSO via HA Companion Addon (Ingress-Proxy)

### Tabs

- **Status-Tab** (Standard): Channel-Karten (WhatsApp, HA Voice, Telegram, Kalender), Fake-Ollama-Status, Dream-Status aller Instanzen, Instanz-Steuerung (Start/Stop/Restart)
- **Chat-Tab**: kanalübergreifend, SSE Live-Updates, Agent-Online/Offline-Status
- **Config-Tab**: Provider-Liste, LLM-Liste, LLM-Zuordnung per User, Modules (dynamisch aus Channel/Skill Framework)
- **Users-Tab**: User CRUD, CLAUDE.md Inline-Editor, HA Person-Entity Dropdown, WhatsApp LID (readonly, auto)
- **Logs-Tab**: Übersicht, Download, Archivstatus
- **Entwicklung-Tab**: Claude Code Provider-Auswahl, Session-Löschen
- **Setup-Wizard**: wiederholbar (extend/fresh Modus)

### Channel/Skill Framework (Modulares Admin-Interface)

Module registrieren sich selbst im Admin-Interface via `module_registry.py`. Das Interface generiert Tabs und Config-Felder dynamisch:

- `GET /api/modules` – liefert Channel/Skill-Metadaten (id, display_name, enabled, config_fields)
- Channels mit komplexer UI liefern ihr Tab-HTML via `get_custom_tab_html()` selbst
- `config_root` ermöglicht channel-spezifische Config-Pfade ohne Spezialfall-Logik im Router
- Derzeit registriert: WhatsApp, HA Voice, Telegram (Stub), Kalender (Stub)

---

## Sub-Agenten (8 spezialisierte Agenten)

Alle Sub-Agenten sind unter `.claude/agents/` definiert. Der Hauptagent (Orchestrator) arbeitet ausschließlich im Plan-Modus.

| Agent | Zweck | Wann einsetzen |
|---|---|---|
| `dev` | Backend-Entwicklung (Python, Docker, API) | Übergreifende Backend-Änderungen |
| `core-dev` | Spezialist core/ (Agent, Memory, API) | Änderungen ausschließlich in core/ |
| `channel-dev` | Spezialist channels/ + skills/ | Channel- oder Skill-Änderungen |
| `ui-dev` | Spezialist admin-interface/ Frontend | Frontend-Änderungen mit strikter Regeldurchsetzung |
| `webdev` | Frontend-Entwicklung (HTML/CSS/JS, i18n) | Alle UI-Änderungen (generell) |
| `docs` | Dokumentation, Logbuch, UI-Hilfen | Nach Meilensteinen, neue Features |
| `reviewer` | Code-Review, Score, Findings | Nach jeder Implementierung vor Deploy |
| `memory` | Architekturentscheidungen dokumentieren | Wenn Entscheidung getroffen oder nachgeschlagen wird |

---

## Datenhaltung + Zugangsdaten

```
/opt/haana/data/
├── qdrant/          ← alle Memory-Collections (Index, rekonstruierbar aus Logs)
├── config/          ← API-Keys, User-Settings, Credentials (Plaintext, nur LAN)
├── claude-auth/     ← OAuth Credentials pro Provider-ID
├── context/         ← Sliding-Window-State pro Instanz (haana:haana Ownership!)
└── logs/
    ├── conversations/alice/     ← täglich rotiert, nie gelöscht
    ├── conversations/bob/
    ├── llm-calls/
    ├── memory-ops/
    ├── tool-calls/
    └── dream/                   ← Tages-Tagebuch pro Instanz (YYYY-MM-DD.jsonl)

Backup (Standalone-Modus):
    → /data zurückkopieren → docker compose up -d → fertig
    → Optional: SMB/CIFS → TrueNAS (nicht priorisiert)
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
## Standalone (Entwicklung + Produktion)
docker-compose.yml
├── admin-interface        (Web-UI, Port 8080, nur LAN)
├── whatsapp-bridge        (Baileys, Node.js) — Profil: agents
└── qdrant                 (Vector Store, Port 6333)

Hinweis: Agent-Instanzen werden dynamisch via DockerAgentManager gestartet
— nicht als statische docker-compose-Einträge.
update.sh nutzt --profile agents damit whatsapp-bridge mitgestartet wird.

## HA Add-on (Produktion) ❄️ Auf Eis — LXC-Variante ist primär
haana-addons/
├── haana-companion/       (Primär: Minimales Addon ~5MB, SSO-Gateway + Admin-Check)
│                           Token-Auth, Ingress-Proxy zu HAANA-LXC
├── haana/                 (DEPRECATED — vollständiger HAANA-Stack als Addon)
│                           Docker-Images unkomprimiert: 5GB → ~21GB auf Disk
└── haana-whatsapp/        (Optional: WhatsApp Bridge)

AgentManager-Abstraktion (core/process_manager.py):
├── DockerAgentManager     → Standalone: Container via Docker SDK
└── InProcessAgentManager  → Add-on: Agents als Python-Objekte im selben Prozess
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
→ HA URL + Long-Lived Access Token (LLAT, manuell eintragen)
→ Verbindung testen → Entities + Persons abrufen
→ Nabu Casa vorhanden? (STT/TTS)

Schritt 6: Backup
→ SMB/CIFS Ziel, Credentials, Zeitplan, Retention

Schritt 7: Privacy
→ Anonymisierer aktivieren?

→ Fertig: docker-compose.yml generiert, docker compose up -d --build
→ Admin-Interface: http://<haana-ip>:8080
```

**Wiederholbar:** Wizard hat `extend`-Modus (bestehende Config erweitern) und `fresh`-Modus (Neustart).

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
- Context-File (`/data/context/alice.json`): Window-State überlebt Container-Restarts
- Pending-Extraktion beim Startup: unfertige Einträge aus letzter Session werden nachgeholt
- Scope-Erkennung: 1) Regex aus Agent-Antwort → 2) LLM-Klassifikation via Ollama (personal vs. household) → 3) Fallback persönlicher Scope
- Custom Fact Extraction Prompt für Mem0: berücksichtigt User- UND Assistant-Nachrichten (Mem0 Default ignoriert Assistant)
- Memory Rebuild aus Konversations-Logs im Admin-Interface (mit Scope-Klassifikation pro Eintrag)

**Agent HTTP-API (`core/api.py`):**
- FastAPI pro Agent-Instanz
- `POST /chat` → `{"message": "...", "channel": "webchat|whatsapp|..."}` → `{"response": "..."}`
- `WS /ws` → WebSocket bidirektional
- `GET /health` → Instanz-Status
- `save_context()` wird nach JEDER `/chat` Anfrage aufgerufen

**Logging (`core/logger.py`):**
- 4 JSONL-Kategorien mit Daily Rotation, nie gelöscht:
  - `conversations/{instance}/YYYY-MM-DD.jsonl`
  - `memory-ops/YYYY-MM-DD.jsonl`
  - `tool-calls/YYYY-MM-DD.jsonl`
  - `llm-calls/YYYY-MM-DD.jsonl`

**Admin-Interface (`admin-interface/`):**
- FastAPI + Jinja2 + Vanilla JS, Port 8080
- 263-Zeilen main.py (nach Router-Refactoring aus 4585 Zeilen)
- 16 fachliche Router-Module unter `admin-interface/routers/`
- i18n: Key-basiertes Übersetzungssystem (de.json + en.json, 728 Leaf-Keys, Parität Pflicht), `t()` Funktion, `data-i18n` Attribute
- Design: Glassmorphism, Gradient-Buttons, CSS Custom Properties, Dark Theme
- Responsive: Mobile-first CSS, Breakpoints bei 640px und 1024px
- Modal-System: Callback-basiert, ersetzt alle `confirm()`-Dialoge
- Restart-Detection: Erkennt welche Config-Änderungen Container-Neustarts erfordern

**Docker Compose:**
- `qdrant`, `admin-interface` immer aktiv
- `whatsapp-bridge` unter Profil `agents`
- Agent-Instanzen dynamisch via DockerAgentManager
- TZ=Europe/Berlin in allen Containern

**WhatsApp-Bridge (`whatsapp-bridge/`):**
- Baileys + Node.js, Routing via Admin-Interface `/api/whatsapp-config`
- JID-Allowlist: Bridge ignoriert Nachrichten von unbekannten Nummern stillschweigend
- Routing-Tabelle: Bridge pollt `/api/whatsapp-config` alle 5 Min. → kein Neustart bei neuem User
- LID-Cache: `lid_mappings` aus Backend beim `refreshConfig` vorbelegen (überlebt Container-Neustart)
- Auto-LID-Learning: LID wird beim ersten Eingang automatisch via `POST /api/users/whatsapp-lid` persistiert
- QR-Code Linking/Unlinking im Admin-Interface: Status-Anzeige, QR-Code scanbar, Start/Stop-Buttons
- Voice Text-First: Text wird sofort gesendet, TTS-Audio folgt danach

---

### Phase 2 – Erster Alltagskanal ✅ Abgeschlossen (Stand 2026-03-13)

**Ziel:** Alice hört auf SSH. Erster echter Alltagskanal.

**Erledigte Aufgaben (vollständig):**

- WhatsApp-Bridge in Betrieb, Alice chattet per WhatsApp (Text + Sprache, bidirektional)
- STT: WhatsApp Sprachnachrichten (.ogg) → Baileys `downloadMediaMessage` → `POST /api/stt/stt.home_assistant_cloud` an HA → Transkription
- TTS: Antwort → `POST /api/tts_proxy` an HA → OGG Opus Audio → WhatsApp (Voice Text-First: Text sofort, Audio danach)
- Admin-Interface: Auth als Middleware (bcrypt, Session-basiert), kein Token-Auth mehr
- Admin-Interface: main.py God-File (4585 Z.) in 16 fachliche Router-Module aufgeteilt
- Universeller LLM-Proxy (Fake-Ollama-API): `core/ollama_compat.py`, alle Provider, Tool-Calling
- Multi-Provider Memory Extraction + Context Enrichment, Smart Rebuild mit Pre-Filtering + Pause/Resume
- Traumprozess: Memory-Konsolidierung, Tages-Tagebuch (`/data/logs/dream/`), Dream-Status im Status-Tab
- Proaktive Benachrichtigungen via Webhook
- Fallback-LLM Kaskade bei Auth-/Connection-Fehlern
- Explicit Memory Write: `_is_explicit_memory_request()` erkennt Befehle, `add_immediate()` schreibt sofort
- Sprache pro User: `users[].language`, `{{RESPONSE_LANGUAGE}}` in CLAUDE.md Templates
- OAuth setup-token, Credential-Watcher, zentraler Token-Store (`/data/claude-auth/{provider-id}/`)
- Delegation-Feedback (Transition-Satz vor [DELEGATE]), Fortschritts-Feedback ("Moment, ich suche...")
- Nachrichten-Debounce 500ms + AbortController in whatsapp-bridge/index.js
- Admin-Modus via WhatsApp (`/admin` Command, 30-Min-Timeout, `haana-admin` Instanz)
- Minimax MCP: Web-Suche + Bildanalyse als optionale Checkboxen
- Timezone Europe/Berlin in allen Containern, `{{TIMEZONE}}` Platzhalter in System-Prompts
- mem0 v1.1 Fix: `"version": "v1.1"` in Config (ohne: zwei LLM-Calls, MiniMax schlägt still fehl)
- LID-Cache Fix: `lid_mappings` aus Backend beim `refreshConfig` vorbelegen
- Context-Persistenz: `/data/context/` mit `haana:haana` Ownership, `save_context()` nach jeder `/chat` Anfrage
- Auto-Start Standalone-Modus: `_autostart_agents()` für `HAANA_MODE in ("addon", "standalone")`
- update.sh vollständig: HAANA_SELF_UPDATED-Guard, `--profile agents`, `/data/context` anlegen, restart-all
- install.sh vollständig: haana-User-Setup, `.bash_profile`, `.bashrc`, `.claude_provider.env` Template, native Claude Code Installation
- validate.sh Host-Detection: überspringt Container-Tests auf Host-Umgebung (261 Tests grün)
- 8 spezialisierte Sub-Agenten: dev, core-dev, channel-dev, ui-dev, webdev, docs, reviewer, memory
- Lessons Learned / Fallstricke in CLAUDE.md dokumentiert
- Channel/Skill Framework Phase 1–3: `channels/base.py`, `skills/base.py`, `common/types.py`, `module_registry.py`, dynamisches Admin-Interface
- WhatsApp-Tab und HA-Tab dynamisch (custom_tab_html Pattern, config_root)
- Status-Tab Redesign: Channel-Karten, Dream-Status, Fake-Ollama-Status
- Cleanup-Sprint: haana-addons/haana/ (DEPRECATED) entfernt, Terminal-Tab entfernt, Altlasten bereinigt
- Code-Review System: REVIEW-2026-03-14.md vollständiges Projekt-Audit (Score 8/10)
- XSS-Fix: escHtml/escAttr für API-Daten in status.js innerHTML

**MS7 Proxmox Installer + HA Companion Addon:**
- `install.sh`: interaktiver Proxmox LXC Installer (Community-Scripts-Stil)
- `update.sh`: System + Stack Update-Script für den HAANA-LXC
- `haana-addons/haana-companion/`: minimales HA Addon (~5MB) mit Ingress-Proxy, Token-Auth, SSO-Gateway
- Companion App v2.0.0: vereinfacht auf SSO + Admin-Check (tote Endpoints entfernt)

**Bekannte offene Punkte (technische Schuld aus Code-Review):**
- core/memory.py (1548 Z.), config.js (2373 Z.), agent.py (1028 Z.), wizard.js (1028 Z.) — massiv über 400-Zeilen-Limit
- /api/wa-proxy/ weiterhin ohne Auth-Prüfung
- tts_also_text Config-Feld: Zombie-Feld (Feature entfernt, Feld bleibt)
- localhost:11434 Fallback: 7 Stellen hardcodiert statt Konstante
- LOGBOOK.md (EN) parallel zu LOGBUCH.md (DE) — doppelter Wartungsaufwand

---

### Phase 3 – Kalender + Bob einladen 📋 Geplant

**Ziel:** Kalender integriert. Bob bekommt Zugang mit echtem Mehrwert gegenüber ChatGPT.

**Aufgaben:**
- CalDAV-Skill vollständig implementieren (derzeit Stub): Familien-Kalender (geteilt), Alices Kalender, Bobs Kalender
- Termine lesen, eintragen, Kalender-Übersicht
- Daily Brief Skill: morgens automatisch, Termine des Tages + Wetter
- Bob-Instanz freischalten: WhatsApp + HA App
- Multi-Agent Kommunikation: interne `/message` API, beide werden benachrichtigt
- household_memory Feedback-Loop für Kalender
- Zweite User-Instanz einrichten (nach Planungs-Session)

**Ergebnis:** Bob hat vom ersten Tag Kalender + Memory + gemeinsamer Kontext. Kein Voice-Zwang – tippen reicht.

---

### Phase 4 – Home Assistant Integration 📋 Geplant

**Ziel:** HA-Steuerung per Chat, HAANA in Voice Pipeline, proaktive Benachrichtigungen.

**HA Chat-Steuerung (großteils durch MCP abgedeckt ✅):**
- ~~HA-Skill: Entities steuern, Status abfragen, Szenen aktivieren~~ → MCP Tools (89 Tools via ha-mcp Add-on)
- ~~HA-Skill: Automationen per Chat erstellen~~ → MCP Tools + Auto-Backup
- ~~Einkaufsliste-Skill: HA Shopping List~~ → MCP Tools (todo/shopping list)
- Monitoring-Skill: Proxmox, TrueNAS, OPNsense Uptime (nicht HA, separater Skill nötig)
- HA-Entity-Index in Qdrant: Nachtprozess, Bereich→Entity-Zuordnung, Morgenbrief-Integration

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

**Ergebnis:** "Alexa kann weg." Chat-Steuerung, Voice per Hand-Trigger, proaktive Alerts, HA bleibt zuverlässiger Kern.

---

### Phase 5 – Voice Satellites 📋 Geplant

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

### Phase 6 – Wissensbasis 📋 Geplant

**Ziel:** Gemeinsame durchsuchbare Wissensbasis für Rezepte, Dokumente, Haushaltswissen.

**Status:** Trilium läuft, Single-User, API gut. Bleibt Platzhalter bis Multi-User-Lösung sinnvoll. Entscheidung offen – Outline (braucht Auth-Provider), AppFlowy (API noch jung). Wenn Auth-System (Authentik o.ä.) sowieso kommt, wird gleichzeitig Wissensbasis evaluiert.

**Aufgaben wenn bereit:**
- Wissensbasis-Skill: Lesen, Schreiben, Suchen per API
- Embedding-Sync: Dokumente → bge-m3 → Qdrant `wissensbasis_docs`
- Webhook oder periodischer Sync für geänderte Dokumente
- Rezept-Pipeline: WhatsApp-Foto → Vision-Modell → strukturiertes Rezept → Wissensbasis

---

### Phase 7 – Optimierung + Community 📋 Geplant

- OLLAMA_KEEP_ALIVE und OLLAMA_NUM_PARALLEL tunen
- Vision-Modell evaluieren: ministral-3-32k:3b vs ministral-3:8b vs qwen3-vl:8b im echten Betrieb
- Daily Brief persönlicher, kontextsensitiver
- Setup-Wizard polieren, README für Community
- GitHub Repo public
- HA Add-on Paketierung: Grundstruktur fertig (haana-companion, Dual-Mode AgentManager). Noch zu testen in HA.
- Dokumentation: ✅ Initiale Docs erstellt (`docs/LOGBUCH.md`, `docs/API.md`, `docs/CONFIG.md`, `docs/UI-HELP.md`)

---

## Für später – Offene Punkte

### Neue Features (📋 Geplant)

- **SOUL.md pro User-Instanz**: Persönlichkeit vom Agent selbst gepflegt, Interview beim ersten Start
- **HA-Entity-Index in Qdrant**: Nachtprozess, Bereich→Entity-Zuordnung, Morgenbrief-Integration
- **Hybrid Search**: BM25 + Vector in Qdrant
- **Inter-Agenten-Kommunikation**: Agenten können sich gegenseitig beauftragen
- **WhatsApp unverarbeitete Nachrichten Notification**: im Admin-Interface anzeigen
- **Update-Button eigene Logik**: nutzt eigene API statt Aufruf von update.sh
- **WS-Handler save_context**: WebSocket-Handler speichert Kontext bei Disconnect (derzeit nur /chat)
- **Onboarding-Flow**: Git SSH-Key Setup, Fork-Anleitung im Admin-Interface
- **HA-Auth als zweite Login-Option**: alternativ zu Passwort-Auth
- **Telegram-Channel vollständig implementieren**: derzeit Stub
- **Kalender-Skill vollständig implementieren**: derzeit Stub (Tool-Definitionen vorhanden)
- **Zweite User-Instanz einrichten**: nach Planungs-Session
- Bring! Integration: Rezepte → konsolidierte Zutatenliste → Bring! API → Abgleich mit Vorrat
- Kamera-Skill: "Zeig mir die Haustür" per WhatsApp (Vision-Modell bereit, Kamera fehlt noch)
- Paperless-NGX Integration: Dokumente ablegen, Assistent kann darin nachschlagen
- Telegram als Fallback-Kanal bei WhatsApp-Sperre
- Radarr/Sonarr Skills
- Graph-Memory (Neo4j) für komplexere Zusammenhänge zwischen Erinnerungen
- Wyoming Whisper + Piper einrichten als HA-Fallback STT/TTS

### Infrastruktur

- LLM-Fallback für Memory-Operationen: Scope-Klassifikation + Extraktion nutzen konfigurierte Provider-Slots
- Authentik oder Keycloak als einheitliches Auth-System für alle Self-Hosted-Dienste
- Multi-User-Wissensbasis (Outline/AppFlowy) wenn Auth-System steht
- MariaDB direkter HA-Zugriff (fragil wegen undokumentiertem Schema, vorerst Webhook-Weg)
- HA Add-on Store Veröffentlichung (Phase 7)
- Backup auf TrueNAS via SMB/CIFS (optional, nachrangig – HA-Backup-Routine reicht)

### Technische Schuld (aus Code-Review 2026-03-14)

- core/memory.py (1548 Z.) aufteilen: `memory_types.py`, `memory_config.py`, `memory.py`
- config.js (2373 Z.) aufteilen — kritisch
- core/agent.py (1028 Z.) aufteilen — kritisch
- admin-interface/static/js/wizard.js (1028 Z.) aufteilen — kritisch
- /api/wa-proxy/ Auth: BRIDGE_SECRET prüfen analog zu /api/whatsapp-config/
- localhost:11434 Fallback: Konstante in core/constants.py (7 Stellen)
- tts_also_text Zombie-Feld aus whatsapp.py Config-Response entfernen
- LOGBOOK.md (EN) oder LOGBUCH.md (DE): nur eine Datei pflegen

### Evaluation

- bge-m3 + ministral-3-32k:3b als lokaler Stack: Extraktion und Voice bestätigt, Vision noch zu evaluieren
- Vision-Qualität: ministral-3-32k:3b vs ministral-3:8b vs qwen3-vl:8b im echten Betrieb
- Traumprozess-Qualität: ministral-3-32k:3b ausreichend oder größeres Modell nötig?
- HA MCP vs REST API: ✅ Evaluiert – Extended ha-mcp Add-on (89 Tools) als Standard

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
- **Keine Dateien über 400 Zeilen** – max 400 Zeilen pro Datei, bei Überschreitung aufteilen
- **Keine userspezifischen Daten im Code** – User-Instanzen immer aus config.json, nie hardcodiert
- **4-Augen-Prinzip** – Hauptagent plant und delegiert, Sub-Agenten implementieren, reviewer prüft
