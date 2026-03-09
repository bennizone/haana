# HAANA Entwicklungs-Logbuch

Chronologische Dokumentation der wichtigsten Aenderungen am HAANA-Projekt.

---

## 2026-03-09 — Sub-Agenten, Log-Management, Fake-Ollama Delegation

- Sub-Agenten fuer Review, Webinterface-Entwicklung und Dokumentation eingerichtet (`.claude/agents/`)
- Log-Download als ZIP und Loesch-Funktion im Admin-Interface implementiert (`/api/logs-download`, `/api/logs-delete`)
- `ha_voice`-Instruktionen auch in CLAUDE.md Templates ergaenzt
- User-Agents werden automatisch als Ollama-Modelle exponiert (Agent-Routing in `ollama_compat.py`)
- `ha_voice` Memory: Extraktion nur noch bei expliziten Speicher-Befehlen ("merke dir", "vergiss nicht" etc.)
- Delegation ha-assist nach ha-advanced via `[DELEGATE]`-Marker (Agent-API statt direktem LLM-Call)
- Universeller LLM-Proxy (Fake-Ollama-API) mit Tool-Calling-Support fuer alle Provider

## 2026-03-08 — Memory-Extraktion Multi-Provider, Context Enrichment, Rebuild

- Konfigurierbares Kontext-Fenster fuer Memory-Extraktion (`context_before`/`context_after`)
- Ollama Thinking-Support (Monkeypatch `client.chat`, `num_predict=8192`)
- Rebuild-Fortschritt: Pause/Resume mit persistentem Progress, Verwerfen-Button
- Review-Fixes: Persoenliche Daten entfernt, Tests erweitert, Code-Qualitaet verbessert
- MiniMax ThinkingBlock-Workaround (`_call_anthropic_direct()`), Anthropic `base_url`-Patch
- Rate-Limiter pro LLM (Token-Bucket, shared Registry), OAuth-Extraction via Claude CLI
- Gemini als Extraction-LLM und Scope-Klassifikation unterstuetzt
- Extraction-LLM nur noch global (nicht mehr per User)
- Multi-Provider Embeddings (Ollama/OpenAI/Gemini), Gemini Embedding `models/gemini-embedding-001`
- Mem0 LLM-Antworten sanitizen (MiniMax Dict/String Kompatibilitaet)
- Smart Memory Rebuild (Pre-Filtering trivialer Eintraege, Rate-Limiting, Pause/Resume)
- Multi-Provider Memory Extraction + Context Enrichment
- Env-Isolation fuer InProcess-Modus (agent.py + memory.py Env-Snapshots)
- Embedding-Mismatch-Detection (`_check_collection_dims()`, loescht Collection bei Mismatch)

## 2026-03-07 — Provider-Redesign, AgentManager, HA Add-on, OAuth

- LLM-Provider-Routing korrigiert (Env-Var-Kette fuer alle Provider-Typen)
- OAuth-Credentials-Fix, i18n-Init-Fix, Chat-UI-Details
- core/ Volume in admin-interface Container gemountet
- Restart-Feedback bei LLM-Aenderung im Users-Tab
- Plan v7 aktualisiert nach HA Add-on Architektur
- HA Add-on Repository mit 3 Add-ons (haana, haana-ollama-cpu, haana-whatsapp)
- AgentManager-Abstraktion: DockerAgentManager + InProcessAgentManager (Dual-Mode)
- Provider/LLM-Trennung: `providers[]` + `llms[]` statt `llm_providers[]`
- Typspezifische Provider-Formulare (Anthropic, Ollama, MiniMax, OpenAI, Gemini, Custom)
- OAuth pro Provider mit eigenen Credential-Pfaden
- Provider-Umbenennung: Live-Sync in `cfg.providers`
- Review-Findings adressiert (XSS, URL Injection, Permissions, Path Traversal)
- OAuth Login Flow im Admin-Interface (PTY-basiert, /proc/net/tcp Port-Detection)
- Vollstaendige i18n fuer chat/config JS, API-Key Auth Option
- Docker Image von 10.5 GB auf 327 MB reduziert (sentence-transformers entfernt, CPU-only)
- Claude OAuth Management im Admin-Interface

## 2026-03-06 — Admin-Interface Modernisierung, STT/TTS, Config Tabs

- Tests fuer Agent MCP, Config Management, i18n Paritaet
- Config-Tabs umstrukturiert, HA Auto-Backup Setting
- MCP Typ-Auswahl (builtin vs extended ha-mcp)
- ~1700 Zeilen inline JS in 10 separate Module extrahiert
- Admin UI Design modernisiert (Glassmorphism, Dark Theme, Responsive)
- `confirm()` Dialoge durch Modal-System ersetzt
- CSS/JS/i18n aus monolithischer index.html extrahiert
- Restart-Detection: Erkennt config-aenderungen die Container-Neustart erfordern
- Fuehrende/trailing Leerzeilen aus Agent-Antworten entfernen
- Sprachoptimierter Prompt + Text zusaetzlich zu Voice
- TTS Audio zu OGG Opus konvertieren + Voice-Auswahl im Admin-Interface

---

## Legende

- **feat:** Neues Feature
- **fix:** Bugfix
- **refactor:** Code-Umstrukturierung ohne Funktionsaenderung
- **perf:** Performance-Verbesserung
- **test:** Tests hinzugefuegt/erweitert
- **docs:** Dokumentation
- **chore:** Wartungsarbeiten
