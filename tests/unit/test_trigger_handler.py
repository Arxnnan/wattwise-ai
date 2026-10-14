"""Unit tests — local trigger handler (email alerting), mocked SMTP."""
from __future__ import annotations
from datetime import datetime, timezone
from email import message_from_string

import pytest

from triggers.handler import TriggerHandler, EnergyEvent


def _sent_body_text(mock_server) -> str:
    """Extract the decoded plain + html body text from the sendmail call.

    The handler sends a multipart alternative (plain + HTML); each part is
    utf-8 and gets base64-encoded by Python's email module. We decode both
    parts and concatenate so substring assertions work regardless of encoding.
    """
    raw = mock_server.sendmail.call_args[0][2]
    msg = message_from_string(raw)
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload is not None:
                    parts.append(payload.decode("utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            parts.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(parts)


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


@pytest.fixture
def mock_smtp(mocker):
    mock_server = mocker.MagicMock()
    mock_cm = mocker.MagicMock()
    mock_cm.__enter__.return_value = mock_server
    mock_cm.__exit__.return_value = False
    return mocker.patch("triggers.handler.smtplib.SMTP", return_value=mock_cm), mock_server


class TestFire:

    def test_success_sends_email_and_records_event(self, mock_smtp):
        _, mock_server = mock_smtp
        handler = TriggerHandler()
        event = _event()

        result = handler.fire(event)

        assert result is True
        mock_server.sendmail.assert_called_once()
        assert handler.events_fired == [event]

    def test_smtp_failure_returns_false_but_still_records_event(self, mocker):
        mocker.patch("triggers.handler.smtplib.SMTP", side_effect=OSError("connection refused"))
        handler = TriggerHandler()
        event = _event()

        result = handler.fire(event)

        assert result is False
        assert handler.events_fired == [event]

    def test_sendmail_exception_is_caught(self, mock_smtp):
        _, mock_server = mock_smtp
        mock_server.sendmail.side_effect = Exception("smtp rejected")
        handler = TriggerHandler()

        result = handler.fire(_event())

        assert result is False

    def test_email_includes_narrative_when_present(self, mock_smtp):
        _, mock_server = mock_smtp
        handler = TriggerHandler()
        handler.fire(_event(narrative="Chiller drawing 3x nameplate load."))

        body = _sent_body_text(mock_server)
        assert "Chiller drawing 3x nameplate load." in body

    def test_email_placeholder_when_narrative_missing(self, mock_smtp):
        _, mock_server = mock_smtp
        handler = TriggerHandler()
        handler.fire(_event(narrative=""))

        body = _sent_body_text(mock_server)
        assert "No narrative generated yet." in body

    def test_multiple_events_accumulate(self, mock_smtp):
        handler = TriggerHandler()
        handler.fire(_event())
        handler.fire(_event())
        assert len(handler.events_fired) == 2
