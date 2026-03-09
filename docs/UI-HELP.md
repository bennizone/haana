# HAANA Admin-Interface UI-Hilfe

Hilfe-Texte fuer alle UI-Bereiche des Admin-Interface.

---

## Bereich: Header

#### Sprachauswahl
- **de:** "Sprache der Benutzeroberflaeche umschalten (Deutsch/Englisch)"
- **en:** "Switch UI language (German/English)"
- **i18n-key:** `app.title`

#### Status-Punkt (Header)
- **de:** "Zeigt den Gesamtstatus des Systems (gruen = OK, rot = Fehler)"
- **en:** "Shows overall system health (green = OK, red = error)"
- **i18n-key:** `status.system_ok`, `status.system_error`

---

## Bereich: Navigation (Tabs)

#### Chat
- **de:** "Konversationen ansehen und mit HAANA chatten"
- **en:** "View conversations and chat with HAANA"
- **i18n-key:** `tabs.chat`

#### Logs
- **de:** "System-Logs einsehen (Memory-Operationen, Tool-Aufrufe, LLM-Calls)"
- **en:** "View system logs (memory operations, tool calls, LLM calls)"
- **i18n-key:** `tabs.logs`

#### Config
- **de:** "Konfiguration verwalten (Provider, LLMs, Memory, HA, WhatsApp)"
- **en:** "Manage configuration (providers, LLMs, memory, HA, WhatsApp)"
- **i18n-key:** `tabs.config`

#### Users
- **de:** "User-Verwaltung (anlegen, bearbeiten, loeschen, Agents starten/stoppen)"
- **en:** "User management (create, edit, delete, start/stop agents)"
- **i18n-key:** `tabs.users`

#### Status
- **de:** "Systemstatus pruefen (Qdrant, Ollama, Agent-Instanzen, Logs)"
- **en:** "Check system status (Qdrant, Ollama, agent instances, logs)"
- **i18n-key:** `tabs.status`

---

## Bereich: Chat-Tab

#### Instanz-Buttons
- **de:** "Zwischen den verschiedenen Agent-Instanzen wechseln"
- **en:** "Switch between different agent instances"

#### Letzte (Limit-Selektor)
- **de:** "Anzahl der angezeigten Konversationen begrenzen"
- **en:** "Limit the number of displayed conversations"
- **i18n-key:** `chat.last`

#### Live-Punkt
- **de:** "Zeigt ob die SSE-Verbindung aktiv ist (gruen = verbunden)"
- **en:** "Shows if the SSE connection is active (green = connected)"
- **i18n-key:** `chat.live`

#### Agent-Status
- **de:** "Zeigt ob der Agent online oder offline ist"
- **en:** "Shows if the agent is online or offline"
- **i18n-key:** `chat.agent_online`, `chat.agent_offline`

#### Chat-Eingabe
- **de:** "Nachricht an HAANA senden. Enter = senden, Shift+Enter = Zeilenumbruch."
- **en:** "Send a message to HAANA. Enter = send, Shift+Enter = newline."
- **i18n-key:** `chat.placeholder`

#### Rebuild-Banner
- **de:** "Erscheint wenn Qdrant leer ist aber Konversations-Logs vorhanden sind. Empfiehlt Memory-Rebuild."
- **en:** "Appears when Qdrant is empty but conversation logs exist. Recommends memory rebuild."
- **i18n-key:** `chat.rebuild_banner`

---

## Bereich: Logs-Tab

#### Log-Kategorien
- **de:** "Memory = Extraktions-Operationen, Tools = MCP/Tool-Aufrufe, LLM Calls = API-Aufrufe an LLMs"
- **en:** "Memory = extraction operations, Tools = MCP/tool calls, LLM Calls = API calls to LLMs"
- **i18n-key:** `logs.memory`, `logs.tools`, `logs.llm_calls`

#### Log-Download
- **de:** "Alle Logs als ZIP-Datei herunterladen. Scope waehlbar: alle, System, Konversationen."
- **en:** "Download all logs as ZIP file. Scope selectable: all, system, conversations."
- **i18n-key:** `logs.download_all`, `logs.download_system`, `logs.download_conversations`

#### Log-Loeschen
- **de:** "Logs unwiderruflich loeschen. Konversations-Logs sind Source of Truth fuer Memory-Rebuild!"
- **en:** "Permanently delete logs. Conversation logs are source of truth for memory rebuild!"
- **i18n-key:** `logs.delete_all`, `logs.delete_system`, `logs.delete_conversations`

#### Log-Dateien (editierbar)
- **de:** "Einzelne JSONL-Dateien anzeigen und bearbeiten. Nach dem Bearbeiten Memory-Rebuild empfohlen."
- **en:** "View and edit individual JSONL files. Memory rebuild recommended after editing."
- **i18n-key:** `logs.log_files`, `log_editor.warning`

---

## Bereich: Config-Tab

### Sub-Tab: Providers

#### Provider hinzufuegen
- **de:** "Neuen LLM-Provider anlegen. 6 Typen verfuegbar: Anthropic, Ollama, MiniMax, OpenAI, Gemini, Custom."
- **en:** "Add new LLM provider. 6 types available: Anthropic, Ollama, MiniMax, OpenAI, Gemini, Custom."
- **i18n-key:** `config_provider.add_provider`, `config_provider.select_type`

#### Anthropic Auth-Methode
- **de:** "API-Key: Direkt eingeben, kein Ablauf. OAuth: Claude Pro/Team Login via 'setup-token' — erzeugt langlebigen Token (~1 Jahr), kein regelmaessiger Ablauf."
- **en:** "API-Key: Enter directly, no expiration. OAuth: Claude Pro/Team login via 'setup-token' — creates long-lived token (~1 year), no regular expiration."
- **i18n-key:** `config_provider.auth_method_apikey`, `config_provider.auth_method_oauth`

#### OAuth Login starten
- **de:** "Oeffnet den Claude OAuth Login-Flow. Du erhaeltst eine URL die du im Browser oeffnest, anschliessend den angezeigten Code hier einfuegst. Der Token ist ca. 1 Jahr gueltig."
- **en:** "Opens the Claude OAuth login flow. You receive a URL to open in your browser, then paste the displayed code here. The token is valid for approximately 1 year."
- **i18n-key:** `auth.login_start`, `auth.login_instructions`

#### Token-Status (langlebig)
- **de:** "Zeigt 'Token gueltig (langlebig)' wenn ein setup-token ohne Ablaufdatum gespeichert ist. Erneuerung ist nicht regelmaessig noetig."
- **en:** "Shows 'Token valid (long-lived)' when a setup-token without expiry is stored. Renewal is not regularly required."
- **i18n-key:** `auth.status_long_lived`

#### Provider URL
- **de:** "API-Endpunkt URL. Bei Anthropic/OpenAI leer lassen fuer Standard-URL. Bei Ollama Pflichtfeld."
- **en:** "API endpoint URL. Leave empty for Anthropic/OpenAI default. Required for Ollama."
- **i18n-key:** `config_provider.url`, `config_provider.url_hint`

#### Verbindung testen
- **de:** "Testet die Verbindung zum Provider. Bei Ollama werden verfuegbare Modelle angezeigt."
- **en:** "Tests the connection to the provider. For Ollama, available models are shown."
- **i18n-key:** `config_provider.test_connection`

### Sub-Tab: LLMs

#### LLM hinzufuegen
- **de:** "Neues LLM anlegen. Jedes LLM braucht einen Provider und eine Modell-ID."
- **en:** "Add new LLM. Each LLM needs a provider and a model ID."
- **i18n-key:** `config_llm.add_llm`

#### Modelle laden
- **de:** "Verfuegbare Modelle vom Provider abrufen. Bei Ollama: installierte Modelle. Bei Anthropic: bekannte Modelle."
- **en:** "Fetch available models from provider. Ollama: installed models. Anthropic: known models."
- **i18n-key:** `config_llm.fetch_models`

#### Rate Limit (RPM)
- **de:** "Requests pro Minute fuer dieses LLM. 0 = kein Limit. Wichtig fuer API-Provider mit Rate-Limits."
- **en:** "Requests per minute for this LLM. 0 = no limit. Important for API providers with rate limits."
- **i18n-key:** `config_llm.rpm`, `config_llm.rpm_hint`

### Sub-Tab: Memory

#### Sliding Window
- **de:** "Das Sliding Window sammelt Nachrichten bevor sie ins Langzeitgedaechtnis (Qdrant) extrahiert werden."
- **en:** "The sliding window collects messages before they are extracted to long-term memory (Qdrant)."
- **i18n-key:** `config_memory.window_title`

#### Window-Groesse
- **de:** "Max. Anzahl Nachrichten im Window. Bei Ueberschreitung werden aelteste Nachrichten extrahiert."
- **en:** "Max number of messages in window. Oldest messages are extracted when exceeded."
- **i18n-key:** `config_memory.window_size`

#### Window-Alter
- **de:** "Max. Alter in Minuten. Nachrichten die aelter sind werden extrahiert."
- **en:** "Max age in minutes. Messages older than this are extracted."
- **i18n-key:** `config_memory.window_minutes`

#### Minimum (immer aktiv)
- **de:** "Mindestanzahl Nachrichten die immer im Window bleiben (auch wenn sie aelter als Window-Alter sind)."
- **en:** "Minimum messages that always stay in window (even if older than window age)."
- **i18n-key:** `config_memory.min_messages`

#### Extraktions-LLM
- **de:** "LLM fuer die Memory-Extraktion. Wird global fuer alle User verwendet. Mem0 macht intern 3-5 LLM-Calls pro add()."
- **en:** "LLM for memory extraction. Used globally for all users. Mem0 makes 3-5 internal LLM calls per add()."
- **i18n-key:** `config_memory.extraction_llm`, `config_memory.extraction_llm_hint`

#### Kontext-Anreicherung
- **de:** "Loest Pronomen und Bezuege vor der Extraktion auf (extra LLM-Call). Nur bei leistungsfaehigen Modellen empfohlen (MiniMax, Claude Haiku). Kleine Modelle koennen fehlerhafte Extraktionen erzeugen."
- **en:** "Resolves pronouns and references before extraction (extra LLM call). Only recommended with capable models (MiniMax, Claude Haiku). Small models may produce erroneous extractions."
- **i18n-key:** `config_memory.context_enrichment`, `config_memory.context_enrichment_hint`

#### Kontext-Fenster
- **de:** "Anzahl Nachrichten vor/nach der aktuellen bei Extraktion. Mehr Kontext hilft bei Korrekturen, kostet aber mehr Tokens."
- **en:** "Number of messages before/after current during extraction. More context helps with corrections but costs more tokens."
- **i18n-key:** `config_memory.context_before`, `config_memory.context_after`, `config_memory.context_window_hint`

#### Embedding-Modell
- **de:** "Wandelt Text in Vektoren um fuer Qdrant-Suche. ACHTUNG: Beim Wechsel muessen ALLE Collections neu aufgebaut werden!"
- **en:** "Converts text to vectors for Qdrant search. WARNING: Changing requires rebuilding ALL collections!"
- **i18n-key:** `config_memory.embedding_title`, `config_memory.embedding_warning`

#### Embedding-Dimensions
- **de:** "Wird automatisch vom Modell bestimmt. Manuell nur aendern wenn Sie die exakte Dimension kennen."
- **en:** "Automatically determined by the model. Only change manually if you know the exact dimension."
- **i18n-key:** `config_memory.embedding_dims`

#### Memory Rebuild
- **de:** "Baut Qdrant komplett neu aus Konversations-Logs auf. Noetig nach Datenverlust oder Embedding-Modell-Wechsel. Kann Stunden dauern."
- **en:** "Completely rebuilds Qdrant from conversation logs. Needed after data loss or embedding model change. May take hours."
- **i18n-key:** `config_memory.rebuild_title`

#### Triviale Eintraege ueberspringen
- **de:** "Kurze Kommandos (Licht an, Hallo, Status) werden nicht verarbeitet. Spart Zeit und Tokens."
- **en:** "Short commands (light on, hello, status) are skipped. Saves time and tokens."
- **i18n-key:** `config_memory.rebuild_skip_trivial`

#### Rebuild-Verzoegerung
- **de:** "Wartezeit zwischen Eintraegen in ms. Hoeher = langsamer aber weniger API-Last. Empfohlen bei API-Providern."
- **en:** "Wait time between entries in ms. Higher = slower but less API load. Recommended for API providers."
- **i18n-key:** `config_memory.rebuild_delay`, `config_memory.rebuild_delay_hint`

### Sub-Tab: Home Assistant

#### HA URL
- **de:** "URL deiner Home Assistant Instanz (z.B. http://homeassistant.local:8123). Wird fuer MCP, STT/TTS und User-Mapping benoetigt."
- **en:** "URL of your Home Assistant instance. Needed for MCP, STT/TTS and user mapping."

#### HA Long-Lived Token
- **de:** "Erstelle unter HA Profil > Sicherheit > Long-Lived Access Tokens. Wird fuer alle HA-Integrationen benoetigt."
- **en:** "Create under HA Profile > Security > Long-Lived Access Tokens. Needed for all HA integrations."

#### MCP Server
- **de:** "Model Context Protocol Server: Gibt dem Agent Zugriff auf HA-Entities, Automationen, Kalender etc."
- **en:** "Model Context Protocol Server: Gives the agent access to HA entities, automations, calendars etc."
- **i18n-key:** `config_services.mcp_title`

#### MCP Typ
- **de:** "Integriert = HA 2025.1+ eingebaut (6 Basis-Tools). Erweitert = ha-mcp Add-on (89 Tools, muss installiert werden)."
- **en:** "Built-in = HA 2025.1+ included (6 basic tools). Extended = ha-mcp add-on (89 tools, must be installed)."
- **i18n-key:** `config_services.mcp_type_builtin`, `config_services.mcp_type_extended`

#### STT Entity
- **de:** "Spracherkennung-Entity aus Home Assistant (z.B. stt.home_assistant_cloud fuer Nabu Casa)"
- **en:** "Speech-to-text entity from Home Assistant (e.g. stt.home_assistant_cloud for Nabu Casa)"
- **i18n-key:** `config_services.stt_entity`

#### TTS Entity
- **de:** "Sprachausgabe-Entity aus Home Assistant (z.B. tts.home_assistant_cloud fuer Nabu Casa)"
- **en:** "Text-to-speech entity from Home Assistant (e.g. tts.home_assistant_cloud for Nabu Casa)"
- **i18n-key:** `config_services.tts_entity`

#### TTS Stimme
- **de:** "Optional: Nabu Casa Stimme (z.B. DeAmala, DeKatja, DeConrad). Leer = Standardstimme."
- **en:** "Optional: Nabu Casa voice (e.g. DeAmala, DeKatja, DeConrad). Empty = default voice."
- **i18n-key:** `config_services.tts_voice`

#### Auto-Backup
- **de:** "Erstellt ein HA-Backup bevor der Agent Automationen, Scripts oder andere Konfigurationen aendert."
- **en:** "Creates an HA backup before the agent modifies automations, scripts or other configurations."
- **i18n-key:** `config_services.auto_backup_label`, `config_services.auto_backup_desc`

### Sub-Tab: WhatsApp

#### Modus
- **de:** "Separate Nummer: HAANA hat eigene SIM/Telefonnummer. Selbst: Du schreibst dir selbst mit Prefix (z.B. '!h Licht an')."
- **en:** "Separate number: HAANA has its own SIM/phone number. Self: You text yourself with prefix (e.g. '!h light on')."
- **i18n-key:** `config_services.wa_mode_separate`, `config_services.wa_mode_self`

#### QR-Code
- **de:** "QR-Code scannen unter WhatsApp > Verknuepfte Geraete > Geraet hinzufuegen. Code wird automatisch aktualisiert."
- **en:** "Scan QR code under WhatsApp > Linked Devices > Add Device. Code refreshes automatically."
- **i18n-key:** `config_services.wa_scan_qr`

### Sub-Tab: Infra

#### Qdrant URL
- **de:** "Vektor-Datenbank fuer Memory-Suche. Standard: http://qdrant:6333 (Docker) oder http://10.83.1.11:6333"
- **en:** "Vector database for memory search. Default: http://qdrant:6333 (Docker) or http://10.83.1.11:6333"
- **i18n-key:** `config_services.qdrant_url`

### Sub-Tab: Retention

#### Log-Retention
- **de:** "Operative Logs werden nach konfigurierbaren Tagen automatisch geloescht. Konversations-Logs werden NIE geloescht (Source of Truth)."
- **en:** "Operational logs are automatically deleted after configurable days. Conversation logs are NEVER deleted (source of truth)."
- **i18n-key:** `config_logs.retention_title`, `config_logs.retention_desc`

### Sub-Tab: CLAUDE.md

#### CLAUDE.md Editor
- **de:** "System-Prompt pro Instanz bearbeiten. Aenderungen sind sofort aktiv (kein Neustart noetig)."
- **en:** "Edit system prompt per instance. Changes are immediately active (no restart needed)."
- **i18n-key:** `config_claude_md.title`

---

## Bereich: Users-Tab

#### Neuer User
- **de:** "Neuen User anlegen. ID muss einmalig sein (a-z, 0-9, -). Port wird automatisch vergeben. CLAUDE.md wird aus Template generiert."
- **en:** "Create new user. ID must be unique (a-z, 0-9, -). Port is auto-assigned. CLAUDE.md is generated from template."
- **i18n-key:** `users.new_user`

#### User-Rollen
- **de:** "Admin = voller Zugriff auf alle MCP-Tools. User = eingeschraenkte Rechte."
- **en:** "Admin = full access to all MCP tools. User = restricted permissions."
- **i18n-key:** `users.role_admin`, `users.role_user`

#### HA-User
- **de:** "Person-Entitaet aus Home Assistant. Wird fuer personalisierte HA-Interaktionen verwendet."
- **en:** "Person entity from Home Assistant. Used for personalized HA interactions."
- **i18n-key:** `users.ha_user`, `users.ha_user_hint`

#### WhatsApp Rufnummer
- **de:** "Internationale Rufnummer ohne + und ohne Leerzeichen (z.B. 491234567890). Wird fuer Nachricht-Routing verwendet."
- **en:** "International phone number without + and spaces (e.g. 491234567890). Used for message routing."
- **i18n-key:** `users.wa_phone`, `users.wa_phone_hint`

#### Primaeres LLM
- **de:** "Haupt-LLM fuer diesen User. Bestimmt welches Modell fuer Chat-Antworten verwendet wird."
- **en:** "Primary LLM for this user. Determines which model is used for chat responses."
- **i18n-key:** `users.primary_llm`

#### Fallback LLM
- **de:** "Wird verwendet wenn das primaere LLM nicht erreichbar ist."
- **en:** "Used when the primary LLM is not reachable."
- **i18n-key:** `users.fallback_llm`

#### Neustart / Stop
- **de:** "Neustart erstellt den Agent-Container mit aktueller Config neu. Stop beendet den Agent graceful."
- **en:** "Restart recreates the agent container with current config. Stop terminates the agent gracefully."
- **i18n-key:** `users.restart`, `users.stop`

#### CLAUDE.md pro User
- **de:** "System-Prompt fuer diesen User bearbeiten. 'Role Default laden' setzt den Inhalt auf das Template der aktuellen Rolle zurueck."
- **en:** "Edit system prompt for this user. 'Load role default' resets content to the current role template."
- **i18n-key:** `users.edit_claude_md`, `users.load_role_default`

---

## Bereich: Status-Tab

#### Qdrant
- **de:** "Vektor-Datenbank Status. Zeigt Collections, Vektor-Anzahl und Dimensions-Mismatch Warnung."
- **en:** "Vector database status. Shows collections, vector count and dimension mismatch warning."
- **i18n-key:** `status.vectors`, `status.dims_mismatch`

#### Ollama
- **de:** "Lokaler LLM-Server Status. Zeigt verfuegbare Modelle."
- **en:** "Local LLM server status. Shows available models."

#### Agent-Instanzen
- **de:** "Status aller Agent-Container (running/stopped/absent). Sofort-Beenden (SIGKILL) moeglich bei haengenden Agents."
- **en:** "Status of all agent containers (running/stopped/absent). Force-stop (SIGKILL) available for stuck agents."
- **i18n-key:** `status.agent_instances`, `status.force_stop`

#### Collection loeschen
- **de:** "Loescht eine Qdrant-Collection unwiderruflich. Danach Memory-Rebuild noetig."
- **en:** "Permanently deletes a Qdrant collection. Memory rebuild needed afterwards."
- **i18n-key:** `status.delete_collection`
