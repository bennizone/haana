# HA Voice Channel

**Channel-ID:** `ha-voice`
**Paket:** `channels/ha_voice/`
**Config-Root:** `services`

## Beschreibung

Exponiert HAANA als Ollama-kompatibler Server fuer die Home Assistant Sprachintegration.
HA nutzt die eingebaute Ollama-Integration — kein HACS-Addon noetig.

Der eigentliche Fake-Ollama-Proxy laeuft in `core/ollama_compat.py`.
Diese Klasse beschreibt das Konfigurationsschema fuer die ModuleRegistry.

## Architektur

3-Tier:
- `ha-assist` (schnell, lokal) → optional: Delegation an `ha-advanced` (Claude)
- Regulaere User-Agenten koennen ebenfalls als Ollama-Modelle exponiert werden.

## Config-Tab (dynamisch)

Seit Phase 3 (2026-03-13): Der HA-Tab ist vollstaendig dynamisch via `get_custom_tab_html()`.
Kein hardcodierter `cfgpanel-ha` mehr in index.html.

`get_config_schema()` gibt `[]` zurueck — alle UI-Elemente kommen aus `get_custom_tab_html()`.
`modules.js` wurde erweitert: Tabs werden auch erstellt wenn `config_schema=[]` aber `custom_tab_html` vorhanden.

### Element-IDs im custom_tab_html

| ID | Beschreibung |
|----|-------------|
| `svc-ha-url` | Home Assistant URL |
| `svc-ha-token` | HA Long-Lived Token |
| `test-ha-result` | Test-Button Ergebnis |
| `svc-mcp-enabled` | MCP Server Toggle |
| `mcp-section` | MCP Konfigurationsblock |
| `svc-mcp-type` | MCP Typ (builtin/extended) |
| `mcp-info-builtin` | Hinweistext builtin |
| `mcp-info-extended` | Hinweistext extended |
| `mcp-auto-btn` | Auto-Fill URL Button |
| `svc-mcp-url` | MCP Server URL |
| `svc-mcp-url-hint` | MCP URL Hinweis |
| `svc-mcp-token` | MCP Auth-Token |
| `test-mcp-result` | MCP Test Ergebnis |
| `svc-pipeline-select` | HA Pipeline Picker |
| `svc-stt-entity` | STT Entity Select |
| `svc-tts-entity` | TTS Entity Select |
| `svc-stt-language` | STT Sprache |
| `svc-tts-voice` | TTS Stimme |
| `svc-tts-also-text` | Text-Fallback Toggle |
| `svc-ha-auto-backup` | Auto-Backup Toggle |
| `save-btn-ha` | Speichern-Button |
| `save-status-ha` | Speicher-Status |

## JS-Funktionen

Diese Funktionen aus `config.js` werden vom Tab genutzt:
- `saveSectionHa()` / `resetSectionHa()` — Speichern/Zuruecksetzen
- `testHaConnection()` — HA URL+Token testen
- `testMcpConnection()` — MCP Server testen
- `toggleMcpSection()` / `updateMcpTypeHints()` — MCP UI
- `autoFillMcpUrl()` — Auto-Fill MCP URL
- `loadSttTtsEntities()` / `loadHaPipelines()` — Entities laden
- `applyPipeline()` — Pipeline uebernehmen

`showCfgTab('mod-ha_voice')` in app.js ruft `resetSectionHa()` auf → laedt Config + Entities.
