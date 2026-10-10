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
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        sender: str | None = None,
        recipient: str | list[str] | None = None,
    ):
        # Fall back to env vars so Alert Settings in the UI feeds through
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST") or "localhost"
        self.smtp_port = int(smtp_port if smtp_port is not None else os.getenv("SMTP_PORT", "1025"))
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")  # Gmail app pwds show with spaces
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "auto").lower()
        self.sender = sender or os.getenv("ACS_SENDER") or self.smtp_user or "wattwise@local.dev"

        # Multi-recipient support — accept list, comma-separated string, or env var
        if isinstance(recipient, list):
            self.recipients = [r.strip() for r in recipient if r.strip()]
        elif isinstance(recipient, str):
            self.recipients = [r.strip() for r in recipient.split(",") if r.strip()]
        else:
            _env = os.getenv("ALERT_RECIPIENTS", "").strip()
            self.recipients = [r.strip() for r in _env.split(",") if r.strip()] or ["ops@local.dev"]
        # Legacy single-recipient attribute (first in list) kept for backward compat
        self.recipient = self.recipients[0]
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
        msg["To"] = ", ".join(self.recipients)

        # Auto-detect whether to use TLS: if port 465 use SMTPS, else STARTTLS when creds supplied
        use_tls = self.smtp_use_tls
        if use_tls == "auto":
            use_tls = "ssl" if self.smtp_port == 465 else ("starttls" if self.smtp_user else "none")

        try:
            if use_tls == "ssl":
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.sender, self.recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if use_tls == "starttls":
                        server.starttls()
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.sender, self.recipients, msg.as_string())
            log.info("Alert email sent to %d recipient(s) via %s", len(self.recipients), self.smtp_host)
            return True
        except Exception as e:
            log.warning("Email send failed: %s", e)
            return False

    @property
    def events_fired(self) -> list[EnergyEvent]:
        return self._events_fired
