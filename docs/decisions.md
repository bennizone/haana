# HAANA — Architektur-Entscheidungen (ADR)

Dieses Dokument hält rückwirkend die wichtigsten Architektur- und Designentscheidungen fest,
die das Projekt langfristig geprägt haben. Neueste Einträge zuerst.
Triviale Bugfixes und reine UI-Korrekturen sind nicht enthalten.

---

## 2026-03-13 | main.py God-File in FastAPI-Router aufgeteilt

**Kontext:** `admin-interface/main.py` war auf ~4585 Zeilen angewachsen. Bei Sub-Agenten-Aufrufen
führte das regelmäßig zu Kontext-Overflows, weil das gesamte Modul in den Prompt geladen werden
musste. Jede Änderung trug das Risiko ungewollter Seiteneffekte.

**Entscheidung:** Aufteilung in 16 fachliche Router-Module unter `admin-interface/routers/`
plus ein zentrales `deps.py` als Shared-State-Modul. `main.py` reduziert auf 263 Zeilen
(App-Init, Middleware, Router-Includes). Alle 102 Endpunkte erhalten, kein Verhalten geändert.

**Alternativen:** Monolithische Datei behalten und Kontext-Overflow per Prompt-Engineering
umschiffen. Abgelehnt, weil das Problem mit wachsendem Code eskaliert und die eigentliche
Ursache nicht beseitigt.

**Auswirkung:** `admin-interface/routers/` (16 Module), `admin-interface/main.py`,
`tests/test_config.py`. Sub-Agenten können einzelne Router lesen ohne den gesamten
Backend-Kontext laden zu müssen.

---

## 2026-03-13 | Terminal-Tab entfernt, Altlasten bereinigt

**Kontext:** Nach Einführung des Sub-Agenten-Workflows (dev, webdev, reviewer, docs) hatte
der Terminal-Tab im Admin-Interface kein aktives Use-Case mehr. `haana-addons/haana/` war seit
MS7 nicht mehr gepflegt und hätte bei jedem Merge Konflikte erzeugt.

**Entscheidung:** Terminal-Tab vollständig entfernt (JS, CSS, HTML, i18n-Keys, Backend-Routen).
`haana-addons/haana/` und `haana-addons/haana-whatsapp/whatsapp-bridge/` gelöscht.
Auskommentierte docker-compose-Einträge (ollama, trilium) entfernt.

**Alternativen:** Terminal-Tab deaktiviert lassen mit "Coming Soon"-Badge. Abgelehnt, weil
toter Code Wartungsaufwand erzeugt und Leser über den tatsächlichen Stack-Umfang täuscht.

**Auswirkung:** `docker-compose.yml`, `admin-interface/templates/index.html`,
`admin-interface/static/js/`, i18n-Dateien (von 721 auf 693 Keys).

---

## 2026-03-12 | WhatsApp LID automatisch persistiert (Auto-LID-Learning)

**Kontext:** WhatsApp nutzt intern LIDs (Linked Device IDs) zur Adressierung. Ohne korrekte LID
können Nachrichten nicht zugestellt werden. Manuelle Eingabe im Admin-Interface ist fehleranfällig
und erfordert technisches Wissen vom User.

**Entscheidung:** Die Bridge ermittelt die LID beim ersten eingehenden Nachrichten-Resolve
automatisch und persistiert sie via `POST /api/users/whatsapp-lid` in `config.json`.
Das UI-Feld ist readonly mit dem Hinweis "Wird automatisch ermittelt".

**Alternativen:** Manuelle LID-Eingabe im User-Formular beibehalten. Abgelehnt, weil die LID
für normale Nutzer nicht transparent ist und Fehleingaben zu stillen Zustellungsfehlern führen.

**Auswirkung:** `whatsapp-bridge/index.js`, `admin-interface/main.py` (neuer Endpunkt),
`admin-interface/static/js/users.js`, i18n-Dateien.

---

## 2026-03-12 | Fake-Ollama-API als universeller LLM-Proxy

**Kontext:** Home Assistant Voice Pipeline benötigt einen Ollama-kompatiblen Endpunkt um
HAANA-Agenten als LLM-Backend einzubinden. Gleichzeitig sollte ein einheitlicher Proxy
für alle externen LLM-Consumer (HA, Claude Code CLI) existieren.

**Entscheidung:** HAANA stellt eine Fake-Ollama-API bereit (`ollama_compat.py`). HA sieht
HAANA wie einen normalen Ollama-Server und wählt pro Gerät das passende "Modell"
(HAANA-Alice, HAANA-Bob, HAANA-HA). Der Proxy übernimmt Agent-Routing und Tool-Calling intern.

**Alternativen:** Nativer HA-Conversation-Agent-Endpunkt ohne Ollama-Kompatibilität.
Abgelehnt, weil der Ollama-Standard von HA bereits vollständig unterstützt wird und
kein eigenes HA-Integration-Plugin nötig ist.

**Auswirkung:** `core/ollama_compat.py`, `admin-interface/main.py` (Ollama-Compat-Endpunkte),
`docker-compose.yml` (Port-Exposition). Auth-Middleware musste Ollama-Compat-Pfade
explizit ausnehmen (HA authentifiziert sich nicht per Session-Cookie).

---

## 2026-03-09 | 4-Augen-Prinzip: Plan-Modus + Sub-Agenten-Workflow

**Kontext:** Direkte Hotfixes durch den Hauptagenten hatten das Reviewer-Prinzip unterlaufen.
Ein Ein-Zeiler-Fix ohne Review untergräbt das Vertrauen, dass jede Änderung geprüft wurde.

**Entscheidung:** Hauptagent (Orchestrator) arbeitet ausschließlich im Plan-Modus: lesen,
planen, delegieren. Alle Code-Änderungen gehen ausnahmslos über Sub-Agenten (dev, webdev).
Jede Implementierung wird vom reviewer-Agenten geprüft (Score ≥ 7/10 erforderlich).
Festgehalten in `/opt/haana/CLAUDE.md` als verbindliche Regel.

**Alternativen:** Ausnahmen für "offensichtliche" Ein-Zeiler-Fixes erlauben. Explizit abgelehnt:
Jede Ausnahme erzeugt Präzedenz für die nächste Ausnahme und macht die Regel wertlos.

**Auswirkung:** `/opt/haana/CLAUDE.md`, `.claude/agents/` (reviewer, dev, webdev, docs).
Alle nachfolgenden Änderungen folgen diesem Workflow.

---

## 2026-03-09 | Admin-Auth als Middleware (nicht als Decorator)

**Kontext:** Das Admin-Interface war initial ohne Authentifizierung. Mit dem Produktionseinsatz
mussten alle Endpunkte abgesichert werden, ohne jeden einzelnen Route-Handler zu annotieren.

**Entscheidung:** Session-basierte Auth via `BaseHTTPMiddleware` in Starlette/FastAPI.
`admin-interface/auth.py` übernimmt bcrypt-Passwort-Hashing. Die Middleware prüft zentral
alle eingehenden Requests — Ausnahmen (Login-Route, Static Assets) werden explizit gelistet.

**Alternativen:** FastAPI `Depends()`-Decorator auf jeder Route. Abgelehnt, weil bei ~100
Endpunkten jede neue Route vergessen werden könnte — Middleware schützt per Default.

**Auswirkung:** `admin-interface/auth.py` (neu), `admin-interface/main.py` (Middleware-Mount).
Ollama-Compat-Endpunkte mussten explizit ausgenommen werden (externe HA-Clients haben keine Session).

---

## 2026-03-07 | Companion-Addon statt vollständigem HAANA als HA-Addon (MS7)

**Kontext:** Das ursprüngliche Ziel war HAANA als vollständiges HA-Addon. Docker-Images
unkomprimiert auf HAOS: 5 GB komprimiert = ~21 GB auf Disk. Ein vollständiger HAANA-Stack
als Addon ist für typische HA-Hardware nicht tragbar.

**Entscheidung:** Minimales `haana-companion`-Addon (~5 MB, Alpine+Python+aiohttp) das
ausschließlich als Ingress-Proxy und Handshake-Bridge zu einem externen HAANA-LXC dient.
Token-Auth via `secrets.compare_digest`. Das altes `haana-addons/haana/` als DEPRECATED markiert.

**Alternativen:** Schlankes HAANA-Lite als Addon mit reduziertem Feature-Set. Abgelehnt,
weil die Maintenance-Last (zwei Code-Pfade: LXC + Addon) den Nutzen übersteigt und ein
externer LXC ohnehin mehr Ressourcen und Flexibilität bietet.

**Auswirkung:** `haana-addons/haana-companion/` (neu), `install.sh`, `update.sh`,
`admin-interface/main.py` (Companion-Endpunkte), `haana-addons/repository.yaml`.

---

## 2026-03-06 | Logs als Source of Truth — Qdrant ist nur der Index

**Kontext:** Bei einem Wechsel des Embedding-Modells oder einer Qdrant-Korruption gehen
alle Memory-Daten verloren, wenn Qdrant die einzige Persistenz-Schicht ist.

**Entscheidung:** Alle Konversationen, LLM-Calls, Memory-Operationen und Tool-Calls werden
als JSONL-Logs in `/data/logs/` geschrieben. Qdrant wird daraus aufgebaut und kann jederzeit
vollständig aus den Logs rekonstruiert werden ("Smart Rebuild"). Logs werden nie automatisch
gelöscht, nur komprimiert.

**Alternativen:** Qdrant als primäre Persistenz, Logs nur für Debugging. Abgelehnt, weil
Embedding-Modell-Wechsel (z.B. bge-m3 → Nachfolger) eine vollständige Neuindexierung erfordern —
ohne Rohdaten ist das unmöglich.

**Auswirkung:** `core/agent.py` (JSONL-Logging), `admin-interface/routers/memory.py`
(Rebuild-Endpunkt), `/data/logs/`-Verzeichnisstruktur. Speicherbedarf unkritisch (Textdateien).

---

## 2026-03-05 | Claude Code SDK direkt — kein LangChain, kein n8n

**Kontext:** Zu Projektbeginn standen verschiedene Agent-Frameworks zur Auswahl.
LangChain und n8n wurden als potenzielle Basis diskutiert.

**Entscheidung:** Jede Chat-Instanz ist direkt ein `claude-code-sdk`-Agent. Kein eigenes
Routing-Framework. Claude entscheidet selbst, welches Tool wann aufgerufen wird.
Der System-Prompt (`CLAUDE.md` pro Instanz) definiert Persönlichkeit und Berechtigungen.
Neue Skills = CLAUDE.md erweitern + neue Python-Tool-Funktionen, kein Framework-Wissen nötig.

**Alternativen:** LangChain für Tool-Orchestrierung; n8n für Workflow-basierte Agent-Logik.
Beide abgelehnt: LangChain ist Overhead über dem SDK; n8n ist für Automationen geeignet,
nicht für Agent-interne Entscheidungslogik. NanoClaw hat bewiesen: SDK direkt reicht.

**Auswirkung:** `core/agent.py` (gesamte Agent-Logik), `instanzen/templates/` (System-Prompts).
Kein separates Routing-LLM, kein einfach/komplex-Split — ein Agent entscheidet vollständig selbst.

---

## 2026-03-04 | Memory-Scopes: dynamisch aus Config, nie hardcodiert

**Kontext:** Frühe Implementierung hatte Memory-Collections (`alice_memory`, `bob_memory`) als
Konstanten im Code. Bei mehreren Nutzern oder geänderten Instanz-Namen waren Code-Änderungen nötig.

**Entscheidung:** Memory-Scopes werden vollständig aus `config.json` (`cfg["users"]`) abgeleitet.
Schema: `{instance}_memory` dynamisch generiert. Kein Instanz-Name (Benutzername) wird im
Code hardcodiert — auch nicht als Default, Fallback oder Kommentar-Beispiel.

**Alternativen:** Feste Collection-Namen als Konfigurationswerte im Code. Abgelehnt, weil
jeder hardcodierte Benutzername Annahmen über die Deployment-Umgebung in den Code trägt
und Community-Forks sofort angepasst werden müssten.

**Auswirkung:** `core/agent.py`, `core/memory.py`, `admin-interface/routers/memory.py`.
Gilt als absolute Coding-Regel für alle Agenten und ist in CLAUDE.md verankert.

---

## 2026-03-03 | 3-Tier HA Voice Pipeline mit Fake-Ollama-Modellen pro Instanz

**Kontext:** HA Voice benötigt schnelle Antworten (Tier 1+2) für einfache Befehle, aber
auch Zugang zum vollständigen HAANA-Agent für komplexe Anfragen (Kalender, Einkaufsliste).
Eine einzige Schicht kann nicht beides gleichzeitig optimal erfüllen.

**Entscheidung:** 3-Tier-Architektur: HA interner Parser (Tier 1, null Latenz) →
HAANA Voice Backend mit lokalem ministral-Modell + Qdrant-Kontext (Tier 2, ~50–200ms) →
vollständiger HAANA-Agent async mit TTS-Zwischenantwort (Tier 3). Jede Instanz bekommt
ein eigenes Fake-Ollama-Modell (HAANA-Alice, HAANA-Bob, HAANA-HA) — HA wählt das Modell,
HAANA weiß damit sofort welche Instanz und welches Memory aktiv ist.

**Alternativen:** Alle Voice-Anfragen direkt an den vollständigen Agenten. Abgelehnt,
weil "Licht an" nicht 2–5 Sekunden LLM-Latenz braucht. Single-Tier mit separatem
Schnell-Router abgelehnt, weil ein zweites Routing-LLM Overhead ohne Mehrwert ist.

**Auswirkung:** `core/ollama_compat.py`, `core/agent.py` (Delegation-Feedback),
`instanzen/templates/ha-assist.md`, `docker-compose.yml` (Port 11434).

---

## 2026-03-02 | Traumprozess: Memory-Konsolidierung als Hintergrundprozess

**Kontext:** Qdrant akkumuliert im Betrieb doppelte, widersprüchliche und veraltete
Memory-Einträge. Echtzeit-Deduplizierung bei jedem Schreibvorgang wäre zu langsam und teuer.

**Entscheidung:** Nächtlicher "Traumprozess" (`core/dream.py`): HA löst via Webhook aus
wenn alle Personen schlafen (person.X focus mode = "Schlafen" > 30 Minuten), Fallback
täglich 03:00 Uhr. Chunked Processing: Qdrant liefert thematische Cluster, lokales LLM
(ministral-3-32k:3b) konsolidiert pro Cluster. Ergebnis: Tages-Tagebuch in
`/data/logs/dream/{instance}/YYYY-MM-DD.jsonl`. "Dream Now"-Button im Admin-Interface.

**Alternativen:** Manuelle Memory-Bereinigung durch den User im Admin-Interface.
Abgelehnt, weil das bei hunderten Einträgen pro Woche nicht skaliert und den User
mit Systemwartung belastet.

**Auswirkung:** `core/dream.py`, `admin-interface/routers/dream.py`,
`admin-interface/templates/index.html` (Dream-Tab), `docker-compose.yml` (Cron-Trigger).
LLM-Auswahl für den Traumprozess ist im Admin-Interface konfigurierbar.
