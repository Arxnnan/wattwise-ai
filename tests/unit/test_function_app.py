"""Unit tests — triggers/function_app.py (Azure Functions v2 HTTP entrypoint).

`triggers/function_app.py` is laid out as an Azure Functions deployment root, so
it imports its sibling module as `from dispatch import ...` (not
`from triggers.dispatch import ...`). We alias `triggers.dispatch` into
`sys.modules` as `dispatch` BEFORE importing the module so the bare import
resolves without duplicating code.

The HTTP handlers are plain Python callables once the `@app.route` decorator
has registered them, so we invoke them directly with an `azure.functions`
`HttpRequest` and inspect the returned `HttpResponse`. The downstream dispatch
helpers are patched at the `triggers.function_app` import site so no network
or SMTP traffic happens.
"""
from __future__ import annotations

import json
import sys

import pytest

# --- Make `from dispatch import ...` work in function_app.py --------------
# The real module already imported under its package path by other tests.
from triggers import dispatch as _triggers_dispatch

sys.modules.setdefault("dispatch", _triggers_dispatch)

import azure.functions as azf  # noqa: E402

from triggers import function_app  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _make_request(path: str, body: bytes, *, method: str = "POST") -> azf.HttpRequest:
    return azf.HttpRequest(
        method=method,
        url=f"http://localhost/api/{path}",
        body=body,
        headers={"Content-Type": "application/json"},
    )


def _valid_event_payload() -> dict:
    return {
        "event_type": "anomaly",
        "facility_id": "office",
        "device_id": "off-main-01",
        "observed_value": 120.0,
        "expected_value": 42.0,
        "anomaly_score": 0.93,
        "narrative": "Spike at 10:00",
        "recipient": "ops@wattwise.local",
        "sms_to": "+15550001111",
    }


@pytest.fixture
def mock_dispatch(mocker):
    """Patch cloud alert functions at the function_app import site."""
    email = mocker.patch(
        "triggers.function_app.send_alert_email",
        return_value={"channel": "acs", "sent": True, "message_id": "msg-1"},
    )
    sms = mocker.patch(
        "triggers.function_app.send_alert_sms",
        return_value={"channel": "twilio", "sent": True, "message_sid": "SM1"},
    )
    bms = mocker.patch(
        "triggers.function_app.dispatch_bms_command",
        return_value={
            "facility_id": "office",
            "device_id": "off-hvac-01",
            "action": "shed_load_15min",
            "status": "logged",
        },
    )
    return {"email": email, "sms": sms, "bms": bms}


def _unwrap(handler):
    """Pull the real Python function out of the decorator-wrapped FunctionBuilder."""
    # Azure Functions decorators return the underlying function unchanged; the
    # module attribute IS the callable. But if a FunctionBuilder wraps it, step
    # through its _func attribute.
    if callable(handler) and not hasattr(handler, "_func"):
        return handler
    return getattr(handler, "_func", handler)


# --------------------------------------------------------------------------
# /api/event
# --------------------------------------------------------------------------


class TestHandleEvent:

    def test_happy_path_returns_200_with_dispatch_summary(self, mock_dispatch):
        req = _make_request("event", json.dumps(_valid_event_payload()).encode())
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        body = json.loads(resp.get_body())
        assert body["received"] is True
        assert body["event_type"] == "anomaly"
        assert body["facility_id"] == "office"
        assert body["device_id"] == "off-main-01"
        assert body["email"]["sent"] is True
        assert body["sms"]["sent"] is True
        assert "processed_at" in body

        # recipient / sms_to and subject/body were threaded through
        assert mock_dispatch["email"].call_count == 1
        email_args = mock_dispatch["email"].call_args.args
        assert email_args[0].startswith("[WattWise AI] ANOMALY detected")
        assert "Facility: office" in email_args[1]
        assert email_args[2] == "ops@wattwise.local"

        sms_args = mock_dispatch["sms"].call_args.args
        assert sms_args[1] == "+15550001111"
        # SMS body truncated to subject + first 140 chars of body
        assert sms_args[0].startswith("[WattWise AI] ANOMALY detected")

    def test_missing_narrative_defaults_to_placeholder_text(self, mock_dispatch):
        payload = _valid_event_payload()
        payload.pop("narrative")
        req = _make_request("event", json.dumps(payload).encode())
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 200
        body = mock_dispatch["email"].call_args.args[1]
        assert "No narrative generated yet." in body

    def test_default_recipient_when_omitted(self, mock_dispatch):
        payload = _valid_event_payload()
        payload.pop("recipient")
        payload.pop("sms_to")
        req = _make_request("event", json.dumps(payload).encode())
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 200
        assert mock_dispatch["email"].call_args.args[2] == "ops@wattwise.local"
        # sms_to omitted -> None forwarded
        assert mock_dispatch["sms"].call_args.args[1] is None

    def test_malformed_json_returns_400(self, mock_dispatch):
        req = _make_request("event", b"{not valid json")
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 400
        assert resp.mimetype == "application/json"
        body = json.loads(resp.get_body())
        assert body == {"error": "request body must be JSON"}
        mock_dispatch["email"].assert_not_called()
        mock_dispatch["sms"].assert_not_called()

    def test_missing_required_fields_returns_400_with_sorted_list(self, mock_dispatch):
        payload = {"event_type": "anomaly", "facility_id": "office"}
        req = _make_request("event", json.dumps(payload).encode())
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 400
        body = json.loads(resp.get_body())
        assert body["error"].startswith("missing required fields:")
        # sorted() output includes exactly the fields that were absent
        for name in (
            "device_id", "observed_value", "expected_value", "anomaly_score",
        ):
            assert name in body["error"]
        mock_dispatch["email"].assert_not_called()

    def test_dispatch_failure_surfaces_in_response(self, mocker, mock_dispatch):
        mock_dispatch["email"].return_value = {
            "channel": "acs", "sent": False, "reason": "ACS quota exceeded",
        }
        mock_dispatch["sms"].return_value = {
            "channel": "log_only", "sent": False, "reason": "no destination number",
        }
        req = _make_request("event", json.dumps(_valid_event_payload()).encode())
        resp = _unwrap(function_app.handle_event)(req)

        assert resp.status_code == 200  # we still ack the event
        body = json.loads(resp.get_body())
        assert body["email"]["sent"] is False
        assert body["sms"]["sent"] is False
        assert body["email"]["reason"] == "ACS quota exceeded"


# --------------------------------------------------------------------------
# /api/bms/webhook
# --------------------------------------------------------------------------


class TestBmsWebhook:

    def test_happy_path_returns_logged_result(self, mock_dispatch):
        payload = {
            "facility_id": "office",
            "device_id": "off-hvac-01",
            "action": "shed_load_15min",
        }
        req = _make_request("bms/webhook", json.dumps(payload).encode())
        resp = _unwrap(function_app.bms_webhook)(req)

        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        body = json.loads(resp.get_body())
        assert body["status"] == "logged"
        mock_dispatch["bms"].assert_called_once_with(
            "office", "off-hvac-01", "shed_load_15min",
        )

    def test_malformed_json_returns_400(self, mock_dispatch):
        req = _make_request("bms/webhook", b"not-json-at-all")
        resp = _unwrap(function_app.bms_webhook)(req)

        assert resp.status_code == 400
        body = json.loads(resp.get_body())
        assert body == {"error": "request body must be JSON"}
        mock_dispatch["bms"].assert_not_called()

    @pytest.mark.parametrize(
        "missing_field,remaining",
        [
            ("facility_id", {"device_id": "d", "action": "a"}),
            ("device_id",   {"facility_id": "f", "action": "a"}),
            ("action",      {"facility_id": "f", "device_id": "d"}),
        ],
    )
    def test_missing_required_field_returns_400(self, missing_field, remaining, mock_dispatch):
        req = _make_request("bms/webhook", json.dumps(remaining).encode())
        resp = _unwrap(function_app.bms_webhook)(req)

        assert resp.status_code == 400
        body = json.loads(resp.get_body())
        assert body == {"error": f"missing required field: {missing_field}"}
        mock_dispatch["bms"].assert_not_called()


# --------------------------------------------------------------------------
# module-level sanity
# --------------------------------------------------------------------------


class TestModuleSetup:

    def test_app_is_function_app_instance(self):
        assert isinstance(function_app.app, azf.FunctionApp)

    def test_required_event_fields_set(self):
        assert function_app.REQUIRED_EVENT_FIELDS == {
            "event_type", "facility_id", "device_id",
            "observed_value", "expected_value", "anomaly_score",
        }
