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
from email.mime.multipart import MIMEMultipart
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

    def send_mail(
        self,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        recipients: list[str] | None = None,
    ) -> bool:
        """Send an email with a plain-text body and optional HTML alternative.

        Shared transport used by both auto-fired alerts and human-approved
        decision notifications. Returns True on success, False on any failure.
        """
        to = recipients or self.recipients
        if not to:
            log.warning("send_mail skipped: no recipients configured")
            return False

        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        else:
            msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(to)

        use_tls = self.smtp_use_tls
        if use_tls == "auto":
            use_tls = "ssl" if self.smtp_port == 465 else ("starttls" if self.smtp_user else "none")

        try:
            if use_tls == "ssl":
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.sender, to, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if use_tls == "starttls":
                        server.starttls()
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.sender, to, msg.as_string())
            log.info("Email sent to %d recipient(s) via %s", len(to), self.smtp_host)
            return True
        except Exception as e:
            log.warning("Email send failed via %s:%s — %s", self.smtp_host, self.smtp_port, e)
            return False

    def _send_email(self, event: EnergyEvent) -> bool:
        type_label = event.event_type.replace("_", " ").title()
        subject = f"[WattWise AI] {type_label} — {event.facility_id} / {event.device_id}"

        explanation = _event_explanation(event)
        delta = event.observed_value - event.expected_value
        delta_pct = (delta / event.expected_value * 100) if event.expected_value else 0.0

        text = f"""WattWise AI — {type_label} detected

What this is
    {explanation}

Where
    Facility : {event.facility_id}
    Device   : {event.device_id}
    Time     : {event.timestamp.isoformat()}

Readings
    Observed : {event.observed_value:.3f} kW
    Expected : {event.expected_value:.3f} kW
    Delta    : {delta:+.3f} kW  ({delta_pct:+.1f}%)
    Score    : {event.anomaly_score:.4f}  (0 = normal, 1 = extreme)

AI narrative
    {event.narrative or "No narrative generated yet."}

View the live dashboard: http://localhost:3001
"""
        html = _render_alert_html(event, type_label, explanation, delta, delta_pct)
        return self.send_mail(subject, text, html)

    @property
    def events_fired(self) -> list[EnergyEvent]:
        return self._events_fired


# ---------------------------------------------------------------- Email HTML --

def _event_explanation(event: EnergyEvent) -> str:
    """One-sentence, demo-friendly explanation of what triggered the alert."""
    kind = event.event_type.lower()
    if kind == "peak_warning":
        return (
            "Demand on this facility is climbing above the configured peak threshold. "
            "If sustained for the metering interval, it will set a new peak-demand charge "
            "on this month's bill. Ops should shed deferrable loads now."
        )
    if kind == "anomaly":
        return (
            "The device's live reading deviates significantly from the forecast "
            "produced by the LSTM auto-encoder. This usually signals equipment drift, "
            "a stuck setpoint, or an unexpected load — worth a quick technician check."
        )
    if kind == "optimization":
        return (
            "The optimizer found a shift / shed opportunity that materially reduces cost "
            "without impacting comfort or SLA. Review and approve to dispatch."
        )
    return "A WattWise AI agent raised this event. See readings and narrative below."


def _render_alert_html(
    event: EnergyEvent, type_label: str, explanation: str, delta: float, delta_pct: float
) -> str:
    """Render an ascetic, dark-mode-safe HTML alert email."""
    narrative = (event.narrative or "No narrative generated yet.").replace("\n", "<br>")
    delta_color = "#D6DF27" if delta <= 0 else "#E57373"
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#0a1515;font-family:Georgia,'Times New Roman',serif;color:#e8f0f0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a1515;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="width:560px;max-width:92%;background:#101e1e;border:1px solid #152626;border-radius:4px;">

        <tr><td style="padding:28px 36px 18px 36px;border-bottom:1px solid #152626;">
          <div style="font-size:11px;letter-spacing:2.4px;color:#28B3B4;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;">— WattWise AI</div>
          <div style="font-size:24px;color:#e8f0f0;margin-top:6px;font-weight:300;letter-spacing:-0.5px;">{type_label} <em style="color:#D6DF27;">detected</em></div>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:8px;">What this is</div>
          <div style="font-size:14px;line-height:1.65;color:#cfd9d9;">{explanation}</div>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:10px;">Where</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:13px;color:#e8f0f0;">
            <tr><td style="padding:4px 0;color:#6b8484;width:110px;">Facility</td><td style="padding:4px 0;">{event.facility_id}</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Device</td><td style="padding:4px 0;">{event.device_id}</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Time (UTC)</td><td style="padding:4px 0;">{event.timestamp.isoformat()}</td></tr>
          </table>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:10px;">Readings</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:13px;color:#e8f0f0;">
            <tr><td style="padding:4px 0;color:#6b8484;width:110px;">Observed</td><td style="padding:4px 0;" align="right">{event.observed_value:.3f} kW</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Expected</td><td style="padding:4px 0;" align="right">{event.expected_value:.3f} kW</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Delta</td><td style="padding:4px 0;color:{delta_color};" align="right">{delta:+.3f} kW&nbsp;&nbsp;({delta_pct:+.1f}%)</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Score</td><td style="padding:4px 0;" align="right">{event.anomaly_score:.4f}&nbsp;&nbsp;<span style="color:#6b8484;">(0 normal · 1 extreme)</span></td></tr>
          </table>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:8px;">AI narrative</div>
          <div style="font-size:14px;line-height:1.65;color:#cfd9d9;font-style:italic;">{narrative}</div>
        </td></tr>

        <tr><td style="padding:28px 36px 32px 36px;">
          <a href="http://localhost:3001" style="display:inline-block;background:#28B3B4;color:#0a1515;text-decoration:none;padding:12px 22px;font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:2.5px;text-transform:uppercase;border-radius:2px;font-weight:600;">Open dashboard</a>
        </td></tr>

        <tr><td style="padding:18px 36px 22px 36px;border-top:1px solid #152626;">
          <div style="font-size:10px;letter-spacing:2px;color:#6b8484;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;">
            WattWise AI · Delivered by <span style="color:#28B3B4;">Psiog</span>
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""


def render_decision_html(suggestion, decision, payload: dict) -> str:
    """HTML body for a human-approved decision notification.

    Takes AIsuggestion / HumanDecision duck-typed; defined here so action_handler
    doesn't have to carry email templating.
    """
    import json as _json

    outcome = decision.outcome.upper()
    outcome_color = {"APPROVED": "#D6DF27", "MODIFIED": "#28B3B4"}.get(outcome, "#9ab0b0")
    rationale = (suggestion.rationale or "").replace("\n", "<br>")
    payload_json = _json.dumps(payload, indent=2, default=str)
    action_label = suggestion.action_type.replace("_", " ").title()

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#0a1515;font-family:Georgia,'Times New Roman',serif;color:#e8f0f0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a1515;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="width:560px;max-width:92%;background:#101e1e;border:1px solid #152626;border-radius:4px;">

        <tr><td style="padding:28px 36px 18px 36px;border-bottom:1px solid #152626;">
          <div style="font-size:11px;letter-spacing:2.4px;color:#28B3B4;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;">— WattWise AI · Human-in-the-loop</div>
          <div style="font-size:24px;color:#e8f0f0;margin-top:6px;font-weight:300;letter-spacing:-0.5px;">Decision <em style="color:{outcome_color};">{outcome.lower()}</em></div>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:8px;">What was approved</div>
          <div style="font-size:16px;line-height:1.4;color:#e8f0f0;font-weight:400;">{suggestion.title}</div>
          <div style="font-size:12px;color:#6b8484;margin-top:6px;font-family:Helvetica,Arial,sans-serif;letter-spacing:0.3px;">
            {suggestion.agent_name} · {suggestion.category} · action: {action_label}
          </div>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:10px;">Decision metadata</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:13px;color:#e8f0f0;">
            <tr><td style="padding:4px 0;color:#6b8484;width:140px;">By</td><td style="padding:4px 0;">{decision.user}</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Decided at (UTC)</td><td style="padding:4px 0;">{decision.decided_at.isoformat()}</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Confidence</td><td style="padding:4px 0;">{suggestion.confidence:.0%}</td></tr>
            <tr><td style="padding:4px 0;color:#6b8484;">Impact</td><td style="padding:4px 0;color:#D6DF27;">INR {suggestion.impact_inr_month:,.0f} / month</td></tr>
          </table>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:8px;">Why the AI suggested this</div>
          <div style="font-size:14px;line-height:1.65;color:#cfd9d9;font-style:italic;">{rationale}</div>
        </td></tr>

        <tr><td style="padding:22px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:2px;color:#9ab0b0;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;margin-bottom:8px;">Dispatched payload</div>
          <pre style="margin:0;padding:14px 16px;background:#0a1515;border:1px solid #152626;border-radius:3px;font-family:'JetBrains Mono',Consolas,monospace;font-size:12px;color:#9ab0b0;line-height:1.5;overflow-x:auto;white-space:pre-wrap;">{payload_json}</pre>
        </td></tr>

        <tr><td style="padding:28px 36px 32px 36px;">
          <a href="http://localhost:3001" style="display:inline-block;background:#28B3B4;color:#0a1515;text-decoration:none;padding:12px 22px;font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:2.5px;text-transform:uppercase;border-radius:2px;font-weight:600;">Open audit log</a>
        </td></tr>

        <tr><td style="padding:18px 36px 22px 36px;border-top:1px solid #152626;">
          <div style="font-size:10px;letter-spacing:2px;color:#6b8484;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;">
            WattWise AI · Delivered by <span style="color:#28B3B4;">Psiog</span>
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""
