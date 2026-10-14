"""Unit tests for `triggers.action_handler` — 100% coverage target."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from triggers.action_handler import (
    AUDIT_LOG_PATH,
    ActionHandler,
    AIsuggestion,
    HumanDecision,
    _serialise,
)


# --------------------------------------------------------------------- Helpers
def _mk_suggestion(action_type: str = "shed_load", sid: str = "sug-1") -> AIsuggestion:
    return AIsuggestion(
        suggestion_id=sid,
        created_at=datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc),
        agent_name="AnomalyAgent",
        category="anomaly",
        action_type=action_type,  # type: ignore[arg-type]
        title="Shed non-critical load",
        rationale="Peak demand projected to exceed contract.",
        confidence=0.87,
        impact_inr_month=12500.0,
        one_click_payload={
            "facility_id": "office",
            "device_id": "off-hvac-02",
            "action": "shed",
        },
    )


def _mk_decision(
    sid: str = "sug-1",
    outcome: str = "approved",
    user: str = "alice@ops.io",
    modified_payload=None,
) -> HumanDecision:
    return HumanDecision(
        suggestion_id=sid,
        user=user,
        outcome=outcome,  # type: ignore[arg-type]
        decided_at=datetime(2026, 10, 10, 9, 5, tzinfo=timezone.utc),
        modified_payload=modified_payload,
        user_note="",
    )


@pytest.fixture
def handler(tmp_path: Path) -> ActionHandler:
    return ActionHandler(log_path=tmp_path / ".streamlit" / "audit_log.jsonl")


# ------------------------------------------------------------- Default path
def test_default_log_path_points_to_streamlit():
    h = ActionHandler()
    assert h.log_path == AUDIT_LOG_PATH
    assert h.log_path.name == "audit_log.jsonl"
    assert h.log_path.parent.name == ".streamlit"


# ------------------------------------------------------------- 1. record_suggestion
def test_record_suggestion_writes_correct_jsonl(handler: ActionHandler):
    sug = _mk_suggestion()
    handler.record_suggestion(sug)

    lines = handler.log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "ai_suggested"
    assert row["suggestion"]["suggestion_id"] == "sug-1"
    assert row["suggestion"]["action_type"] == "shed_load"
    # timestamp is a UTC ISO string
    assert row["ts"].endswith("+00:00")


# ------------------------------------------------------------- 2. record_decision
def test_record_decision_writes_correct_jsonl(handler: ActionHandler):
    handler.record_decision(_mk_decision(outcome="approved"))

    row = json.loads(handler.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["event"] == "human_decided"
    assert row["decision"]["outcome"] == "approved"
    assert row["decision"]["user"] == "alice@ops.io"
    assert row["ts"].endswith("+00:00")


# ----------------------------------------------------- 3. execute_approved paths
def test_execute_approved_shed_load_calls_bms(handler: ActionHandler):
    sug = _mk_suggestion("shed_load")
    dec = _mk_decision(outcome="approved")

    with patch("triggers.dispatch.dispatch_bms_command") as m, \
         patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        m.return_value = {"status": "logged"}
        result = handler.execute_approved(sug, dec)

    m.assert_called_once()
    kwargs = m.call_args.kwargs
    assert kwargs["facility_id"] == "office"
    assert kwargs["device_id"] == "off-hvac-02"
    assert kwargs["action"] == "shed"
    assert kwargs["action_type"] == "shed_load"
    assert result["status"] == "ok"
    assert result["action_type"] == "shed_load"
    assert "bms" in result["channels_fired"]
    # Unified email path runs for every approved action
    assert any(ch.startswith("email:") for ch in result["channels_fired"])
    # action_executed was audited
    rows = handler.read_log()
    assert any(r.get("event") == "action_executed" for r in rows)


def test_execute_approved_dispatch_technician_logs_ticket(handler: ActionHandler):
    sug = _mk_suggestion("dispatch_technician")
    dec = _mk_decision(outcome="approved")
    with patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        result = handler.execute_approved(sug, dec)
    assert result["status"] == "ok"
    assert "ticket_log" in result["channels_fired"]
    assert any(ch.startswith("email:") for ch in result["channels_fired"])


def test_execute_approved_send_alert_notifies_ops(handler: ActionHandler):
    """send_alert is log-only operationally; the unified _notify_decision path
    is what dispatches the email, independent of action_type."""
    sug = _mk_suggestion("send_alert")
    sug.one_click_payload = {
        "event_type": "anomaly",
        "facility_id": "office",
        "device_id": "off-main-01",
        "observed_value": 55.0,
        "expected_value": 42.0,
        "anomaly_score": 0.93,
        "narrative": "Spike detected.",
    }
    dec = _mk_decision(outcome="approved")

    with patch("triggers.action_handler._notify_decision", return_value="sent") as notify_m:
        result = handler.execute_approved(sug, dec)

    notify_m.assert_called_once()
    assert result["status"] == "ok"
    assert "email:sent" in result["channels_fired"]


def test_execute_approved_custom_logs_only(handler: ActionHandler):
    sug = _mk_suggestion("custom")
    dec = _mk_decision(outcome="approved")
    with patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        result = handler.execute_approved(sug, dec)
    assert "log_only" in result["channels_fired"]
    assert any(ch.startswith("email:") for ch in result["channels_fired"])


def test_execute_approved_shift_schedule_logs_only(handler: ActionHandler):
    sug = _mk_suggestion("shift_schedule")
    with patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        result = handler.execute_approved(sug, _mk_decision(outcome="approved"))
    assert "log_only" in result["channels_fired"]


def test_execute_approved_override_threshold_logs_only(handler: ActionHandler):
    sug = _mk_suggestion("override_threshold")
    with patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        result = handler.execute_approved(sug, _mk_decision(outcome="approved"))
    assert "log_only" in result["channels_fired"]


def test_execute_approved_modified_uses_modified_payload(handler: ActionHandler):
    sug = _mk_suggestion("shed_load")
    dec = _mk_decision(
        outcome="modified",
        modified_payload={
            "facility_id": "warehouse",
            "device_id": "wh-chill-01",
            "action": "soft_shed",
        },
    )
    with patch("triggers.dispatch.dispatch_bms_command") as m, \
         patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        m.return_value = {"status": "logged"}
        handler.execute_approved(sug, dec)

    m.assert_called_once()
    kwargs = m.call_args.kwargs
    assert kwargs["facility_id"] == "warehouse"
    assert kwargs["device_id"] == "wh-chill-01"
    assert kwargs["action"] == "soft_shed"


def test_execute_approved_modified_without_payload_falls_back(handler: ActionHandler):
    """modified outcome but modified_payload is None → use suggestion payload."""
    sug = _mk_suggestion("shed_load")
    dec = _mk_decision(outcome="modified", modified_payload=None)
    with patch("triggers.dispatch.dispatch_bms_command") as m, \
         patch("triggers.action_handler._notify_decision", return_value="skipped:no-smtp"):
        m.return_value = {"status": "logged"}
        handler.execute_approved(sug, dec)
    m.assert_called_once()
    kwargs = m.call_args.kwargs
    assert kwargs["facility_id"] == "office"
    assert kwargs["device_id"] == "off-hvac-02"
    assert kwargs["action"] == "shed"


# --------------------------------------------- 4. rejects dismissed / snoozed
@pytest.mark.parametrize("bad_outcome", ["dismissed", "snoozed"])
def test_execute_approved_rejects_dismissed_or_snoozed(handler: ActionHandler, bad_outcome):
    sug = _mk_suggestion("shed_load")
    dec = _mk_decision(outcome=bad_outcome)
    with pytest.raises(ValueError, match="execute_approved"):
        handler.execute_approved(sug, dec)


# ------------------------------------------------------------- 5. read_log
def test_read_log_no_filter_returns_all(handler: ActionHandler):
    handler.record_suggestion(_mk_suggestion(sid="s1"))
    handler.record_decision(_mk_decision(sid="s1", user="alice"))
    handler.record_decision(_mk_decision(sid="s1", user="bob", outcome="dismissed"))
    rows = handler.read_log()
    assert len(rows) == 3


def test_read_log_filters_by_user(handler: ActionHandler):
    handler.record_suggestion(_mk_suggestion(sid="s1"))
    handler.record_decision(_mk_decision(sid="s1", user="alice"))
    handler.record_decision(_mk_decision(sid="s1", user="bob", outcome="dismissed"))
    alice_rows = handler.read_log(user="alice")
    assert len(alice_rows) == 1
    assert alice_rows[0]["decision"]["user"] == "alice"


def test_read_log_filters_user_matches_action_executed(handler: ActionHandler):
    sug = _mk_suggestion("custom")
    handler.execute_approved(sug, _mk_decision(user="carol", outcome="approved"))
    carol_rows = handler.read_log(user="carol")
    assert len(carol_rows) == 1
    assert carol_rows[0]["event"] == "action_executed"


def test_read_log_respects_limit(handler: ActionHandler):
    for i in range(5):
        handler.record_suggestion(_mk_suggestion(sid=f"s{i}"))
    assert len(handler.read_log(limit=2)) == 2
    # most recent two returned
    last_two = handler.read_log(limit=2)
    assert last_two[-1]["suggestion"]["suggestion_id"] == "s4"


def test_read_log_missing_file_returns_empty(tmp_path: Path):
    h = ActionHandler(log_path=tmp_path / "nowhere.jsonl")
    assert h.read_log() == []


def test_read_log_skips_blank_and_malformed_lines(handler: ActionHandler):
    handler.record_suggestion(_mk_suggestion())
    # Append a blank line and a garbage line that would otherwise break JSON parsing
    with handler.log_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write("{not json}\n")
    rows = handler.read_log()
    assert len(rows) == 1  # only the valid record


# ------------------------------------------------------------- 6/7. stats
def test_stats_on_empty_log(tmp_path: Path):
    h = ActionHandler(log_path=tmp_path / "empty.jsonl")
    s = h.stats()
    assert s == {
        "suggestions_count": 0,
        "approved_count": 0,
        "dismissed_count": 0,
        "snoozed_count": 0,
        "approval_rate": 0.0,
    }


def test_stats_computes_approval_rate_ignoring_snoozed(handler: ActionHandler):
    # 3 suggestions, 2 approved, 1 dismissed, 1 snoozed (snoozed excluded)
    for i in range(3):
        handler.record_suggestion(_mk_suggestion(sid=f"s{i}"))
    handler.record_decision(_mk_decision(sid="s0", outcome="approved"))
    handler.record_decision(_mk_decision(sid="s1", outcome="modified"))  # counts as approved
    handler.record_decision(_mk_decision(sid="s2", outcome="dismissed"))
    handler.record_decision(_mk_decision(sid="s2", outcome="snoozed"))

    s = handler.stats()
    assert s["suggestions_count"] == 3
    assert s["approved_count"] == 2
    assert s["dismissed_count"] == 1
    assert s["snoozed_count"] == 1
    # 2 approved / (2 approved + 1 dismissed) = 2/3
    assert s["approval_rate"] == pytest.approx(2 / 3)


# ------------------------------------------------------------- 8. file creation
def test_log_file_created_if_missing(tmp_path: Path):
    nested = tmp_path / "deep" / "nested" / "audit.jsonl"
    assert not nested.exists()
    h = ActionHandler(log_path=nested)
    h.record_suggestion(_mk_suggestion())
    assert nested.exists()
    assert nested.parent.is_dir()


# ------------------------------------------------------------- 9. append-only
def test_append_only_does_not_overwrite(handler: ActionHandler):
    handler.record_suggestion(_mk_suggestion(sid="s1"))
    handler.record_suggestion(_mk_suggestion(sid="s2"))
    handler.record_decision(_mk_decision(sid="s1"))
    lines = handler.log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    # order preserved
    assert json.loads(lines[0])["suggestion"]["suggestion_id"] == "s1"
    assert json.loads(lines[1])["suggestion"]["suggestion_id"] == "s2"
    assert json.loads(lines[2])["event"] == "human_decided"


# ------------------------------------------------------------- 10. timezone-aware timestamps
def test_timestamps_are_timezone_aware_utc(handler: ActionHandler):
    handler.record_suggestion(_mk_suggestion())
    handler.record_decision(_mk_decision())
    for raw in handler.log_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        ts = datetime.fromisoformat(row["ts"])
        assert ts.tzinfo is not None
        assert ts.utcoffset().total_seconds() == 0


def test_serialise_handles_naive_datetime_as_utc():
    naive = datetime(2026, 1, 1, 12, 0)
    out = _serialise(naive)
    assert out.endswith("+00:00")


def test_serialise_recurses_lists_and_dicts():
    data = {"a": [datetime(2026, 1, 1, tzinfo=timezone.utc), {"b": 1}], "c": "x"}
    out = _serialise(data)
    assert out["a"][0].startswith("2026-01-01")
    assert out["a"][1] == {"b": 1}
    assert out["c"] == "x"


# ---------------------------------------- 11. mock TriggerHandler for send_alert
def test_send_alert_path_notifies_via_unified_email(handler: ActionHandler):
    """The send_alert branch is now log-only operationally; the unified
    _notify_decision helper is responsible for every approved email."""
    sug = _mk_suggestion("send_alert")
    sug.one_click_payload = {}
    dec = _mk_decision(outcome="approved")
    with patch("triggers.action_handler._notify_decision", return_value="sent") as notify_m:
        result = handler.execute_approved(sug, dec)
    notify_m.assert_called_once()
    args = notify_m.call_args.args
    # Called with (suggestion, decision, payload) — payload is the suggestion's
    # one_click_payload when the decision wasn't modified.
    assert args[0].action_type == "send_alert"
    assert args[1].outcome == "approved"
    assert result["status"] == "ok"
    assert "email:sent" in result["channels_fired"]


# ---------------------------------------- 12. tmp_path isolation sanity check
def test_tmp_path_isolation_does_not_touch_real_audit_log(tmp_path: Path):
    """Belt-and-braces: ensure tests write only under tmp_path."""
    h = ActionHandler(log_path=tmp_path / "iso.jsonl")
    h.record_suggestion(_mk_suggestion())
    assert h.log_path.exists()
    assert str(tmp_path) in str(h.log_path.resolve())
    # The real audit log path must not have been created by this test
    # (we don't assert on its state since it may legitimately exist from app usage).
    assert h.log_path != AUDIT_LOG_PATH
