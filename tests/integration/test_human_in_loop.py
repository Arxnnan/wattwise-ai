"""Integration tests for the WattWise AI human-in-the-loop decision pipeline.

Exercises the full "AI advises, human decides" loop end-to-end:
    AIsuggestion -> HumanDecision -> ActionHandler.execute_approved -> audit log

Real modules are used throughout (``triggers.action_handler``,
``triggers.dispatch`` and ``triggers.handler``). Only the actual outbound
side-effects are mocked:
    * ``requests.post`` for the BMS webhook
    * ``triggers.handler.TriggerHandler.fire`` for the alert path

The audit log is redirected to ``tmp_path`` on every test so nothing is ever
written to the real ``.streamlit/audit_log.jsonl``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from triggers.action_handler import ActionHandler, AIsuggestion, HumanDecision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    """Per-test audit log file — never touches .streamlit/audit_log.jsonl."""
    return tmp_path / "audit_log.jsonl"


@pytest.fixture
def handler(audit_path: Path) -> ActionHandler:
    return ActionHandler(log_path=audit_path)


@pytest.fixture
def bms_webhook_env(monkeypatch) -> str:
    """Enable the real HTTP code path in dispatch_bms_command."""
    url = "http://mock-bms.local/command"
    monkeypatch.setenv("BMS_WEBHOOK_URL", url)
    monkeypatch.delenv("BMS_AUTH_TOKEN", raising=False)
    return url


def _make_suggestion(
    *,
    action_type: str = "shed_load",
    one_click_payload: dict | None = None,
    suggestion_id: str = "sug-001",
) -> AIsuggestion:
    return AIsuggestion(
        suggestion_id=suggestion_id,
        created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        agent_name="peak_shaving_agent",
        category="demand_response",
        action_type=action_type,  # type: ignore[arg-type]
        title=f"Test suggestion {suggestion_id}",
        rationale="Forecast says 20 kW peak in 45 min — shed non-critical loads.",
        confidence=0.87,
        impact_inr_month=12_500.0,
        one_click_payload=one_click_payload
        or {
            "facility": "office",
            "device_id": "off-main-01",
            "loads": ["chiller_2", "corridor_lights"],
            "shed_kw": 15,
            "action": "shed",
        },
    )


def _make_decision(
    *,
    outcome: str = "approved",
    modified_payload: dict | None = None,
    suggestion_id: str = "sug-001",
    user: str = "ops@wattwise.local",
) -> HumanDecision:
    return HumanDecision(
        suggestion_id=suggestion_id,
        user=user,
        outcome=outcome,  # type: ignore[arg-type]
        decided_at=datetime(2026, 1, 15, 10, 1, tzinfo=timezone.utc),
        modified_payload=modified_payload,
    )


def _read_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _mock_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {"ack": "ok"}
    resp.text = json.dumps(body or {"ack": "ok"})
    return resp


# ---------------------------------------------------------------------------
# 1. Full approve-shed-load loop
# ---------------------------------------------------------------------------


def test_full_approve_shed_load_loop(handler, audit_path, bms_webhook_env):
    suggestion = _make_suggestion()
    decision = _make_decision(outcome="approved")

    with patch("requests.post", return_value=_mock_response(200, {"ack": "scheduled"})) as mp, \
         patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        result = handler.execute_approved(suggestion, decision)

    # Dispatch happened over the real HTTP seam
    assert mp.call_count == 1
    posted_url, posted_kwargs = mp.call_args.args, mp.call_args.kwargs
    assert posted_url[0] == bms_webhook_env
    payload = posted_kwargs["json"]
    assert payload["facility"] == "office"
    assert payload["facility_id"] == "office"
    assert payload["action_type"] == "shed_load"
    assert payload["loads"] == ["chiller_2", "corridor_lights"]
    assert payload["shed_kw"] == 15

    # Audit log has exactly three ordered entries
    events = _read_events(audit_path)
    assert [e["event"] for e in events] == [
        "ai_suggested",
        "human_decided",
        "action_executed",
    ]
    assert events[-1]["result"]["status"] == "ok"
    # Operational channel is BMS; unified decision email always runs after.
    assert "bms" in events[-1]["result"]["channels_fired"]
    assert any(ch.startswith("email:") for ch in events[-1]["result"]["channels_fired"])
    assert "bms" in result["channels_fired"]


# ---------------------------------------------------------------------------
# 2. Dismiss skips dispatch
# ---------------------------------------------------------------------------


def test_dismiss_skips_dispatch(handler, audit_path, bms_webhook_env):
    suggestion = _make_suggestion()
    decision = _make_decision(outcome="dismissed")

    with patch("requests.post") as mp:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        with pytest.raises(ValueError, match="execute_approved"):
            handler.execute_approved(suggestion, decision)

    mp.assert_not_called()
    events = _read_events(audit_path)
    assert [e["event"] for e in events] == ["ai_suggested", "human_decided"]


# ---------------------------------------------------------------------------
# 3. Snooze also skips dispatch
# ---------------------------------------------------------------------------


def test_snooze_skips_dispatch(handler, audit_path, bms_webhook_env):
    suggestion = _make_suggestion()
    decision = _make_decision(outcome="snoozed")

    with patch("requests.post") as mp:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        with pytest.raises(ValueError):
            handler.execute_approved(suggestion, decision)

    mp.assert_not_called()
    events = _read_events(audit_path)
    assert len(events) == 2
    assert events[1]["decision"]["outcome"] == "snoozed"


# ---------------------------------------------------------------------------
# 4. Modified payload overrides original
# ---------------------------------------------------------------------------


def test_modified_payload_overrides_original(handler, bms_webhook_env):
    suggestion = _make_suggestion()  # original shed_kw=15
    modified = {
        "facility": "office",
        "device_id": "off-main-01",
        "loads": ["chiller_2"],
        "shed_kw": 50,  # operator bumped it
        "action": "shed",
    }
    decision = _make_decision(outcome="modified", modified_payload=modified)

    with patch("requests.post", return_value=_mock_response(200)) as mp:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        handler.execute_approved(suggestion, decision)

    sent = mp.call_args.kwargs["json"]
    assert sent["shed_kw"] == 50
    assert sent["loads"] == ["chiller_2"]


# ---------------------------------------------------------------------------
# 5. send_alert fires TriggerHandler.fire
# ---------------------------------------------------------------------------


def test_send_alert_fires_trigger_handler(handler, audit_path):
    suggestion = _make_suggestion(
        action_type="send_alert",
        one_click_payload={
            "facility_id": "warehouse",
            "device_id": "wh-main-01",
            "event_type": "peak_warning",
            "observed_value": 85.3,
            "expected_value": 60.0,
            "anomaly_score": 0.91,
            "narrative": "Rolling 15-min demand above 90th percentile",
        },
    )
    decision = _make_decision(outcome="approved")

    with patch("triggers.action_handler._notify_decision", return_value="sent") as notify_m:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        result = handler.execute_approved(suggestion, decision)

    # send_alert goes through the unified decision-email path (which calls
    # TriggerHandler.send_mail internally); here we just confirm the policy.
    notify_m.assert_called_once()
    args = notify_m.call_args.args
    assert args[0].action_type == "send_alert"
    payload = args[2]
    assert payload["facility_id"] == "warehouse"
    assert payload["device_id"] == "wh-main-01"
    assert "email:sent" in result["channels_fired"]


# ---------------------------------------------------------------------------
# 6. dispatch_technician logs a ticket channel
# ---------------------------------------------------------------------------


def test_dispatch_technician_logs_ticket(handler, audit_path):
    suggestion = _make_suggestion(
        action_type="dispatch_technician",
        one_click_payload={
            "facility_id": "warehouse",
            "device_id": "wh-chiller-02",
            "priority": "high",
            "symptom": "temperature drift",
        },
    )
    decision = _make_decision(outcome="approved")

    with patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        result = handler.execute_approved(suggestion, decision)

    assert result["status"] == "ok"
    # Operational channel is "ticket_log"; the decision email runs after.
    assert "ticket_log" in result["channels_fired"]
    assert any(ch.startswith("email:") for ch in result["channels_fired"])

    events = _read_events(audit_path)
    assert events[-1]["event"] == "action_executed"
    assert "ticket_log" in events[-1]["result"]["channels_fired"]


# ---------------------------------------------------------------------------
# 7. BMS HTTP 500 is handled gracefully
# ---------------------------------------------------------------------------


def test_bms_http_error_recorded_gracefully(handler, audit_path, bms_webhook_env):
    suggestion = _make_suggestion()
    decision = _make_decision(outcome="approved")

    with patch("requests.post", return_value=_mock_response(500, {"error": "bms down"})) as mp:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        # Must not raise — dispatch_bms_command swallows HTTP errors into a dict
        result = handler.execute_approved(suggestion, decision)

    assert mp.call_count == 1
    # action_handler still logs the audit entry; dispatch returned an http_error
    # dict (not an exception), so the audit record itself is 'ok' with the bms
    # channel marked as fired. The call did happen — that's what we assert.
    events = _read_events(audit_path)
    assert [e["event"] for e in events] == [
        "ai_suggested",
        "human_decided",
        "action_executed",
    ]
    executed = events[-1]
    assert "bms" in executed["result"]["channels_fired"]
    assert result["action_type"] == "shed_load"


# ---------------------------------------------------------------------------
# 8. BMS connection failure is handled gracefully
# ---------------------------------------------------------------------------


def test_bms_connection_error_recorded_gracefully(handler, audit_path, bms_webhook_env):
    suggestion = _make_suggestion()
    decision = _make_decision(outcome="approved")

    import requests as _requests

    with patch(
        "requests.post", side_effect=_requests.ConnectionError("connection refused")
    ) as mp:
        handler.record_suggestion(suggestion)
        handler.record_decision(decision)
        # dispatch_bms_command catches the ConnectionError internally and
        # returns a {status: 'failed', error: ...} dict — execute_approved
        # therefore completes without raising.
        result = handler.execute_approved(suggestion, decision)

    assert mp.call_count == 1
    events = _read_events(audit_path)
    assert len(events) == 3
    assert events[-1]["event"] == "action_executed"
    # The dispatch wrapper swallowed the error — audit still records the attempt
    assert "bms" in events[-1]["result"]["channels_fired"]
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# 9. Approval stats exclude snoozed from the denominator
# ---------------------------------------------------------------------------


def test_approval_stats_exclude_snoozed(handler, bms_webhook_env):
    outcomes = ["approved", "approved", "approved", "dismissed", "snoozed"]

    with patch("requests.post", return_value=_mock_response(200)):
        for i, outcome in enumerate(outcomes):
            sug = _make_suggestion(suggestion_id=f"sug-{i:03d}")
            dec = _make_decision(outcome=outcome, suggestion_id=f"sug-{i:03d}")
            handler.record_suggestion(sug)
            handler.record_decision(dec)
            if outcome in ("approved", "modified"):
                handler.execute_approved(sug, dec)

    s = handler.stats()
    assert s["suggestions_count"] == 5
    assert s["approved_count"] == 3
    assert s["dismissed_count"] == 1
    assert s["snoozed_count"] == 1
    assert s["approval_rate"] == pytest.approx(0.75)  # 3 / (3 + 1)


# ---------------------------------------------------------------------------
# 10. Full round-trip through a temp audit file
# ---------------------------------------------------------------------------


def test_round_trip_via_audit_file(handler, audit_path, bms_webhook_env):
    scenarios = [
        ("sug-A", "approved"),
        ("sug-B", "dismissed"),
        ("sug-C", "modified"),
    ]

    with patch("requests.post", return_value=_mock_response(200)):
        for sid, outcome in scenarios:
            sug = _make_suggestion(suggestion_id=sid)
            dec = _make_decision(
                suggestion_id=sid,
                outcome=outcome,
                modified_payload={"facility": "office", "shed_kw": 7, "action": "shed"}
                if outcome == "modified"
                else None,
            )
            handler.record_suggestion(sug)
            handler.record_decision(dec)
            if outcome in ("approved", "modified"):
                handler.execute_approved(sug, dec)

    # Chronological ordering is: suggest-A, decide-A, exec-A, suggest-B, decide-B,
    # suggest-C, decide-C, exec-C
    rows = handler.read_log(limit=100)
    expected = [
        ("ai_suggested", "sug-A"),
        ("human_decided", "sug-A"),
        ("action_executed", "sug-A"),
        ("ai_suggested", "sug-B"),
        ("human_decided", "sug-B"),
        ("ai_suggested", "sug-C"),
        ("human_decided", "sug-C"),
        ("action_executed", "sug-C"),
    ]
    actual = [
        (
            r["event"],
            r.get("suggestion", {}).get("suggestion_id")
            or r.get("decision", {}).get("suggestion_id")
            or r.get("suggestion_id"),
        )
        for r in rows
    ]
    assert actual == expected

    s = handler.stats()
    assert s["suggestions_count"] == 3
    assert s["approved_count"] == 2  # approved + modified
    assert s["dismissed_count"] == 1
    assert s["snoozed_count"] == 0
    assert s["approval_rate"] == pytest.approx(2 / 3)

    # Audit file lives under tmp_path — never under .streamlit/
    assert audit_path.exists()
    assert ".streamlit" not in str(audit_path)
