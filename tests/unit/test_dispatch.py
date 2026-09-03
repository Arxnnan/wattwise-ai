"""Unit tests — triggers/dispatch.py (Azure Functions cloud alert path)."""
from __future__ import annotations
import pytest

from triggers.dispatch import send_alert_email, send_alert_sms, dispatch_bms_command


class TestSendAlertEmail:

    def test_falls_back_to_log_when_acs_not_configured(self, monkeypatch):
        monkeypatch.delenv("ACS_CONNECTION_STRING", raising=False)
        result = send_alert_email("subject", "body", "ops@example.com")
        assert result == {
            "channel": "log_only", "sent": False, "reason": "ACS_CONNECTION_STRING not set",
        }

    def test_uses_acs_when_configured(self, monkeypatch, mocker):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://fake.communication.azure.com/;accesskey=fake")
        mock_client = mocker.MagicMock()
        mock_poller = mocker.MagicMock()
        mock_poller.result.return_value = {"id": "msg-123"}
        mock_client.begin_send.return_value = mock_poller
        mocker.patch("triggers.dispatch._try_acs_client", return_value=mock_client)

        result = send_alert_email("subject", "body", "ops@example.com")

        assert result == {"channel": "acs", "sent": True, "message_id": "msg-123"}
        mock_client.begin_send.assert_called_once()

    def test_acs_send_failure_is_reported_not_raised(self, monkeypatch, mocker):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://fake.communication.azure.com/;accesskey=fake")
        mock_client = mocker.MagicMock()
        mock_client.begin_send.side_effect = Exception("ACS quota exceeded")
        mocker.patch("triggers.dispatch._try_acs_client", return_value=mock_client)

        result = send_alert_email("subject", "body", "ops@example.com")

        assert result["sent"] is False
        assert result["channel"] == "acs"
        assert "ACS quota exceeded" in result["reason"]

    def test_try_acs_client_returns_none_without_connection_string(self, monkeypatch):
        from triggers.dispatch import _try_acs_client
        monkeypatch.delenv("ACS_CONNECTION_STRING", raising=False)
        assert _try_acs_client() is None


class TestSendAlertSms:

    def test_falls_back_to_log_when_twilio_not_configured(self, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        result = send_alert_sms("body text", "+15551234567")
        assert result == {
            "channel": "log_only", "sent": False,
            "reason": "TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN not set",
        }

    def test_falls_back_when_no_destination_number(self, monkeypatch, mocker):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "fake_sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake_token")
        monkeypatch.delenv("TWILIO_TO_NUMBER", raising=False)
        mocker.patch("triggers.dispatch._try_twilio_client", return_value=mocker.MagicMock())

        result = send_alert_sms("body text", to_number=None)

        assert result["sent"] is False
        assert result["reason"] == "no destination number"

    def test_uses_twilio_when_configured(self, monkeypatch, mocker):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "fake_sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake_token")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550001111")
        mock_client = mocker.MagicMock()
        mock_message = mocker.MagicMock(sid="SM123")
        mock_client.messages.create.return_value = mock_message
        mocker.patch("triggers.dispatch._try_twilio_client", return_value=mock_client)

        result = send_alert_sms("body text", "+15551234567")

        assert result == {"channel": "twilio", "sent": True, "message_sid": "SM123"}
        mock_client.messages.create.assert_called_once()

    def test_twilio_send_failure_is_reported_not_raised(self, monkeypatch, mocker):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "fake_sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake_token")
        mock_client = mocker.MagicMock()
        mock_client.messages.create.side_effect = Exception("Twilio rejected number")
        mocker.patch("triggers.dispatch._try_twilio_client", return_value=mock_client)

        result = send_alert_sms("body text", "+15551234567")

        assert result["sent"] is False
        assert result["channel"] == "twilio"
        assert "Twilio rejected number" in result["reason"]

    def test_try_twilio_client_returns_none_without_credentials(self, monkeypatch):
        from triggers.dispatch import _try_twilio_client
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        assert _try_twilio_client() is None


class TestDispatchBmsCommand:

    def test_returns_logged_status(self):
        result = dispatch_bms_command("office", "off-hvac-01", "shed_load_15min")
        assert result == {
            "facility_id": "office",
            "device_id": "off-hvac-01",
            "action": "shed_load_15min",
            "status": "logged",
        }
