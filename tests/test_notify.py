"""Tests fuer core/notify.py – Proaktive Benachrichtigungen via Webhook."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.notify import create_notify_router, PRIORITIES


# ── Test-Fixtures ────────────────────────────────────────────────────────────

def _make_app(
    agent_url="http://agent:8001",
    bridge_url="http://whatsapp-bridge:3001",
    user_jid="491234567890@s.whatsapp.net",
):
    """Erstellt eine Test-FastAPI-App mit dem Notify-Router."""

    def get_agent_url(instance):
        if instance == "unknown":
            return None
        return agent_url

    def get_config():
        return {
            "users": [
                {
                    "id": "alice",
                    "whatsapp_jid": user_jid,
                },
            ],
            "services": {
                "whatsapp_bridge_url": bridge_url,
            },
        }

    app = FastAPI()
    router = create_notify_router(get_agent_url, get_config)
    app.include_router(router)
    return app


@pytest.fixture
def client():
    """TestClient mit Standard-Konfiguration."""
    app = _make_app()
    return TestClient(app)


@pytest.fixture
def client_no_bridge():
    """TestClient ohne WhatsApp-Bridge-URL."""
    app = _make_app(bridge_url="")
    return TestClient(app)


@pytest.fixture
def client_no_jid():
    """TestClient ohne WhatsApp-JID fuer den User."""
    app = _make_app(user_jid="")
    return TestClient(app)


# ── Validierung ──────────────────────────────────────────────────────────────

class TestWebhookValidation:
    """Tests fuer Request-Validierung."""

    def test_missing_instance(self, client):
        r = client.post("/api/notify/webhook", json={"message": "Test"})
        assert r.status_code == 400
        assert "instance" in r.json()["detail"]

    def test_empty_instance(self, client):
        r = client.post("/api/notify/webhook", json={"instance": "", "message": "Test"})
        assert r.status_code == 400

    def test_missing_message(self, client):
        r = client.post("/api/notify/webhook", json={"instance": "alice"})
        assert r.status_code == 400
        assert "message" in r.json()["detail"]

    def test_empty_message(self, client):
        r = client.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": ""},
        )
        assert r.status_code == 400

    def test_invalid_priority(self, client):
        r = client.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test", "priority": "urgent"},
        )
        assert r.status_code == 400
        assert "priority" in r.json()["detail"]

    def test_invalid_json(self, client):
        r = client.post(
            "/api/notify/webhook",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400

    def test_unknown_instance(self, client):
        """Unbekannte Instanz -> 503 (Agent nicht verfuegbar)."""
        r = client.post(
            "/api/notify/webhook",
            json={"instance": "unknown", "message": "Test"},
        )
        assert r.status_code == 503


# ── Agent-Kommunikation ─────────────────────────────────────────────────────

class TestAgentCommunication:
    """Tests fuer die Agent-Chat-Kommunikation."""

    @patch("core.notify.httpx.AsyncClient")
    def test_agent_receives_notification(self, mock_client_cls, client):
        """Agent erhaelt die Nachricht mit Event-Kontext."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Die Waesche ist fertig!"}
        mock_response.raise_for_status = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client.post(
            "/api/notify/webhook",
            json={
                "instance": "alice",
                "message": "Waschmaschine ist fertig",
                "event": "washer_done",
                "channel": "whatsapp",
                "priority": "normal",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["instance"] == "alice"
        assert data["event"] == "washer_done"
        assert "agent_response" in data
        assert "delivery" in data

        # Pruefen dass Agent-POST aufgerufen wurde
        post_calls = [
            c for c in mock_client.post.call_args_list
            if "/chat" in str(c)
        ]
        assert len(post_calls) >= 1
        # Nachricht an Agent enthaelt Event-Info
        chat_payload = post_calls[0].kwargs.get("json", {})
        assert "washer_done" in chat_payload.get("message", "")

    @patch("core.notify.httpx.AsyncClient")
    def test_agent_timeout(self, mock_client_cls, client):
        """Agent-Timeout fuehrt zu 504."""
        import httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test"},
        )
        assert r.status_code == 504

    @patch("core.notify.httpx.AsyncClient")
    def test_default_values(self, mock_client_cls, client):
        """Defaults: channel=whatsapp, priority=normal, event=generic."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "OK"}
        mock_response.raise_for_status = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Hallo"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["event"] == "generic"


# ── WhatsApp-Zustellung ─────────────────────────────────────────────────────

class TestWhatsAppDelivery:
    """Tests fuer die WhatsApp-Nachrichtenzustellung."""

    @patch("core.notify.httpx.AsyncClient")
    def test_no_bridge_url(self, mock_client_cls, client_no_bridge):
        """Ohne Bridge-URL: Agent-Antwort kommt, aber Zustellung schlaegt fehl."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Test-Antwort"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client_no_bridge.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["delivery"]["sent"] is False
        assert "nicht konfiguriert" in data["delivery"]["error"]

    @patch("core.notify.httpx.AsyncClient")
    def test_no_user_jid(self, mock_client_cls, client_no_jid):
        """Ohne JID: Agent-Antwort kommt, aber WhatsApp-Zustellung schlaegt fehl."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Test-Antwort"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client_no_jid.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["delivery"]["sent"] is False
        assert "JID" in data["delivery"]["error"]

    @patch("core.notify.httpx.AsyncClient")
    def test_webchat_channel_no_bridge_needed(self, mock_client_cls, client):
        """Webchat-Channel braucht keine Bridge-Zustellung."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Antwort"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test", "channel": "webchat"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["delivery"]["channel"] == "webchat"
        assert data["delivery"]["sent"] is True


# ── Health-Endpoint ──────────────────────────────────────────────────────────

class TestNotifyHealth:
    """Tests fuer den Health-Endpoint."""

    @patch("core.notify.httpx.AsyncClient")
    def test_health_with_bridge(self, mock_client_cls, client):
        """Health zeigt Bridge-Status."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"status": "connected"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        r = client.get("/api/notify/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["whatsapp_bridge_configured"] is True
        assert data["whatsapp_bridge_connected"] is True

    def test_health_without_bridge(self, client_no_bridge):
        """Health ohne Bridge-URL."""
        r = client_no_bridge.get("/api/notify/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["whatsapp_bridge_configured"] is False
        assert data["whatsapp_bridge_connected"] is False


# ── Priorities ───────────────────────────────────────────────────────────────

class TestPriorities:
    """Tests fuer verschiedene Priority-Level."""

    def test_valid_priorities(self):
        """Alle gueltigen Priorities pruefen."""
        assert PRIORITIES == ("low", "normal", "high", "critical")

    @patch("core.notify.httpx.AsyncClient")
    def test_all_priorities_accepted(self, mock_client_cls, client):
        """Alle gueltigen Priorities werden akzeptiert."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "OK"}
        mock_response.raise_for_status = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        for p in PRIORITIES:
            r = client.post(
                "/api/notify/webhook",
                json={"instance": "alice", "message": "Test", "priority": p},
            )
            assert r.status_code == 200, f"Priority '{p}' wurde nicht akzeptiert"


# ── JID-Normalisierung ──────────────────────────────────────────────────────

class TestJidNormalization:
    """Tests fuer JID-Normalisierung bei WhatsApp-Zustellung."""

    @patch("core.notify.httpx.AsyncClient")
    def test_jid_without_suffix_gets_normalized(self, mock_client_cls):
        """JID ohne @s.whatsapp.net bekommt Suffix hinzugefuegt."""
        app = _make_app(user_jid="491234567890")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "OK"}
        mock_response.raise_for_status = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        tc = TestClient(app)
        r = tc.post(
            "/api/notify/webhook",
            json={"instance": "alice", "message": "Test"},
        )
        assert r.status_code == 200

        # Pruefen dass der /send Call die normalisierte JID benutzt
        send_calls = [
            c for c in mock_client.post.call_args_list
            if "/send" in str(c)
        ]
        if send_calls:
            payload = send_calls[0].kwargs.get("json", {})
            assert payload.get("jid", "").endswith("@s.whatsapp.net")
