"""Extra unit tests — triggers/dispatch.py + triggers/handler.py.

Targets the branches not covered by test_dispatch.py / test_trigger_handler.py:
- ACS / Twilio import-missing and generic-exception fallbacks (dispatch._try_* helpers).
- SMTP auth, STARTTLS, SSL (port 465), and TLS-mode env fallbacks.
- Multi-recipient parsing: list input, comma-separated string input, env-var input.
- Login called only when SMTP_USER is set.
- Graceful failure on SMTP errors in each TLS mode.
All SMTP, HTTP and Twilio calls are mocked — no real network I/O.
"""
from __future__ import annotations

import builtins
import sys
from datetime import datetime, timezone

import pytest

from triggers import dispatch
from triggers.handler import EnergyEvent, TriggerHandler


# -------------------- helpers --------------------


def _event(narrative: str = "") -> EnergyEvent:
    return EnergyEvent(
        event_type="anomaly",
        facility_id="office",
        device_id="off-main-01",
        timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        observed_value=120.0,
        expected_value=40.0,
        anomaly_score=0.93,
        narrative=narrative,
    )


def _ctx(mocker):
    """Return (patched-class-mock, server-mock) — class acts as context manager."""
    server = mocker.MagicMock()
    cm = mocker.MagicMock()
    cm.__enter__.return_value = server
    cm.__exit__.return_value = False
    return cm, server


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Scrub env vars that the modules under test consult so each test is isolated."""
    for var in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS",
        "ACS_SENDER", "ALERT_RECIPIENTS",
        "ACS_CONNECTION_STRING", "ACS_SENDER_EMAIL",
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "TWILIO_TO_NUMBER",
    ):
        monkeypatch.delenv(var, raising=False)


# ============================================================
# dispatch._try_acs_client — import + exception branches
# ============================================================


class TestTryAcsClientBranches:

    def test_import_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://f.communication.azure.com/;accesskey=k")
        # Make azure.communication.email import raise ImportError
        monkeypatch.setitem(sys.modules, "azure.communication.email", None)
        assert dispatch._try_acs_client() is None

    def test_generic_exception_returns_none(self, monkeypatch, mocker):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "bogus-but-truthy")

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "azure.communication.email":
                class _Boom:
                    @staticmethod
                    def from_connection_string(_):
                        raise RuntimeError("bad conn str")
                mod = type(sys)("azure.communication.email")
                mod.EmailClient = _Boom
                return mod
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert dispatch._try_acs_client() is None

    def test_success_builds_client(self, monkeypatch):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://f.communication.azure.com/;accesskey=k")

        real_import = builtins.__import__
        sentinel_client = object()

        def fake_import(name, *args, **kwargs):
            if name == "azure.communication.email":
                mod = type(sys)("azure.communication.email")

                class _EC:
                    @staticmethod
                    def from_connection_string(_):
                        return sentinel_client

                mod.EmailClient = _EC
                return mod
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert dispatch._try_acs_client() is sentinel_client


# ============================================================
# dispatch._try_twilio_client — import + exception branches
# ============================================================


class TestTryTwilioClientBranches:

    def test_import_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        monkeypatch.setitem(sys.modules, "twilio.rest", None)
        assert dispatch._try_twilio_client() is None

    def test_generic_exception_returns_none(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "twilio.rest":
                mod = type(sys)("twilio.rest")

                def _ctor(sid, token):
                    raise RuntimeError("auth is wrong")

                mod.Client = _ctor
                return mod
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert dispatch._try_twilio_client() is None

    def test_success_builds_client(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")

        real_import = builtins.__import__
        sentinel = object()

        def fake_import(name, *args, **kwargs):
            if name == "twilio.rest":
                mod = type(sys)("twilio.rest")

                def _ctor(sid, token):
                    assert (sid, token) == ("sid", "tok")
                    return sentinel

                mod.Client = _ctor
                return mod
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert dispatch._try_twilio_client() is sentinel


# ============================================================
# dispatch.send_alert_sms — env-based destination number
# ============================================================


class TestSmsEnvDestination:

    def test_uses_env_to_number_when_arg_omitted(self, monkeypatch, mocker):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")
        monkeypatch.setenv("TWILIO_TO_NUMBER", "+15559999999")

        mock_client = mocker.MagicMock()
        mock_client.messages.create.return_value = mocker.MagicMock(sid="SMenv")
        mocker.patch("triggers.dispatch._try_twilio_client", return_value=mock_client)

        result = dispatch.send_alert_sms("hello")
        assert result == {"channel": "twilio", "sent": True, "message_sid": "SMenv"}
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["to"] == "+15559999999"
        assert kwargs["from_"] == "+15550000000"

    def test_sms_body_is_truncated_to_1600_chars(self, monkeypatch, mocker):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")

        mock_client = mocker.MagicMock()
        mock_client.messages.create.return_value = mocker.MagicMock(sid="SMlong")
        mocker.patch("triggers.dispatch._try_twilio_client", return_value=mock_client)

        long_body = "x" * 5000
        dispatch.send_alert_sms(long_body, "+15551111111")
        assert len(mock_client.messages.create.call_args.kwargs["body"]) == 1600


# ============================================================
# dispatch.send_alert_email — uses ACS_SENDER_EMAIL env override
# ============================================================


class TestAcsSenderEnv:

    def test_sender_env_override_passed_to_client(self, monkeypatch, mocker):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "x")
        monkeypatch.setenv("ACS_SENDER_EMAIL", "custom@sender.net")

        poller = mocker.MagicMock()
        poller.result.return_value = {"id": "id-env"}
        client = mocker.MagicMock()
        client.begin_send.return_value = poller
        mocker.patch("triggers.dispatch._try_acs_client", return_value=client)

        result = dispatch.send_alert_email("s", "b", "to@x.io")
        assert result["sent"] is True
        message = client.begin_send.call_args.args[0]
        assert message["senderAddress"] == "custom@sender.net"
        assert message["recipients"] == {"to": [{"address": "to@x.io"}]}

    def test_result_without_id_still_returns_dict(self, monkeypatch, mocker):
        monkeypatch.setenv("ACS_CONNECTION_STRING", "x")
        poller = mocker.MagicMock()
        poller.result.return_value = {}  # no 'id' key
        client = mocker.MagicMock()
        client.begin_send.return_value = poller
        mocker.patch("triggers.dispatch._try_acs_client", return_value=client)

        result = dispatch.send_alert_email("s", "b", "to@x.io")
        assert result == {"channel": "acs", "sent": True, "message_id": None}


# ============================================================
# handler.TriggerHandler __init__ — env-var fallbacks & recipients
# ============================================================


class TestHandlerInit:

    def test_smtp_user_and_password_from_env(self, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "  user@gmail.com  ")  # whitespace trimmed
        monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")  # spaces stripped
        monkeypatch.setenv("SMTP_USE_TLS", "STARTTLS")  # lowercased

        h = TriggerHandler()
        assert h.smtp_user == "user@gmail.com"
        assert h.smtp_password == "abcdefghijklmnop"
        assert h.smtp_use_tls == "starttls"

    def test_sender_defaults_to_smtp_user_when_no_explicit_or_acs(self, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "me@site.io")
        h = TriggerHandler()
        assert h.sender == "me@site.io"

    def test_sender_falls_through_to_wattwise_local(self):
        h = TriggerHandler()
        assert h.sender == "wattwise@local.dev"

    def test_sender_env_acs_sender_takes_precedence_over_user(self, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "user@site.io")
        monkeypatch.setenv("ACS_SENDER", "alerts@wattwise.io")
        h = TriggerHandler()
        assert h.sender == "alerts@wattwise.io"

    def test_recipients_from_list_arg(self):
        h = TriggerHandler(recipient=[" a@x.io ", "b@x.io", ""])  # trim + drop empties
        assert h.recipients == ["a@x.io", "b@x.io"]
        assert h.recipient == "a@x.io"

    def test_recipients_from_comma_separated_string(self):
        h = TriggerHandler(recipient="a@x.io, b@x.io ,c@x.io")
        assert h.recipients == ["a@x.io", "b@x.io", "c@x.io"]
        assert h.recipient == "a@x.io"

    def test_recipients_from_env_alert_recipients(self, monkeypatch):
        monkeypatch.setenv("ALERT_RECIPIENTS", "ops1@x.io, ops2@x.io")
        h = TriggerHandler()
        assert h.recipients == ["ops1@x.io", "ops2@x.io"]

    def test_recipients_default_when_nothing_set(self):
        h = TriggerHandler()
        assert h.recipients == ["ops@local.dev"]

    def test_smtp_host_and_port_from_env(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        monkeypatch.setenv("SMTP_PORT", "2525")
        h = TriggerHandler()
        assert h.smtp_host == "mail.example.com"
        assert h.smtp_port == 2525

    def test_explicit_args_override_env(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "env-host")
        monkeypatch.setenv("SMTP_PORT", "9999")
        h = TriggerHandler(smtp_host="arg-host", smtp_port=4242, sender="s@x.io")
        assert h.smtp_host == "arg-host"
        assert h.smtp_port == 4242
        assert h.sender == "s@x.io"


# ============================================================
# handler._send_email — TLS modes
# ============================================================


class TestSendEmailTlsModes:

    def test_ssl_mode_uses_smtp_ssl_and_login(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "user@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        cm, server = _ctx(mocker)
        ssl_cls = mocker.patch("triggers.handler.smtplib.SMTP_SSL", return_value=cm)
        plain_cls = mocker.patch("triggers.handler.smtplib.SMTP")

        h = TriggerHandler(smtp_host="smtp.gmail.com", smtp_port=465)
        assert h.fire(_event()) is True
        ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        plain_cls.assert_not_called()
        server.login.assert_called_once_with("user@gmail.com", "pw")
        server.sendmail.assert_called_once()
        server.starttls.assert_not_called()

    def test_ssl_mode_without_user_skips_login(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "ssl")
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP_SSL", return_value=cm)
        mocker.patch("triggers.handler.smtplib.SMTP")

        h = TriggerHandler(smtp_host="smtp.gmail.com", smtp_port=465)
        assert h.fire(_event()) is True
        server.login.assert_not_called()
        server.sendmail.assert_called_once()

    def test_starttls_mode_via_auto_and_user(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "user@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        cm, server = _ctx(mocker)
        plain_cls = mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)
        ssl_cls = mocker.patch("triggers.handler.smtplib.SMTP_SSL")

        # Default port 1025 + user set -> auto -> starttls
        h = TriggerHandler()
        assert h.fire(_event()) is True
        plain_cls.assert_called_once_with("localhost", 1025, timeout=15)
        ssl_cls.assert_not_called()
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user@gmail.com", "pw")

    def test_starttls_mode_explicit(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "starttls")
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler()  # no user
        assert h.fire(_event()) is True
        server.starttls.assert_called_once()
        server.login.assert_not_called()  # no user set

    def test_none_mode_no_starttls_no_login(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "none")
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler()
        assert h.fire(_event()) is True
        server.starttls.assert_not_called()
        server.login.assert_not_called()

    def test_auto_without_user_resolves_to_none(self, mocker):
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler()  # default auto, no SMTP_USER
        assert h.fire(_event()) is True
        server.starttls.assert_not_called()
        server.login.assert_not_called()

    def test_login_only_when_smtp_user_set(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "starttls")
        monkeypatch.setenv("SMTP_USER", "user@site.io")
        monkeypatch.setenv("SMTP_PASSWORD", "pass123")
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler()
        assert h.fire(_event()) is True
        server.login.assert_called_once_with("user@site.io", "pass123")

    def test_ssl_mode_graceful_failure(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "ssl")
        mocker.patch("triggers.handler.smtplib.SMTP_SSL",
                     side_effect=OSError("tls handshake failed"))

        h = TriggerHandler(smtp_host="smtp.gmail.com", smtp_port=465)
        assert h.fire(_event()) is False
        assert len(h.events_fired) == 1  # still recorded

    def test_starttls_handshake_failure_graceful(self, mocker, monkeypatch):
        monkeypatch.setenv("SMTP_USE_TLS", "starttls")
        cm, server = _ctx(mocker)
        server.starttls.side_effect = Exception("starttls refused")
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler()
        assert h.fire(_event()) is False

    def test_multi_recipient_sendmail_includes_all(self, mocker):
        cm, server = _ctx(mocker)
        mocker.patch("triggers.handler.smtplib.SMTP", return_value=cm)

        h = TriggerHandler(recipient=["a@x.io", "b@x.io", "c@x.io"])
        assert h.fire(_event()) is True
        args = server.sendmail.call_args.args
        # sendmail(sender, recipients, body)
        assert args[1] == ["a@x.io", "b@x.io", "c@x.io"]
        # 'To' header is comma-joined
        assert "a@x.io, b@x.io, c@x.io" in args[2]
