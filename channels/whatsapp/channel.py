"""
HAANA WhatsApp Channel — Self-describing Channel-Klasse.

Delegiert zur Laufzeit an routers/whatsapp.py — diese Klasse verändert
den bestehenden Code nicht, sie beschreibt ihn nur für die ModuleRegistry.

Konfiguration:
  Global:   whatsapp.mode, whatsapp.self_prefix, bridge_url (via Env)
  Pro-User: whatsapp_phone, whatsapp_lid (optional)
"""

from __future__ import annotations
from common.types import ConfigField
from channels.base import BaseChannel


class WhatsAppChannel(BaseChannel):
    """WhatsApp als Eingangskanal via Baileys-Bridge.

    Jeder User wird anhand seiner Telefonnummer (whatsapp_phone) gematcht.
    Optional: LID-basiertes Routing für Multi-Device-Setups.
    """

    channel_id = "whatsapp"
    display_name = "WhatsApp"
    config_root = "whatsapp"

    def get_config_schema(self) -> list[ConfigField]:
        """Globale WhatsApp-Konfiguration."""
        return [
            ConfigField(
                key="mode",
                label="Mode",
                label_de="Modus",
                field_type="select",
                required=False,
                default="separate",
                options=["separate", "self"],
                hint="'separate': dedicated number for HAANA. 'self': share your own number (prefix required).",
                hint_de="'separate': eigene HAANA-Nummer. 'self': eigene Nummer teilen (Prefix erforderlich).",
            ),
            ConfigField(
                key="self_prefix",
                label="Self-Prefix",
                label_de="Self-Prefix",
                field_type="text",
                required=False,
                default="!h ",
                hint="Only used in 'self' mode. Messages starting with this prefix are routed to HAANA.",
                hint_de="Nur im 'self'-Modus. Nachrichten mit diesem Prefix werden an HAANA geroutet.",
            ),
            ConfigField(
                key="bridge_url",
                label="Bridge URL (optional)",
                label_de="Bridge-URL (optional)",
                field_type="text",
                required=False,
                default="",
                hint="URL of the WhatsApp Bridge. Leave empty to use default (WHATSAPP_BRIDGE_URL env or http://whatsapp-bridge:3001).",
                hint_de="URL der WhatsApp-Bridge. Leer lassen für Standard (WHATSAPP_BRIDGE_URL env oder http://whatsapp-bridge:3001).",
            ),
        ]

    def get_custom_tab_html(self) -> str:
        """Verbindungsstatus-Block, QR-Code, Bridge-Buttons für den Admin-Tab."""
        return (
            '<div class="config-section">'
            '<div class="config-section-header">WhatsApp Bridge</div>'
            '<div class="config-section-body">'
            '<div id="wa-connection" class="wa-connection">'
            '<div class="wa-status-row">'
            '<div class="wa-status-indicator">'
            '<span id="wa-status-dot" class="wa-status-dot"></span>'
            '<strong id="wa-status-text">Status wird geladen\u2026</strong>'
            '</div>'
            '<div class="form-inline">'
            '<button class="btn btn-sm btn-secondary" onclick="refreshWaStatus()">Aktualisieren</button>'
            '<button class="btn btn-sm btn-secondary" id="wa-logout-btn" style="display:none;" onclick="waLogout()">Trennen</button>'
            '<button class="btn btn-sm btn-danger" onclick="waBridgeStop()" id="wa-stop-btn" style="display:none">Bridge stoppen</button>'
            '</div>'
            '</div>'
            '<div id="wa-account-info" class="wa-account-info" style="display:none;">'
            'Verbunden als: <span id="wa-account-name"></span> (<span id="wa-account-jid"></span>)'
            '</div>'
            '<div id="wa-qr-container" class="wa-qr-container" style="display:none;">'
            '<p class="form-hint" style="margin-bottom:8px;">QR-Code mit WhatsApp scannen (Verkn\u00fcpfte Ger\u00e4te \u2192 Ger\u00e4t hinzuf\u00fcgen):</p>'
            '<img id="wa-qr-img" alt="QR-Code">'
            '<p class="form-hint" style="margin-top:6px;">Code wird automatisch aktualisiert\u2026</p>'
            '</div>'
            '<div id="wa-offline-info" class="form-hint" style="display:none;">'
            'Bridge-Container nicht erreichbar. Starte mit: <code class="tag">docker compose --profile agents up -d</code>'
            '<br><button class="btn btn-primary" onclick="waBridgeStart()" id="wa-start-btn" style="margin-top:8px;">Bridge starten</button>'
            '</div>'
            '</div>'
            '</div>'
            '</div>'
        )

    def get_user_config_schema(self) -> list[ConfigField]:
        """Pro-User WhatsApp-Konfiguration."""
        return [
            ConfigField(
                key="whatsapp_phone",
                label="WhatsApp Phone Number",
                label_de="WhatsApp-Telefonnummer",
                field_type="text",
                required=False,
                hint="International format without +, e.g. 49123456789",
                hint_de="Internationales Format ohne +, z.B. 49123456789",
            ),
            ConfigField(
                key="whatsapp_lid",
                label="WhatsApp LID (optional)",
                label_de="WhatsApp LID (optional)",
                field_type="text",
                required=False,
                hint="Device-linked ID. Set automatically when detected by the bridge.",
                hint_de="Gerätegebundene ID. Wird automatisch von der Bridge gesetzt wenn erkannt.",
            ),
        ]

    def get_docker_service(self) -> dict:
        """Beschreibt den whatsapp-bridge Docker-Service (als Referenz)."""
        return {
            "image": "node:20-alpine",
            "working_dir": "/app",
            "volumes": ["./whatsapp-bridge:/app", "haana-data:/data"],
            "environment": {
                "BRIDGE_SECRET": "${HAANA_BRIDGE_SECRET}",
                "HAANA_ADMIN_URL": "${HAANA_ADMIN_SELF_URL}",
            },
            "restart": "unless-stopped",
        }

    def is_enabled(self, config: dict) -> bool:
        """WhatsApp ist aktiv wenn mindestens ein nicht-System-User eine Telefonnummer hat."""
        users = config.get("users", [])
        return any(
            u.get("whatsapp_phone", "").strip()
            for u in users
            if not u.get("system")
        )
