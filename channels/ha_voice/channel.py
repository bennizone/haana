"""
HAANA HA Voice Channel — Home Assistant Sprachintegration.

Exponiert HAANA als Ollama-kompatibler Server, damit HA die eingebaute
Ollama-Integration direkt nutzen kann. Kein HACS-Addon nötig.

Der eigentliche Fake-Ollama-Proxy läuft in core/ollama_compat.py
und wird vom Admin-Interface beim Start eingebunden.
Diese Klasse beschreibt das Konfigurationsschema für die ModuleRegistry.
"""

from __future__ import annotations
from common.types import ConfigField
from channels.base import BaseChannel


class HAVoiceChannel(BaseChannel):
    """Home Assistant Sprach-Integration via Fake-Ollama-API.

    HAANA täuscht einen Ollama-Server vor: HA verbindet sich über
    die eingebaute Ollama-Integration, HAANA routet die Anfragen
    intern an seine LLM-Provider und gibt die Antwort im Ollama-Format zurück.

    3-Tier-Architektur:
      ha-assist (schnell, lokal) → optional: Delegation an ha-advanced (Claude)
      Reguläre User-Agenten können ebenfalls als Ollama-Modelle exponiert werden.
    """

    channel_id = "ha-voice"  # Bindestrich: externe ID-Konvention; Package-Name nutzt Unterstrich (Python)
    display_name = "Home Assistant"
    config_root = "services"

    def get_config_schema(self) -> list[ConfigField]:
        """Globale HA Voice / Fake-Ollama Konfiguration — UI via get_custom_tab_html()."""
        return []

    def get_custom_tab_html(self) -> str:
        """Vollständiges HTML für den Services-Tab im Admin-Interface."""
        return """
    <div class="config-section">
      <div class="config-section-header" data-i18n="config_services.ha_title">Home Assistant</div>
      <div class="config-section-body">
        <div class="form-row">
          <div class="form-group">
            <label>Home Assistant URL</label>
            <input type="url" id="svc-ha-url" placeholder="http://homeassistant.local:8123">
          </div>
          <div class="form-group">
            <label>HA Long-Lived Token</label>
            <input type="password" id="svc-ha-token" placeholder="••••••••">
            <p class="form-hint" data-i18n="config_services.ha_token_hint"></p>
          </div>
        </div>
        <div class="form-inline" style="margin-top:4px;">
          <button class="btn btn-sm btn-secondary" onclick="testHaConnection()">Verbindung testen</button>
          <span id="test-ha-result" class="form-hint"></span>
        </div>

        <!-- MCP Server -->
        <div class="mcp-subsection">
          <div class="mcp-header">
            <span class="label" data-i18n="config_services.mcp_title">MCP Server</span>
            <label class="checkbox-label">
              <input type="checkbox" id="svc-mcp-enabled" onchange="toggleMcpSection(this.checked)">
              <span data-i18n="config_services.mcp_enabled">aktiviert</span>
            </label>
            <div class="mcp-links">
              <a href="https://www.home-assistant.io/integrations/mcp_server/" target="_blank" data-i18n="config_services.mcp_docs">HA MCP Docs</a>
              <a href="https://github.com/homeassistant-ai/ha-mcp" target="_blank">ha-mcp GitHub</a>
            </div>
          </div>
          <div id="mcp-section" style="display:none;">
            <div class="form-row">
              <div class="form-group">
                <label data-i18n="config_services.mcp_type">Typ</label>
                <select id="svc-mcp-type" onchange="updateMcpTypeHints()">
                  <option value="extended" data-i18n="config_services.mcp_type_extended">Erweitert / ha-mcp (89 Tools, Add-on nötig)</option>
                  <option value="builtin" data-i18n="config_services.mcp_type_builtin">Integriert (HA 2025.1+, 6 Basis-Tools)</option>
                </select>
              </div>
            </div>
            <p id="mcp-info-builtin" class="form-hint" style="margin-bottom:10px; display:none;" data-i18n="config_services.mcp_info_builtin">
              Integrierter MCP-Server ab HA 2025.1. In HA unter Einstellungen → Integrationen → Model Context Protocol Server aktivieren.
            </p>
            <p id="mcp-info-extended" class="form-hint" style="margin-bottom:10px;" data-i18n="config_services.mcp_info_extended">
              ha-mcp Add-on bietet 89 Tools: Entity-Steuerung, Automationen, Dashboards, Kalender, Todo-Listen, HACS, History, Backups und mehr.
            </p>
            <div class="form-row">
              <div class="form-group">
                <label data-i18n="config_services.mcp_url">MCP Server URL</label>
                <div class="form-inline">
                  <input type="url" id="svc-mcp-url" style="flex:1;"
                    oninput="document.getElementById('svc-mcp-url-hint').style.display='none'">
                  <button id="mcp-auto-btn" class="btn btn-sm btn-secondary" onclick="autoFillMcpUrl()" style="display:none;" data-i18n="config_services.mcp_auto">Auto</button>
                </div>
                <span id="svc-mcp-url-hint" class="form-hint"></span>
              </div>
              <div class="form-group">
                <label data-i18n="config_services.mcp_token">Auth-Token</label>
                <input type="password" id="svc-mcp-token" placeholder="">
                <span class="form-hint" data-i18n="config_services.mcp_empty_hint">leer = HA-Token verwenden</span>
              </div>
            </div>
            <div class="form-inline" style="margin-top:4px;">
              <button class="btn btn-sm btn-secondary" onclick="testMcpConnection()" data-i18n="config_services.mcp_test">MCP testen</button>
              <span id="test-mcp-result" class="form-hint"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- STT / TTS -->
    <div class="config-section">
      <div class="config-section-header" data-i18n="config_services.stt_tts_title">Sprache (STT / TTS)</div>
      <div class="config-section-body">
        <p class="form-hint" style="margin-bottom:14px;">
          Speech-to-Text und Text-to-Speech über Home Assistant. Entities werden automatisch aus HA geladen.
        </p>

        <!-- Pipeline Picker -->
        <div style="margin-bottom:18px;">
          <label data-i18n="config_services.pipeline">Sprachassistent</label>
          <div class="pipeline-picker-row">
            <select id="svc-pipeline-select">
              <option value="" data-i18n="config_services.pipeline_select">Bitte wählen...</option>
            </select>
            <button class="btn btn-sm btn-secondary" onclick="loadHaPipelines()" data-i18n="config_services.pipeline_load">Laden</button>
            <button class="btn btn-sm btn-primary" onclick="applyPipeline()" data-i18n="config_services.pipeline_apply">Übernehmen</button>
            <span id="pipeline-load-status" class="form-hint"></span>
          </div>
          <div id="pipeline-details" class="pipeline-details" style="display:none;"></div>
        </div>

        <hr style="border:none;border-top:1px solid var(--border);margin-bottom:14px;">

        <div class="form-inline" style="margin-bottom:14px;">
          <button class="btn btn-sm btn-secondary" onclick="loadSttTtsEntities()">Entities laden</button>
          <span id="stt-tts-load-status" class="form-hint"></span>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>STT Entity <span class="hint">(Spracherkennung)</span></label>
            <select id="svc-stt-entity">
              <option value="">– nicht konfiguriert –</option>
            </select>
          </div>
          <div class="form-group">
            <label>TTS Entity <span class="hint">(Sprachausgabe)</span></label>
            <select id="svc-tts-entity">
              <option value="">– nicht konfiguriert –</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Sprache</label>
            <select id="svc-stt-language">
              <option value="de-DE">Deutsch (de-DE)</option>
              <option value="en-US">English (en-US)</option>
              <option value="en-GB">English UK (en-GB)</option>
              <option value="fr-FR">Français (fr-FR)</option>
              <option value="es-ES">Español (es-ES)</option>
              <option value="it-IT">Italiano (it-IT)</option>
              <option value="nl-NL">Nederlands (nl-NL)</option>
              <option value="pl-PL">Polski (pl-PL)</option>
              <option value="pt-BR">Português (pt-BR)</option>
            </select>
          </div>
          <div class="form-group">
            <label>TTS Stimme <span class="hint">(optional)</span></label>
            <input type="text" id="svc-tts-voice" placeholder="z.B. DeAmala, DeKatja, DeConrad">
            <span class="form-hint">
              Nabu Casa Stimmen findest du in der HA App unter Einstellungen → Sprachassistenten → TTS.
              Leer = Standardstimme.
            </span>
          </div>
        </div>
        <div style="margin-top:10px;">
          <label class="checkbox-label">
            <input type="checkbox" id="svc-tts-also-text">
            Antwort zusätzlich als Text senden (neben der Sprachnachricht)
          </label>
        </div>
      </div>
    </div>

    <!-- Auto-Backup -->
    <div class="config-section">
      <div class="config-section-header" data-i18n="config_services.auto_backup_title">Auto-Backup</div>
      <div class="config-section-body">
        <label class="checkbox-label">
          <input type="checkbox" id="svc-ha-auto-backup">
          <span data-i18n="config_services.auto_backup_label">Automatisches HA-Backup vor Agent-Änderungen</span>
        </label>
        <p class="form-hint" data-i18n="config_services.auto_backup_desc">
          Erstellt ein Home Assistant Backup bevor der Agent Automationen, Scripts
          oder andere HA-Konfigurationen ändert.
        </p>
      </div>
    </div>

    <!-- Geplante Dienste -->
    <div class="config-section muted">
      <div class="config-section-header">Geplante Integrationen</div>
      <div class="config-section-body" style="display:flex;flex-direction:column;gap:12px;">
        <div class="planned-card">
          <div class="planned-card-title">HA Subscriptions · Phase 4+</div>
          <div class="planned-card-desc">Echtzeit-Subscriptions auf HA-Ereignisse (Türklingel, Bewegungsmelder, …). Der Agent wird proaktiv benachrichtigt.</div>
        </div>
      </div>
    </div>

    <div class="cfg-section-save-bar">
      <button class="btn btn-primary" id="save-btn-ha" onclick="saveSectionHa()">
        <span data-i18n="config.section_save">Speichern</span>
      </button>
      <button class="btn btn-secondary" onclick="resetSectionHa()">
        <span data-i18n="config.section_reset">&#8635; Zurücksetzen</span>
      </button>
      <span id="save-status-ha" class="cfg-section-save-status"></span>
    </div>
"""

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User HA Voice Konfiguration."""
        return [
            ConfigField(
                key="ha_person_entity",
                label="HA Person Entity",
                label_de="HA Personen-Entität",
                field_type="text",
                required=False,
                hint="e.g. person.firstname -- links this user to an HA person.",
                hint_de="z.B. person.vorname -- verknüpft diesen User mit einer HA-Person.",
            ),
        ]

    def get_docker_service(self) -> None:
        """Kein eigener Docker-Service — HA Voice läuft im admin-interface Container."""
        return None

    def is_enabled(self, config: dict) -> bool:
        """HA Voice ist aktiv wenn ollama_compat aktiviert ist."""
        return bool(config.get("ollama_compat", {}).get("enabled", False))

    def get_status_info(self, config: dict) -> dict:
        svc = config.get("services", {})
        ha_url = svc.get("ha_url", "").strip()
        ha_token = svc.get("ha_token", "").strip()
        mcp_enabled = bool(svc.get("mcp_enabled", False))
        stt_entity = svc.get("stt_entity", "")
        tts_entity = svc.get("tts_entity", "")

        if ha_url and ha_token:
            status = "connected"
            label = "Verbunden"
        elif ha_url:
            status = "degraded"
            label = "Kein Token"
        else:
            status = "unconfigured"
            label = "Nicht konfiguriert"

        metrics = [
            {"label": "MCP", "value": "aktiv" if mcp_enabled else "inaktiv"},
        ]
        if stt_entity:
            metrics.append({"label": "STT", "value": stt_entity})
        if tts_entity:
            metrics.append({"label": "TTS", "value": tts_entity})

        return {
            "status": status,
            "label": label,
            "metrics": metrics,
            "actions": [
                {"id": "open_config", "label": "Konfigurieren", "style": "secondary"}
            ],
        }
