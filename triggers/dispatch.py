"""WattWise AI — cloud alert dispatch (ACS email + Twilio SMS).

Separate from `handler.py`'s local Mailpit/SMTP path (used by the Podman dev
stack). This is what runs when deployed to the Azure Functions app.

Neither channel has real credentials behind it yet:
- ACS is provisioned-but-blocked (`AuthorizationFailed`, same RBAC gap as the
  B1s VM/IoT Hub — see PROJECT_BLUEPRINT.md §11).
- Twilio is optional/demo-only per the blueprint (§4) and no account has been
  created for this project — there is no Twilio credential to test against.

Both degrade to a structured log entry when unconfigured, the same "real
code path, honest fallback when the dependency isn't there yet" pattern
already used for Chronos/TensorFlow/Evidently in `ml/`. This means the
Twilio path is real, reviewable code that has been exercised through its
fallback branch, not through an actual SMS send — said plainly rather than
implied otherwise.
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger(__name__)


def _try_acs_client():
    conn_str = os.environ.get("ACS_CONNECTION_STRING")
    if not conn_str:
        return None
    try:
        from azure.communication.email import EmailClient
        return EmailClient.from_connection_string(conn_str)
    except ImportError:
        log.warning("azure-communication-email not installed — logging alert instead of sending")
        return None
    except Exception as e:
        log.warning("Could not build ACS EmailClient (%s) — logging alert instead", e)
        return None


def send_alert_email(subject: str, body: str, recipient: str) -> dict:
    """Send via ACS if configured, else log-and-degrade gracefully.

    Returns a dict describing what actually happened — callers (the Functions
    HTTP handler) surface this in the response so "we tried to email and it
    silently did nothing" is never a possible outcome.
    """
    client = _try_acs_client()
    if client is None:
        log.warning("[ALERT - no ACS configured] to=%s subject=%s\n%s", recipient, subject, body)
        return {"channel": "log_only", "sent": False, "reason": "ACS_CONNECTION_STRING not set"}

    sender = os.environ.get("ACS_SENDER_EMAIL", "DoNotReply@wattwise.azurecomm.net")
    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": recipient}]},
        "content": {"subject": subject, "plainText": body},
    }
    try:
        poller = client.begin_send(message)
        result = poller.result()
        log.info("ACS email sent: %s", result.get("id", "unknown"))
        return {"channel": "acs", "sent": True, "message_id": result.get("id")}
    except Exception as e:
        log.error("ACS send failed: %s", e)
        return {"channel": "acs", "sent": False, "reason": str(e)}


def _try_twilio_client():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        return Client(sid, token)
    except ImportError:
        log.warning("twilio not installed — logging alert instead of sending SMS")
        return None
    except Exception as e:
        log.warning("Could not build Twilio client (%s) — logging alert instead", e)
        return None


def send_alert_sms(body: str, to_number: str | None = None) -> dict:
    """Send an SMS via Twilio if configured, else log-and-degrade gracefully.

    Optional/demo channel (blueprint §4) — most deployments will only ever
    exercise the fallback branch, which is why it's tested explicitly rather
    than assumed to work by analogy with the ACS path.
    """
    client = _try_twilio_client()
    to_number = to_number or os.environ.get("TWILIO_TO_NUMBER")
    if client is None or not to_number:
        reason = "TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN not set" if client is None else "no destination number"
        log.warning("[SMS ALERT - no Twilio configured] to=%s\n%s", to_number, body)
        return {"channel": "log_only", "sent": False, "reason": reason}

    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    try:
        message = client.messages.create(body=body[:1600], from_=from_number, to=to_number)
        log.info("Twilio SMS sent: %s", message.sid)
        return {"channel": "twilio", "sent": True, "message_sid": message.sid}
    except Exception as e:
        log.error("Twilio send failed: %s", e)
        return {"channel": "twilio", "sent": False, "reason": str(e)}


def dispatch_bms_command(facility_id: str, device_id: str, action: str) -> dict:
    """Mock BMS webhook (blueprint §Layer 4: "mock REST webhook, logs the
    action"). No real building-management system is wired up — this records
    the load-shed decision so the closed-loop path is demonstrable end-to-end
    without needing a real BMS integration in scope."""
    log.warning(
        "[MOCK BMS COMMAND] facility=%s device=%s action=%s", facility_id, device_id, action
    )
    return {"facility_id": facility_id, "device_id": device_id, "action": action, "status": "logged"}
