# BnD Assistant – Finaler Implementierungsplan v7

## Vision

Ein selbst-gehosteter, persönlicher AI-Assistent für Haushalte. Inspiriert von NanoClaw's Philosophie: minimaler Code, Container-Isolation, jede Zeile hat einen Grund. Von Claude Code entwickelt und gewartet. Community-teilbar, sofort lauffähig ohne GPU, optional erweiterbar.

Langfristiges Ziel: Home Assistant Add-on das jeder mit ein paar Klicks installieren kann.

---

## Kernprinzipien

- **Claude Code SDK** – jede Instanz ist ein Claude Code SDK Agent, wie bei NanoClaw. Kein eigenes Agent-Framework, kein LangChain, kein n8n. Claude Code ist Framework und Ausführungsumgebung in einem.
- **NanoClaw-Philosophie** – minimaler Code, transparent, auditierbar, jede Zeile hat einen Grund
- **Alles in Docker** – portabel, isoliert, HA Add-on-fähig
- **Sofort lauffähig** – nur Anthropic API-Key nötig, alles andere optional
- **Multi-User von Anfang an** – skaliert von 1 bis n Personen
- **Claude Code entwickelt** – Alice beschreibt, Claude Code baut und wartet
- **Community-first** – fork, setup.sh, fertig
- **Privacy by design** – sensible Daten verlassen das Heimnetz nie (optional)
- **HA als zentraler Hub** – STT, TTS, Entity-Steuerung, Subscriptions alles über HA

---

## Wie die Agenten funktionieren (Claude Code SDK)

Jede Instanz (Alice, Bob, HA Assist, HA Advanced) ist ein eigenständiger Claude Code SDK Agent:

```python
# Vereinfachtes Beispiel – so sieht eine Instanz aus
from anthropic import Anthropic
import claude_code_sdk

agent = claude_code_sdk.Agent(
    system_prompt=open("instanzen/admin/CLAUDE.md").read(),
    tools=[ha_tool, memory_tool, trilium_tool, calendar_tool, ...],
    model="claude-sonnet-4-5",  # konfigurierbar
)

# Nachricht eingehend (WhatsApp, Webchat, HA, ...)
response = agent.run(message, context=memory.get_relevant(message))
```

**Was das bedeutet:**
- Kein eigenes Routing-Framework – Claude entscheidet selbst welches Tool wann aufgerufen wird
- Tools sind Python-Funktionen die der Agent aufrufen kann
- CLAUDE.md ist der System-Prompt der Instanz – definiert Persönlichkeit, Berechtigungen, Verhalten
- Skills = Sammlungen von Tools + zugehörigem System-Prompt-Kontext
- Neue Skills: CLAUDE.md erweitern + neue Tool-Funktionen → Git Pull → sofort aktiv

**Warum kein n8n, kein LangChain?**
- n8n hat seinen Platz für Automationen, aber Agent-Logik gehört nicht in Workflow-Tools
- LangChain ist Overhead – Claude Code SDK ist direkter, transparenter, einfacher zu debuggen
- NanoClaw hat bewiesen: SDK direkt reicht, der Rest ist Komplexität um der Komplexität willen

---

## Architektur: Vier Instanz-Typen

### Übersicht

| Instanz | Modell | Kanal | Zugriff | Memory |
|---|---|---|---|---|
| Alice (Admin) | Sonnet/Haiku | WhatsApp + Webchat + HA App | Voll + Skill-Management + Konfigurator | alice_memory + bnd_memory |
| Bob (User) | Sonnet/Haiku | WhatsApp + HA App | Eingeschränkt, kein System-Zugriff | bob_memory + bnd_memory |
| HA Assist | qwen2.5:1.5b lokal | Voice Satellites | HA-Steuerung + Kurzzeit-Kontext, delegiert | bnd_memory lesen + Presence |
| HA Advanced | Haiku / lokal groß | Voice-Overflow | Skills, kein persönliches Memory | bnd_memory lesen |

### Warum vier Instanzen?

**Alice + Bob** kommunizieren per WhatsApp oder HA App. Latenz spielt keine Rolle – bis eine Nachricht getippt ist, sind 1–2 Sekunden LLM-Antwortzeit kein Problem. Das LLM entscheidet vollständig selbst was zu tun ist. Kein separates Routing-Modell nötig.

**HA Assist** ist für Sprache optimiert: blitzschnell, lokal, kein Cloud-Call für einfache Befehle. Ein einziges kleines Modell (qwen2.5:1.5b) macht alles – HA-Befehle direkt ausführen oder selbst erkennen wann etwas zu komplex ist und sofort delegieren.

**HA Advanced** ist der Overflow-Handler für Sprache: übernimmt alles was HA Assist nicht direkt kann (Wetter, Kalender, komplexe Fragen). Kein eigenes persönliches Memory – nur gemeinsamer Haushaltskontext.

### Instanzen im Repo

```
bnd-assistant/
├── instanzen/
│   ├── alice/
│   │   └── CLAUDE.md      ← System-Prompt: Persönlichkeit, Fähigkeiten, Berechtigungen
│   ├── bob/
│   │   └── CLAUDE.md
│   ├── ha-assist/
│   │   └── CLAUDE.md      ← kurze Antworten, delegiert, 3min Kontext
│   └── ha-advanced/
│       └── CLAUDE.md      ← Skills read-only, kein persönliches Memory
├── skills/
│   └── ...
└── core/
    └── agent.py           ← gemeinsame Agent-Basis für alle Instanzen
```

---

## Memory-System (Qdrant + Mem0)

### Memory-Scopes

```
Instanz Alice        Instanz Bob        HA Assist      HA Advanced
     │                    │                  │                │
     ├──► alice_memory     ├──► bob_memory   │                │
     ├──► bnd_memory ◄─────┤                 │                │
     └────────────────────────────── lesen ──┴────────────────┘
```

Vier Qdrant-Collections:
- `alice_memory` – Alices persönliche Erinnerungen, Vorlieben, Kontext
- `bob_memory` – Bobs persönliche Erinnerungen, Vorlieben, Kontext
- `bnd_memory` – gemeinsamer Haushaltskontext, geteilte Vorlieben, Haushaltswissen
- `outline_docs` – Embeddings der Trilium-Dokumente (für semantische Suche)

### Wann wird wo geschrieben?

Das LLM erkennt beim Speichern automatisch den richtigen Scope:

```
"Ich mag morgens keinen Kaffee"      → alice_memory
"Bob schläft gerne lange"           → alice_memory (Alicees Aussage über Bob)
"Wir wollen abends warmweißes Licht" → bnd_memory
"Unser WLAN-Passwort ist..."         → bnd_memory
"Meine Mutter heißt..."              → alice_memory
```

Bei Unklarheit fragt der Agent nach **und gibt Feedback** wenn er gespeichert hat:

```
Alice: "Wir mögen es abends warm und gemütlich"
Agent: "Verstanden – ich merke mir das für euch beide. Soll ich auch die
        Lichtfarbe und Temperatur konkret hinterlegen wenn ihr mir das nächste
        Mal sagt wie es sein soll?"
```

**Korrektur jederzeit möglich:**
```
Alice: "Das mit dem Licht ist nur für mich, Bob mag es eher kühler"
Agent: "Alright, ich verschiebe das in deinen persönlichen Speicher und
        merke mir für Bob: bevorzugt kühleres Licht abends."
```

### Presence-aware Memory (HA Assist)

HA Assist liest `person.alice` und `person.bob` direkt aus HA:

```
Nur Alice @ home    → Alicees Vorlieben aus alice_memory aktiv
Nur Bob @ home     → Bobs Vorlieben aus bob_memory aktiv
Beide @ home        → bnd_memory (gemeinsame Vorlieben bevorzugt)
Niemand @ home      → Standardwerte / Energiesparmodus
```

Die Presence-Entities werden beim Setup automatisch aus HA abgefragt und den Usern zugeordnet (siehe Setup-Wizard Schritt 1).

### HA Assist – Kurzzeit-Kontext (3 Minuten)

HA Assist hält die letzten 3 Minuten Konversation im aktiven Context Window:

```
"Schalte das Licht im Wohnzimmer an"  ✓ ausgeführt
"Mach es grün"                         ✓ weiß noch: Wohnzimmer-Licht gemeint
"Etwas dunkler"                        ✓ weiß noch: Wohnzimmer-Licht, grün
[3 Minuten Pause]
"Etwas heller"                         ? fragt nach oder nimmt letzten bekannten Raum
```

Langfristige Vorlieben kommen aus bnd_memory (Embeddings), nicht aus dem Kurzzeit-Kontext. Das ist die Kombination: schnelle Reaktion auf aktuellen Gesprächsfluss + persistente Präferenzen aus dem Gedächtnis.

---

## Multi-Agent Kommunikation

### Alice ↔ Bob

Instanzen kommunizieren über einen internen API-Endpoint. Jede Instanz hat eine `/message` Route.

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

**Beide werden informiert** – Bob weiß dass es erledigt ist, Alice weiß dass etwas eingetragen wurde. Keine stummen Aktionen im Hintergrund.

### HA Assist → HA Advanced (Delegations-Flow)

```
"Wie wird das Wetter morgen?"
    │
    ▼
HA Assist: kein HA-Tool, kein lokales Wissen → delegieren
    │
    ▼
Sofortige TTS-Antwort: "Moment, ich schaue nach..."   ← keine gefühlte Pause
    │
    ▼
Async: POST /api/instanzen/ha-advanced/message
    │
    ▼
HA Advanced: Wetter-Skill → API-Aufruf → Antwort
    │
    ▼
TTS zurück via HA: "Morgen wird es 12 Grad und bewölkt"
```

Die sofortige Zwischenantwort ist entscheidend für gutes Voice-UX – kein stilles Warten.

---

## LLM-System

### Kein zentrales Router-LLM

WhatsApp-Instanzen (Alice/Bob) brauchen kein separates Routing. Sonnet/Haiku entscheidet vollständig selbst welches Tool wann aufgerufen wird – das ist genau wofür große LLMs gebaut sind. Ein zusätzliches Router-Modell wäre Overhead ohne Mehrwert.

HA Assist hat das "Routing" eingebaut: das lokale Modell erkennt aus dem Kontext ob es direkt handeln kann oder delegieren muss.

### LLM-Auswahl pro Use Case

Im Konfigurator wählbar. Dropdowns werden **dynamisch befüllt** – der Setup-Wizard fragt beim Start die Ollama API nach verfügbaren Modellen ab und kombiniert das mit einer bekannten Liste von Cloud-Modellen. Kein Hardcoding, kein manuelles Pflegen von Listen. Kommt ein neues Modell auf den GPU-Server, erscheint es automatisch.

| Use Case | Standard | Fallback |
|---|---|---|
| HA Assist (Voice, simpel + schnell) | qwen2.5:1.5b lokal | Haiku |
| HA Advanced (Voice-Overflow) | Haiku | lokal groß |
| Chat WhatsApp (Alice/Bob) | Sonnet | Haiku |
| Vision (Rezept-Fotos, Bilder) | Qwen3-VL:8b oder Ministral-3b (wählbar) | Sonnet |
| Embeddings | bge-m3 lokal | OpenAI text-embedding-3-small |
| Cron / Daily Brief | Haiku | qwen2.5:1.5b lokal |

> **Lokal groß** = Qwen3-VL:8b oder Ministral-3b. Beide können Vision + Tool Use. Ministral ohne Thinking (direkter), Qwen3-VL mit opt-in Thinking für komplexere Aufgaben. Welches besser ist entscheidet der echte Betrieb – deshalb beide im Konfigurator wählbar.

> **Chat WhatsApp kein einfach/komplex Split** – das LLM entscheidet selbst ob es ein Tool braucht oder direkt antwortet. Keine künstliche Unterscheidung nötig.

### LLM-Kaskade (= Failover, kein Routing)

Die Kaskade ist reine Ausfallsicherheit – nicht Routing nach Komplexität:

```
Anfrage eingehend
    │
    ├── Anonymisierer aktiv? → sensible Daten ersetzen (nur Cloud-Calls)
    │
    ├── Lokal verfügbar + konfiguriert?  → Ollama (GPU-Server)
    └── Sonst                            → Cloud primär (Anthropic API)
                                              │
                                              └── Fehler / Timeout?
                                                    → Cloud Fallback (MiniMax)
                                                          │
                                                          └── Fehler?
                                                                → Ollama falls verfügbar
                                                                → Fehlermeldung an User
    │
    └── Antwort → Anonymisierer: Platzhalter zurücksetzen
```

### Provider-Konfiguration

Jeder Provider-Slot hat **vier Felder**:

| Feld | Beschreibung |
|---|---|
| Typ | OpenAI-kompatibel oder Anthropic-kompatibel |
| Base URL | z.B. `https://api.anthropic.com` oder custom |
| API-Key | Secret |
| Modell | Freitextfeld oder Dropdown wenn API Modellliste liefert |

Das Modellfeld ist entscheidend wenn ein Provider mehrere Modelle anbietet oder keine Modellliste zurückgibt. Immer manuell überschreibbar.

```
Slot 1 – Primär:
  Typ: anthropic-kompatibel
  URL: https://api.anthropic.com
  Key: sk-ant-...
  Modell: claude-sonnet-4-5  ← Dropdown aus bekannter Liste

Slot 2 – Fallback:
  Typ: anthropic-kompatibel
  URL: https://api.minimaxi.chat/v1
  Key: ...
  Modell: MiniMax-Text-01    ← manuell eingetragen

Slot 3 – Lokal:
  Typ: openai-kompatibel
  URL: http://192.168.1.50:11434/v1  ← GPU-Server
  Key: (leer)
  Modell: (wird von Ollama API dynamisch abgefragt)

Slot 4 – Custom:
  [frei konfigurierbar]
  → Groq, Together AI, LM Studio, vLLM, etc.
```

### Claude Subscription als Option

Beim Setup wählbar mit ehrlichem Hinweis:

```
LLM-Authentifizierung:
○ Anthropic API-Key          (empfohlen – Pay-as-you-go, volle Kontrolle)
○ Claude.ai Subscription     (⚠ nur für private Nutzung, nicht für exzessiven
                               oder dauerhaften Betrieb – bitte API-Key verwenden)
○ MiniMax als Primär         (günstiger, etwas schwächere Qualität)
```

---

## STT / TTS über Home Assistant

Der Agent delegiert STT und TTS vollständig an HA. Was dahinter liegt – Nabu Casa, Wyoming Whisper, Piper, oder zukünftige Backends – ist HAs Sache, nicht die des Agents.

```
WhatsApp Sprachnachricht (.ogg)          Voice Satellite
         │                                      │
         ▼                                      ▼
   POST /api/stt an HA                  HA Assist Pipeline
         │                                      │
         ▼                                      ▼
   HA Pipeline entscheidet              Nabu Casa STT (primär)
   (Nabu Casa oder Wyoming)             Wyoming als HA-Fallback
         │                                      │
         ▼                                      ▼
   Transkription → Agent                Transkription → HA Assist Instanz

TTS: Text → POST /api/tts_proxy an HA → Audio → WhatsApp Sprachnachricht
```

**Warum dieser Ansatz:**
- Nabu Casa ist bereits bezahlt und schnell – keine doppelte Whisper-Instanz nötig
- Wyoming Whisper + Piper laufen als HA-Fallback auf CPU des GPU-Hosts – kein VRAM-Verbrauch für unseren Stack
- Wenn der GPU-Server ausfällt, übernimmt Nabu Casa – HA regelt das, der Agent merkt nichts
- Pipeline-Umschaltung (automatischer Fallback bei Ausfall) ist aktuell noch keine native HA-Funktion – per HA-Automation lösbar, auf offizielle Unterstützung warten

---

## HA Entity Subscriptions

Der Agent kann HA-Entities nicht nur steuern sondern auch abonnieren und auf Änderungen reagieren.

**Wie es funktioniert:**
- `"Abonniere Haustür und benachrichtige mich wenn sie länger als 10 Minuten offen ist"` → Agent legt Subscription an
- Subscriptions werden persistent gespeichert (überleben Container-Neustarts)
- HA feuert einen Webhook wenn sich der Entity-Status ändert
- Agent reagiert: Benachrichtigung per WhatsApp, TTS-Ansage, Automation auslösen, oder weiterleiten

**Konkrete Use Cases:**
- Haustür offen > 10 Minuten → WhatsApp-Nachricht an Alice + Bob
- Wassersensor schlägt an → sofortige Benachrichtigung beide
- `person.alice` kommt nach Hause → personalisierter Empfang via Voice Satellite
- Alarm aktiv → TTS-Ansage auf allen Voice Satellites + WhatsApp gleichzeitig
- Waschmaschine fertig (via Steckdosen-Stromverbrauch) → WhatsApp "Wäsche fertig"

Eigener Skill `ha-subscriptions/` – baut auf derselben HA-Integration auf wie die direkte Steuerung.

---

## Skills: Gemeinsame Basis, individuelle Berechtigungen

```
bnd-assistant/
├── skills/
│   ├── home-assistant/        ← Entity-Steuerung, Status, Szenen
│   ├── ha-subscriptions/      ← Entity-Abonnements und Reaktionen
│   ├── ha-automations/        ← Automationen per Chat erstellen (mit Auto-Backup)
│   ├── kalender/              ← CalDAV, user-spezifisch
│   ├── rezepte/               ← Screenshot → Vision → Trilium
│   ├── trilium/               ← Wissensbasis lesen/schreiben/suchen
│   ├── morning-brief/         ← Daily Brief (Termine, Wetter, Erinnerungen)
│   ├── monitoring/            ← Proxmox, TrueNAS, Netzwerk-Status
│   ├── einkaufsliste/         ← HA Shopping List oder ähnliches
│   └── [weitere per Skill-File hinzufügbar]
├── instanzen/
│   ├── alice/CLAUDE.md        ← Admin: voller Zugriff, Skill-Management, Konfigurator
│   ├── bob/CLAUDE.md         ← User: eingeschränkt, kein System-Zugriff
│   ├── ha-assist/CLAUDE.md    ← Voice: kurze Antworten, delegiert, 3min Kontext
│   └── ha-advanced/CLAUDE.md  ← Voice-Overflow: Skills, kein persönliches Memory
├── core/
│   ├── agent.py               ← Claude Code SDK Agent Basis
│   ├── memory.py              ← Mem0 + Qdrant Wrapper
│   ├── channels.py            ← WhatsApp, Webchat, HA
│   └── cascade.py             ← LLM-Failover Logik
└── docker-compose.yml
```

**Neue Skills aktivieren:**
1. Skill-Ordner im Repo anlegen
2. CLAUDE.md der relevanten Instanzen erweitern (Berechtigungen)
3. Git Pull auf allen Instanzen → sofort aktiv

**Berechtigungen stehen in CLAUDE.md, nicht im Skill-Code.** Das ist die NanoClaw-Philosophie: der Agent weiß was er darf, der Code macht nur was der Agent ihn anweist.

### User-spezifische Dienste

Globale Dienste (HA, Trilium, Ollama) werden einmal konfiguriert und sind für alle Instanzen verfügbar.

Persönliche Dienste werden pro Instanz/User konfiguriert:

| Dienst | Scope | Beispiel |
|---|---|---|
| CalDAV (Kalender) | Pro User | Bobs iCloud, Alices eigener CalDAV |
| IMAP (E-Mail lesen) | Pro User | Alices Mailbox |
| SMTP (E-Mail senden) | Pro User | Alices Absender |
| Persönliche API-Keys | Pro User | Alices spezifische Dienste |
| WhatsApp-Nummer | Pro User | Alicees +49..., Bobs +49... |
| HA Person-Entity | Pro User | `person.alice`, `person.bob` |

---

## Wissensbasis: Trilium Next

Trilium läuft bereits als LXC mit Caddy. Der BnD Assistant integriert sich per Trilium REST API.

**Nutzungskonzept:**
- Trilium = gemeinsame Haushaltswissensbasis (Rezepte, Gerätedokumentation, Anleitungen, gemeinsames Wissen)
- Alices persönliche Notizen (Homelab-Doku, ausgearbeitete Lösungen) ebenfalls in Trilium, in eigenem Notizbuch
- Assistent kann suchen, lesen, neue Notizen anlegen und bestehende aktualisieren

**Semantic Search über Trilium:**
- Trilium-Dokumente werden von bge-m3 embedded und in Qdrant Collection `trilium_docs` gespeichert
- Webhook oder periodischer Sync: neue/geänderte Dokumente werden automatisch neu embedded
- Suche: Query → bge-m3 → Qdrant Vektorsuche → Top-Treffer → Trilium API holt Volltext → Antwort
- Kein "lade alle Notizen in den Kontext" – nur was semantisch relevant ist

**Zukünftige Migration:** Wenn irgendwann ein Multi-User-System gewünscht wird (Bob eigenes Notizbuch, Gastzugang für Freunde), ist ein Umzug auf Outline oder AppFlowy möglich. Trilium bleibt bis dahin – pragmatisch, läuft, API ist gut.

---

## Anonymisierer (optional)

Im Setup und Konfigurator aktivierbar. Gilt **nur** für Cloud-LLMs (Anthropic, MiniMax, etc.), **nie** für lokales Ollama.

**Was ersetzt wird:**
- Personennamen: Bob → `[USER_2]`, Dr. Müller → `[PERSON_1]`
- Adressen und Ortsnamen: Musterstraße 12 → `[ADDR_1]`
- Telefonnummern: +49 123... → `[PHONE_1]`
- E-Mail-Adressen
- IP-Adressen, interne Hostnamen

**Flow:**
```
Original:  "Bob hat Termin bei Dr. Müller in der Musterstraße"
An Cloud:  "[USER_2] hat Termin bei [PERSON_1] in [ADDR_1]"
Antwort:   "Termin für [USER_2] bei [PERSON_1] eingetragen"
Zurück:    "Termin für Bob bei Dr. Müller eingetragen"
```

API-Keys und Passwörter gehen grundsätzlich nie ans LLM – das ist eine separate, immer aktive Sicherheitsschicht, unabhängig vom Anonymisierer.

---

## Admin-Webinterface

Nur für Admin-Instanzen (Alice) zugänglich. Erreichbar unter `http://[HOST]:8080`.

### Chat-Tab

Hier wird der echte Chatverlauf der jeweiligen Instanz angezeigt – **nicht eine separate Debug-Ansicht**, sondern derselbe Verlauf der auch per WhatsApp und HA App geführt wird. Eine Session, mehrere Eingabekanäle.

**User-Dropdown:** Als welche Instanz soll ich chatten/debuggen?
- Alice (Admin) – normaler Betrieb
- Bob – simuliere Bobs Sicht für Tests
- HA Assist – Voice-Verhalten testen
- HA Advanced – Overflow-Verhalten testen

**Kanalindikator:** Jede Nachricht zeigt woher sie kam:
- 📱 WhatsApp
- 🖥️ Webchat
- 🏠 HA App / Voice

**Jede Nachricht aufklappbar:**
```
► [10:34] "Mach das Licht im Wohnzimmer warm"    📱 WhatsApp
   ▼ aufklappen:
   [Memory geladen]     3 Treffer: "Wohnzimmer-Vorlieben", "Abend-Modus", ...
   [Tool aufgerufen]    ha_control(entity="light.wohnzimmer", color_temp=2700K)
   [HA Antwort]         OK, Zustand: an, 2700K, 80%
   [Memory gespeichert] bnd_memory: "Abends warmweißes Licht Wohnzimmer" (Scope: BnD)
   [Antwort]            "Wohnzimmer auf warmweiß gedimmt."
```

**Warum kanalübergreifend?**
Alice chattet tagsüber per WhatsApp. Abends öffnet er das Webinterface und sieht genau was passiert ist. Scrollt zum Zeitpunkt wo etwas komisch war, klappt auf und sieht alle internen Schritte. Dann antwortet er direkt im Webchat – selbe Session, selber Kontext.

Das gilt auch für die HA App als dritten Kanal: öffnet die HA App, schreibt eine Nachricht, der Kontext aus WhatsApp ist noch da.

### Config-Tab

**Nutzer:**
- Hinzufügen, bearbeiten, Memory zurücksetzen, löschen
- Pro User: Name, WhatsApp-Nummer, Typ (Admin/User), HA Person-Entity (Dropdown)
- Persönliche Dienste pro User: CalDAV URL+Credentials, IMAP, SMTP

**CLAUDE.md:**
- Direkt im Browser editieren pro Instanz
- Syntax-Highlighting, Vorschau
- Änderung → sofort aktiv (kein Container-Neustart nötig)

**Skills:**
- Aktivieren / Deaktivieren pro Instanz
- Status: aktiv, inaktiv, Fehler beim letzten Aufruf

**LLM-Konfiguration:**
- Pro Use Case: Dropdown Primärmodell + Dropdown Fallback
- Provider-Slots: Typ, Base URL, API-Key, Modell (Freitextfeld, überschreibbar)
- "Teste Verbindung" Button pro Slot

**Dienste global:**
- Home Assistant: URL + Long-Lived Token
- Ollama: URL (extern oder lokaler Container)
- Trilium: URL + API-Token

**Dienste pro User:**
- CalDAV, IMAP, SMTP pro Nutzer

**Backup:**
- SMB/CIFS Ziel, Credentials, Zeitplan (täglich/wöchentlich)
- Manuell auslösen
- Letztes Backup: Zeitstempel + Größe

**Anonymisierer:**
- Aktivieren/Deaktivieren
- Bekannte Namen verwalten (manuell ergänzen/entfernen)
- Automatisch erkannte Namen anzeigen

**HA Subscriptions:**
- Aktive Abonnements anzeigen mit Entity, Bedingung, Aktion
- Einzelne Subscriptions pausieren oder löschen

---

## Setup-Wizard

Einmalig beim ersten Start, danach über Config-Tab änderbar.

```
Schritt 1: Nutzer anlegen
→ Anzahl Nutzer (1–5)
→ Pro Nutzer:
    - Name
    - Typ: Admin / User
    - WhatsApp-Nummer (optional, kann später ergänzt werden)
    - HA Person-Entity: Dropdown aus HA Persons API
      (wird live von HA abgefragt: person.alice, person.bob, ...)
    - CalDAV URL + Credentials (optional)
    - IMAP (optional)

Schritt 2: Dienste (global)
→ Ollama:
    ○ Bestehender Server im Netzwerk → URL eingeben (kein Container)
    ○ Lokaler CPU-Container → wird gestartet (langsamer, sofort nutzbar)
    ○ Lokaler GPU-Container → nvidia-runtime erforderlich
    ○ Kein Ollama → OpenAI Embeddings als Fallback
→ Trilium:
    ○ Bestehende Instanz → URL + API-Token
    ○ Neuer Docker-Container → wird gestartet
    ○ Überspringen → Wissensbasis-Skills deaktiviert

Schritt 3: LLM-Provider
→ Primär:
    ○ Anthropic API-Key (empfohlen)
    ○ Claude.ai Subscription (mit Hinweis: nur privat, nicht exzessiv)
→ Fallback (optional):
    ○ MiniMax – Base URL + API-Key + Modell
    ○ Custom – Typ + URL + Key + Modell
→ Lokale Modelle:
    → wird von Ollama API abgefragt und angezeigt

Schritt 4: LLM pro Use Case
→ Dropdowns mit verfügbaren Modellen (aus Schritt 3 + Ollama-Abfrage)
→ Pro Use Case: Primär + Fallback

Schritt 5: Home Assistant
→ HA URL + Long-Lived Access Token
→ Verbindung testen → Entities + Persons werden abgerufen
→ Nabu Casa vorhanden? (für STT/TTS – empfohlen)

Schritt 6: Backup
→ SMB/CIFS Ziel: \\server\share
→ Credentials: User + Passwort
→ Zeitplan: täglich um [HH:MM]
→ Retention: [7] Tage

Schritt 7: Privacy
→ Anonymisierer aktivieren? (nur relevant wenn Cloud-LLMs genutzt werden)

→ Fertig:
    docker-compose.yml generiert
    CLAUDE.md pro Instanz erstellt
    docker compose up -d
    → Admin-Interface: http://[HOST]:8080
```

**Als HA Add-on (zukünftig):**
Schritt 5 entfällt – das Add-on hat automatisch Zugriff auf die interne HA API, URL und Token werden nicht benötigt.

---

## Kanäle

| Kanal | Phase | Instanz | Bemerkung |
|---|---|---|---|
| Webchat (Admin-Interface) | Phase 1 | Alice (Admin) | Gemeinsamer Verlauf mit WhatsApp |
| WhatsApp (Baileys) | Phase 2 | Alice + Bob | Sprachnachrichten via HA STT/TTS |
| HA App (Conversation) | Phase 2 | Alice + Bob | Gleiche Session wie WhatsApp |
| HA Assist (Voice Satellites) | Phase 5 | HA Assist + HA Advanced | Presence-aware |
| Telegram | Später | Optional | Als Fallback bei WhatsApp-Sperre |

---

## Docker-Stack

```
docker-compose.yml
├── instanz-alice          (Python, Claude Code SDK Agent, Admin)
├── instanz-bob           (Python, Claude Code SDK Agent, User)
├── instanz-ha-assist      (Python, Claude Code SDK Agent, qwen2.5:1.5b)
├── instanz-ha-advanced    (Python, Claude Code SDK Agent, Haiku/lokal groß)
├── admin-interface        (Web-UI, nur intern, Port 8080)
├── whatsapp-bridge        (Baileys, Node.js)
├── qdrant                 (Vector Store, Port 6333)
├── mem0                   (Memory Layer)
├── trilium                (optional – wenn kein externer Server)
└── ollama                 (optional – CPU oder GPU)

Persistent Storage: /opt/bnd-assistant/data/
├── qdrant/          ← alle Memory-Collections + Trilium-Embeddings
├── trilium/         ← nur wenn Docker-Container, sonst extern
├── config/          ← API-Keys, User-Settings, docker-compose.yml
└── claude-md/       ← CLAUDE.md aller Instanzen (versioniert via Git)

Backup: täglich → SMB/CIFS → TrueNAS, komprimiert, 7 Tage Retention
Restore: /data zurückkopieren → docker compose up -d → fertig
```

---

## Phasenplan

### Voraussetzungen (Stand heute)
- [x] Trilium Next läuft (LXC + Caddy)
- [x] Nabu Casa Subscription aktiv (STT/TTS primär)
- [x] GPU-Server läuft (Ollama + alle Modelle geladen)
- [x] Proxmox Cluster läuft (2 Nodes)
- [ ] Docker-LXC auf Proxmox erstellen
- [ ] GitHub-Repo anlegen (privat)
- [ ] Anthropic API-Key besorgen
- [ ] Claude Code auf Docker-LXC installieren

---

### Phase 1 – Fundament (Woche 1–2)

**Ziel:** Alice chattet im Webchat, der Agent merkt sich Dinge korrekt, alles ist transparent nachvollziehbar.

**Aufgaben:**
- Docker-LXC aufsetzen, Docker + Docker Compose installieren
- GitHub-Repo anlegen, Claude Code konfigurieren
- Grundstruktur: `core/agent.py`, `instanzen/alice/CLAUDE.md`
- Setup-Wizard Grundgerüst (Schritt 1–3, Grundkonfiguration)
- Alice-Instanz: Claude Code SDK Agent, Admin-Interface + Webchat
- Basis-Agent-Loop: Nachricht eingehend → LLM → Tool-Aufruf oder Antwort
- Mem0 + Qdrant: Memory schreiben und lesen funktioniert
- Memory-Scope-Erkennung: "Ich" vs "Wir" → korrekter Scope
- Feedback beim Speichern: Agent bestätigt was er wo gespeichert hat
- LLM-Failover: Anthropic primär → Fallback → Ollama
- Provider-Konfiguration: vier Felder pro Slot, Modell manuell eingebbar
- Webchat: kanalübergreifender Verlauf, aufklappbare Details je Nachricht
- Git-Repo: Struktur, README, CLAUDE.md für Instanzen versioniert

**Ergebnis:** Alice chattet im Webchat. Der Agent merkt sich Dinge im richtigen Scope. Alle internen Schritte sind im Webchat aufklappbar sichtbar.

---

### Phase 2 – Multi-User + WhatsApp (Woche 3–4)

**Ziel:** Beide nutzen WhatsApp mit Sprach-Support. Scopes funktionieren. Täglicher Brief läuft automatisch.

**Aufgaben:**
- Bob-Instanz aufsetzen (CLAUDE.md, User-Berechtigungen)
- Setup-Wizard Schritt 1 erweitern: HA Person-Entity Dropdown per API-Abfrage
- User-spezifische Dienste: CalDAV, IMAP pro Instanz konfigurierbar
- WhatsApp-Bridge (Baileys): QR-Code Scan, Nachrichten routing zu den Instanzen
- STT: WhatsApp Sprachnachricht (.ogg) → `POST /api/stt` an HA → Transkription
- TTS: Agent-Antwort → `POST /api/tts_proxy` an HA → Audio → WhatsApp Sprachnachricht (optional, konfigurierbar)
- Multi-Agent Kommunikation: interne `/message` API zwischen Instanzen
- Beide werden benachrichtigt wenn eine Instanz im Namen der anderen handelt
- bnd_memory Feedback-Loop: Bestätigung + Korrekturmöglichkeit
- Daily Brief Skill (morning-brief/): Wetter + Erinnerungen, morgens automatisch
- Backup auf TrueNAS: SMB/CIFS, täglich, komprimiert
- HA App als Kanal: Conversation-Integration, gleiche Session wie WhatsApp

**Ergebnis:** Alice und Bob nutzen WhatsApp und HA App. Sprachnachrichten werden transkribiert. Memory-Scopes korrekt. Täglicher Brief läuft.

---

### Phase 3 – Wissensbasis + Rezepte + Kalender (Woche 5–6)

**Ziel:** Rezepte per Foto, Kalender integriert, Trilium als durchsuchbare Wissensbasis.

**Aufgaben:**
- Trilium-Skill: Lesen, Schreiben, Suchen per Trilium REST API
- Trilium-Embedding-Sync: Dokumente → bge-m3 → Qdrant `trilium_docs`
- Webhook oder periodischer Sync für geänderte Dokumente
- Rezept-Pipeline: WhatsApp-Foto → Vision-Modell → strukturiertes Rezept → Trilium-Eintrag
- CalDAV pro User: Termine lesen, Termine eintragen, Kalender-Übersicht
- Daily Brief erweitern: Termine des Tages aus CalDAV
- Anonymisierer implementieren (optional, konfigurierbar)
- Setup-Wizard Schritt 7 ausbauen

**Ergebnis:** Rezept fotografieren → automatisch in Trilium gespeichert. Kalender integriert. Assistent kann in der Wissensbasis suchen.

---

### Phase 4 – Home Assistant (Woche 7–8)

**Ziel:** Alexa kann weg. HA-Steuerung, proaktive Benachrichtigungen, Monitoring.

**Aufgaben:**
- HA-Skill: Entities steuern, Status abfragen, Szenen aktivieren
- HA-Skill: Automationen per Chat erstellen (mit automatischem HA-Backup vorher)
- HA Subscriptions Skill: Entities abonnieren, Webhooks empfangen, reagieren
- Presence Detection: `person.alice` + `person.bob` für Memory-Scope-Umschaltung
- Presence-basierte Begrüßung (Voice Announcement oder WhatsApp)
- Proaktive Benachrichtigungen: Haustür, Wassersensor, Waschmaschine
- Monitoring-Skill: Proxmox Node-Status, TrueNAS Pools/Disks, OPNsense Uptime
- Admin-Interface: HA Subscriptions Tab (anzeigen, pausieren, löschen)

**Ergebnis:** Sprachsteuerung, proaktive Alerts, Automationen per Chat, Homelab-Monitoring.

---

### Phase 5 – HA Assist + HA Advanced (Woche 9–10)

**Ziel:** Sprachsteuerung über alle Voice Satellites, presence-aware, schnell.

**Aufgaben:**
- HA Assist Instanz: qwen2.5:1.5b, CLAUDE.md auf kurze Antworten optimiert
- HA Assist CLAUDE.md: 3-Minuten-Kontext-Handling, Delegations-Trigger
- HA Advanced Instanz: Haiku/lokal groß, alle Skills verfügbar
- Delegations-Flow: sofortige TTS-Zwischenantwort + async Übergabe an HA Advanced
- HA registriert HA Assist als externen Conversation Agent (ersetzt eingebauten Assist)
- Pro Voice Satellite eigene HA Pipeline konfigurieren
- Presence-aware Vorlieben: bnd_memory Vectors für HA Assist
- Tests: Latenz, Delegationsqualität, Presence-Switching

**Ergebnis:** "Hey Assist, mach das Licht warm" → direkt. "Hey Assist, wie wird das Wetter?" → "Moment..." → Antwort. Presence-aware.

---

### Phase 6 – Feinschliff + Optimierung (laufend)

**Aufgaben:**
- `OLLAMA_KEEP_ALIVE=-1` für qwen2.5:1.5b → immer im VRAM
- `OLLAMA_NUM_PARALLEL` tunen (mehrere gleichzeitige Sessions)
- Vision-Modell-Evaluation in echtem Betrieb: Qwen3-VL:8b vs. Ministral-3b
- bge-m3 Embedding-Qualität beurteilen (Suchqualität im Alltag)
- Daily Brief ausbauen: persönlicher, mit mehr Kontext
- Setup-Wizard polieren

---

### Phase 7 – Community + HA Add-on (später)

**Aufgaben:**
- Vollständiges README für Community-User
- Setup-Wizard: alles sauber, mit Erklärungen, für Nicht-Techniker verständlich
- GitHub Repo public schalten
- HA Add-on Paketierung: HAOS-kompatibel, Add-on Store ready
- Als HA Add-on: HA URL/Token automatisch, Setup-Wizard Schritt 5 entfällt

---

## GPU-Server (bereit)

| Modell | VRAM | Aufgabe | Ladestrategie |
|---|---|---|---|
| bge-m3 | ~1.2 GB | Embeddings (Deutsch+Englisch) | KEEP_ALIVE=-1 (dauerhaft) |
| qwen2.5:1.5b | ~1.0 GB | HA Assist | KEEP_ALIVE=-1 (dauerhaft) |
| Qwen3-VL:8b | ~6.1 GB | Vision + Fallback Chat | on-demand |
| Ministral-3b | ~6.0 GB | Alternative Vision/Chat | on-demand |

> Qwen3-VL und Ministral können nicht gleichzeitig geladen sein (~12 GB zusammen > 11 GB VRAM). Ollama lädt immer nur das gerade benötigte. Welches besser ist zeigt der echte Betrieb – beide im Konfigurator wählbar.

> Whisper + Piper laufen auf CPU als HA-Fallback – kein VRAM-Verbrauch für BnD Assistant.

**Freier Headroom (~2.7 GB):** Reicht für erhöhtes `OLLAMA_NUM_PARALLEL` damit HA Assist + Embeddings + ein großes Modell gleichzeitig laufen können.

---

## Bestehende Infrastruktur

| Service | Status | Details |
|---|---|---|
| Proxmox Cluster | ✅ Läuft | 2 Nodes |
| OPNsense | ✅ Läuft | Firewall / Router |
| TrueNAS | ✅ Läuft | Storage + Backup-Ziel (SMB/CIFS) |
| Home Assistant | ✅ Läuft | Smart Home Hub |
| Nabu Casa | ✅ Läuft | STT/TTS primär (bereits bezahlt) |
| Wyoming Whisper | ✅ Läuft | HA Fallback STT (CPU auf GPU-Host) |
| Piper | ✅ Läuft | HA Fallback TTS (CPU auf GPU-Host) |
| Trilium Next | ✅ Läuft | LXC + Caddy, bereits produktiv |
| GPU-Server | ✅ Läuft | Bare Metal, 1080ti, Ollama + Modelle bereit |
| Docker-LXC | ⏳ Ausstehend | Nächster Schritt |

---

## Technische Referenzen

| Projekt/Tool | Zweck | URL |
|---|---|---|
| NanoClaw | Philosophie + Ausgangspunkt | github.com/qwibitai/nanoclaw |
| Anthropic SDK / Claude Code | Agent-Basis, SDK | github.com/anthropics/anthropic-sdk-python |
| Baileys | WhatsApp Bridge (Node.js) | github.com/WhiskeySockets/Baileys |
| Mem0 | Memory Layer | github.com/mem0ai/mem0 |
| Qdrant | Vector Store | qdrant.tech |
| Trilium Next | Wissensbasis | github.com/TriliumNext/Notes |
| Anthropic API | Primäres LLM | api.anthropic.com |
| MiniMax | Cloud Fallback LLM | api.minimaxi.chat |
| Ollama | Lokale Modelle | ollama.ai |
| HA REST API | STT, TTS, Steuerung, Presence, Webhooks | developers.home-assistant.io |
| Nabu Casa | STT/TTS primär (bereits vorhanden) | nabucasa.com |

---

## Für später – Offene Punkte

Diese Punkte sind notiert aber aktuell nicht dringend. Wenn das System läuft, kommen sie der Reihe nach.

**Features:**
- Bring! Integration als Skill: Rezepte → konsolidierte Zutatenliste → Bring! API → interaktiver Abgleich mit Vorrat
- Kamera-Skill: "Zeig mir die Haustür" per WhatsApp (Vision-Modell ist bereit, nur Kamera fehlt noch)
- Paperless-NGX Integration: Dokumente ablegen, suchen, Assistent kann darin nachschlagen
- Telegram als Fallback-Kanal wenn WhatsApp gesperrt wird
- Radarr/Sonarr Skills
- Graph-Memory (Neo4j) für komplexere Zusammenhänge zwischen Erinnerungen
- Morning Brief intelligenter: persönlicher, kontextsensitiver, ausbaufähig

**Infrastruktur:**
- Einheitliches Auth-System (Authentik oder Keycloak) für alle Self-Hosted-Dienste
- Outline oder AppFlowy als Multi-User-Wissensbasis wenn Auth-System steht
- HA Add-on Store Veröffentlichung (Phase 7)

**Evaluation:**
- Vision-Modell im echten Betrieb testen: Qwen3-VL:8b vs. Ministral-3b
- Embedding-Qualität bge-m3 in der Praxis beurteilen
- Daily Brief Qualität nach mehreren Wochen Betrieb verbessern

---

## Hinweise für Claude Code

Diese Hinweise sind für Claude Code beim Implementieren:

- **Kein eigenes Agent-Framework bauen** – direkt Claude Code SDK verwenden wie NanoClaw
- **CLAUDE.md ist der System-Prompt** – Berechtigungen und Persönlichkeit gehören dorthin, nicht in Code
- **Tools sind einfache Python-Funktionen** – keine Klassen-Hierarchien, keine abstrakten Interfaces
- **Fehler immer an den User zurückgeben** – kein stilles Scheitern, immer erklären was nicht funktioniert hat
- **Memory-Scope beim Speichern immer explizit** – nie implizit entscheiden, Scope immer loggen
- **LLM-Kaskade ist Failover** – nicht für Routing nach Komplexität missbrauchen
- **Kein Vendor-Lock-in** – Provider-abstraktion von Anfang an, API-Keys nie hardcoden
- **Jede Instanz ist unabhängig** – gemeinsame Basis in `core/`, instanz-spezifisches in `instanzen/`
- **Docker-first** – alles was nach außen geht läuft im Container, Ports dokumentiert
- **Git für alles** – CLAUDE.md Änderungen, Skill-Updates, Konfiguration – alles versioniert
