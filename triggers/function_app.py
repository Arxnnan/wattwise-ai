"""WattWise AI — Azure Functions app (Layer 4: Automated Triggers).

Python v2 programming model. Two HTTP-triggered endpoints:
  POST /api/event        - AI-detected anomaly/peak/optimization event -> alert
  POST /api/bms/webhook  - mock BMS load-shed command (logged, not a real BMS)

Deploy: func azure functionapp publish wattwise-functions
Local:  func start   (needs local.settings.json, gitignored — copy from
        local.settings.json.example)
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from dispatch import send_alert_email, send_alert_sms, dispatch_bms_command

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
log = logging.getLogger(__name__)

REQUIRED_EVENT_FIELDS = {
    "event_type", "facility_id", "device_id", "observed_value", "expected_value", "anomaly_score",
}


@app.route(route="event", methods=["POST"])
def handle_event(req: func.HttpRequest) -> func.HttpResponse:
    """Receives an AI event (anomaly / peak_warning / optimization) and
    dispatches an alert. This is the closed-loop step the blueprint
    describes as Chronos/PyOD/LSTM-AE -> Gemini narrative -> trigger -> alert.
    """
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "request body must be JSON"}),
            status_code=400, mimetype="application/json",
        )

    missing = REQUIRED_EVENT_FIELDS - payload.keys()
    if missing:
        return func.HttpResponse(
            json.dumps({"error": f"missing required fields: {sorted(missing)}"}),
            status_code=400, mimetype="application/json",
        )

    event_type = payload["event_type"]
    facility_id = payload["facility_id"]
    device_id = payload["device_id"]
    narrative = payload.get("narrative", "")

    subject = f"[WattWise AI] {event_type.upper()} detected — {facility_id}/{device_id}"
    body = (
        f"Type: {event_type.upper()}\n"
        f"Facility: {facility_id}\n"
        f"Device: {device_id}\n"
        f"Observed: {payload['observed_value']}\n"
        f"Expected: {payload['expected_value']}\n"
        f"Anomaly score: {payload['anomaly_score']}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"AI Narrative:\n{narrative or 'No narrative generated yet.'}"
    )
    recipient = payload.get("recipient", "ops@wattwise.local")

    email_result = send_alert_email(subject, body, recipient)
    sms_result = send_alert_sms(f"{subject}\n{body[:140]}", payload.get("sms_to"))

    response = {
        "received": True,
        "event_type": event_type,
        "facility_id": facility_id,
        "device_id": device_id,
        "email": email_result,
        "sms": sms_result,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info("Event processed: %s", response)
    return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")


@app.route(route="bms/webhook", methods=["POST"])
def bms_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """Mock building-management-system command endpoint — logs a load-shed
    action rather than actually controlling equipment (no real BMS in scope).
    """
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "request body must be JSON"}),
            status_code=400, mimetype="application/json",
        )

    for field in ("facility_id", "device_id", "action"):
        if field not in payload:
            return func.HttpResponse(
                json.dumps({"error": f"missing required field: {field}"}),
                status_code=400, mimetype="application/json",
            )

    result = dispatch_bms_command(payload["facility_id"], payload["device_id"], payload["action"])
    return func.HttpResponse(json.dumps(result), status_code=200, mimetype="application/json")
