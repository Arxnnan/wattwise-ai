"""WattWise AI — local trigger handler.

Listens for anomaly/peak events and dispatches:
- Email alert via MailHog (local SMTP on port 1025)
- Console/log output
- (In Phase 2: Azure Functions + ACS)
"""
from __future__ import annotations
import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Literal

log = logging.getLogger(__name__)

EventType = Literal["anomaly", "peak_warning", "optimization"]


@dataclass
class EnergyEvent:
    event_type: EventType
    facility_id: str
    device_id: str
    timestamp: datetime
    observed_value: float
    expected_value: float
    anomaly_score: float
    narrative: str = ""


class TriggerHandler:
    """Dispatches alerts when AI detects anomalies or peak warnings."""

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 1025,
        sender: str = "wattwise@local.dev",
        recipient: str = "ops@local.dev",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.recipient = recipient
        self._events_fired: list[EnergyEvent] = []

    def fire(self, event: EnergyEvent) -> bool:
        """Process an energy event — log and send email alert."""
        log.warning(
            "[%s] %s | facility=%s device=%s | observed=%.2f expected=%.2f score=%.3f",
            event.event_type.upper(),
            event.timestamp.isoformat(),
            event.facility_id,
            event.device_id,
            event.observed_value,
            event.expected_value,
            event.anomaly_score,
        )
        self._events_fired.append(event)
        return self._send_email(event)

    def _send_email(self, event: EnergyEvent) -> bool:
        subject = (
            f"[WattWise AI] {event.event_type.upper()} detected — "
            f"{event.facility_id} / {event.device_id}"
        )
        body = f"""WattWise AI Alert
==================
Type:      {event.event_type.upper()}
Facility:  {event.facility_id}
Device:    {event.device_id}
Time:      {event.timestamp.isoformat()}
Observed:  {event.observed_value:.3f} kW
Expected:  {event.expected_value:.3f} kW
Score:     {event.anomaly_score:.4f}

AI Narrative:
{event.narrative or "No narrative generated yet."}

View dashboard: http://localhost:3001
"""
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5) as server:
                server.sendmail(self.sender, [self.recipient], msg.as_string())
            log.info("Alert email sent to %s", self.recipient)
            return True
        except Exception as e:
            log.warning("Email send failed (is MailHog running?): %s", e)
            return False

    @property
    def events_fired(self) -> list[EnergyEvent]:
        return self._events_fired
