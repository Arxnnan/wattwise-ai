"""Tests for the upgraded triggers/dispatch.py:dispatch_bms_command — real HTTP path."""
from unittest.mock import patch, MagicMock

import pytest

from triggers.dispatch import dispatch_bms_command


@pytest.fixture
def _clear_env(monkeypatch):
    monkeypatch.delenv("BMS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("BMS_AUTH_TOKEN", raising=False)


class TestDispatchBMSFallback:
    def test_no_url_logs_and_returns_logged_status(self, _clear_env):
        """Without BMS_WEBHOOK_URL, legacy stub path returns 'logged'."""
        r = dispatch_bms_command("office", "HVAC-A", "shed")
        assert r["status"] == "logged"
        assert r["facility_id"] == "office"
        assert r["device_id"] == "HVAC-A"
        assert r["action"] == "shed"
        assert "endpoint" not in r

    def test_empty_url_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "   ")  # whitespace only
        r = dispatch_bms_command("office", "HVAC-A", "shed")
        assert r["status"] == "logged"


class TestDispatchBMSHTTP:
    def test_url_set_fires_post_and_returns_ack(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://localhost:9100/command")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"accepted": True, "ref": "ok-123"}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            r = dispatch_bms_command("warehouse", "comp-2", "shed",
                                     loads=["HVAC-A"], shed_kw=42.5, action_type="shed_load")
        assert r["status"] == "sent"
        assert r["http_status"] == 200
        assert r["endpoint"] == "http://localhost:9100/command"
        assert r["ack"] == {"accepted": True, "ref": "ok-123"}
        # verify payload contains the extras we passed
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:9100/command"
        payload = kwargs["json"]
        assert payload["facility"] == "warehouse"
        assert payload["loads"] == ["HVAC-A"]
        assert payload["shed_kw"] == 42.5
        assert payload["action_type"] == "shed_load"

    def test_auth_token_added_as_bearer_header(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://bms/api/cmd")
        monkeypatch.setenv("BMS_AUTH_TOKEN", "secret123")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            dispatch_bms_command("office", "x", "shed")
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer secret123"

    def test_no_token_no_auth_header(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://bms/api/cmd")
        monkeypatch.delenv("BMS_AUTH_TOKEN", raising=False)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            dispatch_bms_command("office", "x", "shed")
        _, kwargs = mock_post.call_args
        assert "Authorization" not in kwargs["headers"]

    def test_non_json_response_still_returns_sent(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://bms/api/cmd")
        mock_resp = MagicMock(status_code=200, text="OK plaintext")
        mock_resp.json.side_effect = ValueError("not json")
        with patch("requests.post", return_value=mock_resp):
            r = dispatch_bms_command("office", "x", "shed")
        assert r["status"] == "sent"
        assert r["ack"] == {"ack": "OK plaintext"}

    def test_http_4xx_returns_http_error(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://bms/api/cmd")
        mock_resp = MagicMock(status_code=404)
        with patch("requests.post", return_value=mock_resp):
            r = dispatch_bms_command("office", "x", "shed")
        assert r["status"] == "http_error"
        assert r["http_status"] == 404

    def test_connection_exception_returns_failed_status(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://nonexistent/cmd")
        with patch("requests.post", side_effect=ConnectionError("network down")):
            r = dispatch_bms_command("office", "x", "shed")
        assert r["status"] == "failed"
        assert "network down" in r["error"]
        assert r["endpoint"] == "http://nonexistent/cmd"

    def test_timeout_exception_returns_failed(self, monkeypatch):
        monkeypatch.setenv("BMS_WEBHOOK_URL", "http://slow/cmd")
        with patch("requests.post", side_effect=TimeoutError("read timeout")):
            r = dispatch_bms_command("office", "x", "shed")
        assert r["status"] == "failed"
        assert "timeout" in r["error"].lower()
