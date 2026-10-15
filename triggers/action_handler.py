"""WattWise AI — HUMAN-APPROVED actions pipeline.

Clearly separated from `triggers/handler.py` (AUTO-FIRED alerts). This module
ONLY runs when a human clicks Approve on an AI suggestion in the UI.

Writes an append-only audit log at `.streamlit/audit_log.jsonl` with two kinds
of events:
    * ``ai_suggested`` — the AI produced a recommendation
    * ``human_decided`` — a human approved / modified / snoozed / dismissed it
    * ``action_executed`` — the dispatched result of an approved action

Everything is JSON-serialisable, timezone-aware (UTC) and safe to replay.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

log = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path(__file__).parent.parent / ".streamlit" / "audit_log.jsonl"

ActionType = Literal[
    "shed_load",
    "dispatch_technician",
    "shift_schedule",
    "override_threshold",
    "send_alert",
    "custom",
]
Outcome = Literal["approved", "modified", "snoozed", "dismissed"]


@dataclass
class AIsuggestion:
    suggestion_id: str
    created_at: datetime
    agent_name: str
    category: str
    action_type: ActionType
    title: str
    rationale: str
    confidence: float
    impact_inr_month: float
    one_click_payload: dict = field(default_factory=dict)


@dataclass
class HumanDecision:
    suggestion_id: str
    user: str
    outcome: Outcome
    decided_at: datetime
    modified_payload: Optional[dict] = None
    user_note: str = ""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialise(obj):
    """Recursively convert datetimes to ISO strings for JSON."""
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(v) for v in obj]
    return obj


def _notify_decision(
    suggestion: "AIsuggestion", decision: "HumanDecision", payload: dict
) -> str:
    """Email ops with a human-readable summary of an approved decision.

    Returns a short status string ("sent", "skipped:no-recipients",
    "skipped:no-smtp", "failed:<reason>") so the UI can show WHY email didn't
    land. Never raises.
    """
    import os as _os

    if not _os.getenv("SMTP_HOST") or _os.getenv("SMTP_HOST") == "localhost":
        return "skipped:no-smtp"
    if not _os.getenv("ALERT_RECIPIENTS"):
        return "skipped:no-recipients"

    try:
        from triggers.handler import TriggerHandler, _dashboard_url, render_decision_html

        th = TriggerHandler()
        action_label = suggestion.action_type.replace("_", " ").title()
        subject = (
            f"[WattWise AI] {decision.outcome.upper()} — "
            f"{action_label} · {suggestion.title}"
        )
        text = f"""WattWise AI — Human-approved decision

Decision     : {decision.outcome.upper()} by {decision.user}
Decided (UTC): {decision.decided_at.isoformat()}

Suggestion
    Title      : {suggestion.title}
    Agent      : {suggestion.agent_name}
    Category   : {suggestion.category}
    Action     : {action_label}
    Confidence : {suggestion.confidence:.0%}
    Impact     : INR {suggestion.impact_inr_month:,.0f} / month

Why the AI suggested this
    {suggestion.rationale}

Dispatched payload
{json.dumps(payload, indent=2, default=str)}

Open audit log: {_dashboard_url('Audit Log')}
"""
        html = render_decision_html(suggestion, decision, payload)
        ok = th.send_mail(subject, text, html)
        return "sent" if ok else "failed:smtp"
    except Exception as e:  # pragma: no cover - defensive
        log.warning("Decision email failed: %s", e)
        return f"failed:{type(e).__name__}"


class ActionHandler:
    """Records AI suggestions, human decisions and dispatches approved ones."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = Path(log_path) if log_path is not None else AUDIT_LOG_PATH

    # ------------------------------------------------------------------ IO
    def _append(self, record: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_serialise(record), default=str)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # ------------------------------------------------------------- Public
    def record_suggestion(self, suggestion: AIsuggestion) -> None:
        record = {
            "event": "ai_suggested",
            "ts": _utcnow_iso(),
            "suggestion": asdict(suggestion),
        }
        self._append(record)

    def record_decision(self, decision: HumanDecision) -> None:
        record = {
            "event": "human_decided",
            "ts": _utcnow_iso(),
            "decision": asdict(decision),
        }
        self._append(record)

    def execute_approved(
        self, suggestion: AIsuggestion, decision: HumanDecision
    ) -> dict:
        """Dispatch an approved (or modified) action and audit the result."""
        if decision.outcome not in ("approved", "modified"):
            raise ValueError(
                f"execute_approved called with outcome={decision.outcome!r}; "
                "only 'approved' or 'modified' are allowed"
            )

        payload = (
            decision.modified_payload
            if decision.outcome == "modified" and decision.modified_payload is not None
            else suggestion.one_click_payload
        )
        channels_fired: list[str] = []
        status = "ok"

        action = suggestion.action_type
        if action == "shed_load":
            try:
                from triggers.dispatch import dispatch_bms_command  # type: ignore

                dispatch_bms_command(
                    facility_id=payload.get("facility") or payload.get("facility_id", ""),
                    device_id=payload.get("device_id", ""),
                    action=payload.get("action", "shed"),
                    action_type="shed_load",
                    loads=payload.get("loads", []),
                    shed_kw=payload.get("shed_kw", 0),
                )
                channels_fired.append("bms")
            except Exception as e:  # pragma: no cover - defensive
                log.warning("BMS dispatch failed: %s", e)
                status = "error"

        elif action == "dispatch_technician":
            log.info(
                "[TICKET] facility=%s payload=%s",
                payload.get("facility_id", "?"),
                payload,
            )
            channels_fired.append("ticket_log")

        elif action in ("send_alert", "shift_schedule", "override_threshold", "custom"):
            log.info("[%s] payload=%s", action.upper(), payload)
            channels_fired.append("log_only")

        else:  # pragma: no cover - Literal already constrains this
            status = "unknown_action"

        # Every approved/modified decision notifies ops by email — single codepath,
        # independent of the operational side-effect above.
        email_outcome = _notify_decision(suggestion, decision, payload)
        channels_fired.append(f"email:{email_outcome}")

        result = {
            "status": status,
            "action_type": action,
            "channels_fired": channels_fired,
            "timestamp": _utcnow_iso(),
        }
        self._append(
            {
                "event": "action_executed",
                "ts": result["timestamp"],
                "suggestion_id": suggestion.suggestion_id,
                "user": decision.user,
                "result": result,
            }
        )
        return result

    def read_log(
        self, user: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        if not self.log_path.exists():
            return []
        rows: list[dict] = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

        if user is not None:
            def _owner(row: dict) -> Optional[str]:
                if "decision" in row:
                    return row["decision"].get("user")
                return row.get("user")

            rows = [r for r in rows if _owner(r) == user]

        if limit is not None and limit >= 0:
            rows = rows[-limit:]
        return rows

    def stats(self) -> dict:
        rows = self.read_log(limit=10 ** 9)
        suggestions_count = sum(1 for r in rows if r.get("event") == "ai_suggested")
        decisions = [r.get("decision", {}) for r in rows if r.get("event") == "human_decided"]
        approved_count = sum(1 for d in decisions if d.get("outcome") in ("approved", "modified"))
        dismissed_count = sum(1 for d in decisions if d.get("outcome") == "dismissed")
        snoozed_count = sum(1 for d in decisions if d.get("outcome") == "snoozed")

        # approval_rate excludes snoozed per spec
        considered = approved_count + dismissed_count
        approval_rate = (approved_count / considered) if considered else 0.0

        return {
            "suggestions_count": suggestions_count,
            "approved_count": approved_count,
            "dismissed_count": dismissed_count,
            "snoozed_count": snoozed_count,
            "approval_rate": approval_rate,
        }
