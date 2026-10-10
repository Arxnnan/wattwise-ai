"""WattWise AI — Morning Briefing Agent.

The Morning Briefing engine orchestrates all specialist agents in parallel,
collects their findings, and distills them into the top N actionable
recommendations for a human reviewer. The AI never auto-executes — every
recommendation is a suggestion for human Approve / Modify / Snooze / Dismiss.

Design:
- Fan out to the 4 specialists via ThreadPoolExecutor (per-specialist timeout).
- Each `_X_candidates` wrapper calls its specialist, parses the free-text
  reply into one or more ActionRecommendation objects, and swallows any
  exception so one failing specialist cannot sink the whole briefing.
- Dedupe by device_id (highest impact wins) then rank by
  impact_inr_month * confidence (desc, stable).
"""
from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal

log = logging.getLogger(__name__)

Category = Literal["cost", "anomaly", "optimization", "forecast"]
ActionType = Literal[
    "shed_load", "dispatch_technician", "shift_schedule",
    "override_threshold", "send_alert",
]


@dataclass
class ActionRecommendation:
    id: str
    created_at: datetime
    facility_id: str
    category: Category
    agent_name: str
    title: str
    rationale: str
    impact_inr_month: float
    confidence: float
    action_type: ActionType
    one_click_payload: dict
    counterfactual: str = ""
    similar_past_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_BLOCK_SPLIT_RE = re.compile(r"(?mi)^\s*RECOMMENDATION\s*:?\s*$")
_KV_RE = re.compile(r"(?mi)^\s*([a-z_]+)\s*[:=]\s*(.+?)\s*$")


def _parse_blocks(text: str) -> list[dict]:
    """Split specialist text into zero-or-more key/value blocks.

    A block starts at a line that is exactly `RECOMMENDATION` (optionally with
    a trailing colon). If no such marker is present, the whole string is
    treated as a single block.
    """
    if not text or not text.strip():
        return []
    parts = _BLOCK_SPLIT_RE.split(text)
    # Drop any leading preamble before the first marker; keep single-block case.
    blocks: list[dict] = []
    candidates = parts[1:] if len(parts) > 1 else parts
    for raw in candidates:
        kv: dict = {}
        for m in _KV_RE.finditer(raw):
            kv[m.group(1).lower()] = m.group(2).strip()
        if kv:
            blocks.append(kv)
    return blocks


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    # Strip common currency / thousands formatting.
    cleaned = re.sub(r"[^\d.\-]", "", value)
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default


def _as_confidence(value: str | None, default: float = 0.5) -> float:
    conf = _as_float(value, default)
    if conf > 1.0:
        conf = conf / 100.0
    if conf < 0.0:
        conf = 0.0
    if conf > 1.0:
        conf = 1.0
    return conf


def _build_recommendation(
    *,
    block: dict,
    facility_id: str,
    category: Category,
    agent_name: str,
    default_title: str,
    default_action: ActionType,
) -> ActionRecommendation:
    device_id = block.get("device") or block.get("device_id") or ""
    payload: dict = {"device_id": device_id} if device_id else {}
    if "window" in block:
        payload["window"] = block["window"]
    return ActionRecommendation(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        facility_id=facility_id,
        category=category,
        agent_name=agent_name,
        title=block.get("title", default_title),
        rationale=block.get("rationale", ""),
        impact_inr_month=_as_float(block.get("impact"), 0.0),
        confidence=_as_confidence(block.get("confidence")),
        action_type=block.get("action_type", default_action),  # type: ignore[arg-type]
        one_click_payload=payload,
        counterfactual=block.get("counterfactual", ""),
    )


# ---------------------------------------------------------------------------
# BriefingAgent
# ---------------------------------------------------------------------------


class BriefingAgent:
    """Orchestrates the 4 specialists in parallel and ranks their outputs."""

    def __init__(self, specialists: dict | None = None):
        self._specialists = specialists
        self._executor = ThreadPoolExecutor(max_workers=4)

    # ---- public API ------------------------------------------------------

    def generate(
        self, facility_id: str, top_n: int = 3, timeout_sec: int = 20,
    ) -> list[ActionRecommendation]:
        """Fan out to specialists, collect, rank, dedupe, return top N."""
        jobs: dict[str, Callable[[str], list[ActionRecommendation]]] = {
            "anomaly": self._anomaly_candidates,
            "cost": self._cost_candidates,
            "optimization": self._optimizer_candidates,
            "forecast": self._forecast_candidates,
        }
        futures = {
            name: self._executor.submit(fn, facility_id)
            for name, fn in jobs.items()
        }
        collected: list[ActionRecommendation] = []
        for name, fut in futures.items():
            try:
                collected.extend(fut.result(timeout=timeout_sec))
            except FutureTimeoutError:
                log.warning("Briefing: %s specialist timed out after %ss", name, timeout_sec)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("Briefing: %s specialist raised: %s", name, exc)

        if not collected:
            log.warning("Briefing: no recommendations produced for %s", facility_id)
            return []

        deduped = self._dedupe_by_device(collected)
        ranked = self._rank(deduped)
        return ranked[:top_n]

    # ---- specialist loading ---------------------------------------------

    def _get_specialists(self) -> dict:
        """Lazy-load the real specialist agents on first use."""
        if self._specialists is None:
            from ml.agents.anomaly_agent import AnomalyAgent
            from ml.agents.cost_agent import CostAgent
            from ml.agents.forecast_agent import ForecastAgent
            from ml.agents.optimizer_agent import OptimizerAgent
            self._specialists = {
                "anomaly": AnomalyAgent(),
                "cost": CostAgent(),
                "optimizer": OptimizerAgent(),
                "forecast": ForecastAgent(),
            }
        return self._specialists

    # ---- per-specialist adapters ----------------------------------------

    def _anomaly_candidates(self, facility_id: str) -> list[ActionRecommendation]:
        try:
            agent = self._get_specialists()["anomaly"]
            text = agent.monitor(facility_id)
        except Exception as exc:
            log.warning("AnomalyAgent failed: %s", exc)
            return []
        return [
            _build_recommendation(
                block=b, facility_id=facility_id, category="anomaly",
                agent_name="AnomalyAgent",
                default_title="Investigate anomalous consumption",
                default_action="dispatch_technician",
            )
            for b in _parse_blocks(text)
        ]

    def _cost_candidates(self, facility_id: str) -> list[ActionRecommendation]:
        try:
            agent = self._get_specialists()["cost"]
            text = agent.analyze(facility_id)
        except Exception as exc:
            log.warning("CostAgent failed: %s", exc)
            return []
        return [
            _build_recommendation(
                block=b, facility_id=facility_id, category="cost",
                agent_name="CostAgent",
                default_title="Reduce tariff exposure",
                default_action="shift_schedule",
            )
            for b in _parse_blocks(text)
        ]

    def _optimizer_candidates(self, facility_id: str) -> list[ActionRecommendation]:
        try:
            agent = self._get_specialists()["optimizer"]
            text = agent.optimize(facility_id)
        except Exception as exc:
            log.warning("OptimizerAgent failed: %s", exc)
            return []
        return [
            _build_recommendation(
                block=b, facility_id=facility_id, category="optimization",
                agent_name="OptimizerAgent",
                default_title="Shed non-critical load",
                default_action="shed_load",
            )
            for b in _parse_blocks(text)
        ]

    def _forecast_candidates(self, facility_id: str) -> list[ActionRecommendation]:
        try:
            agent = self._get_specialists()["forecast"]
            text = agent.predict(facility_id)
        except Exception as exc:
            log.warning("ForecastAgent failed: %s", exc)
            return []
        return [
            _build_recommendation(
                block=b, facility_id=facility_id, category="forecast",
                agent_name="ForecastAgent",
                default_title="Prepare for forecast peak",
                default_action="send_alert",
            )
            for b in _parse_blocks(text)
        ]

    # ---- ranking / dedupe ------------------------------------------------

    def _dedupe_by_device(
        self, recs: list[ActionRecommendation],
    ) -> list[ActionRecommendation]:
        """If 2 recommendations target same device_id, keep the higher-impact one.

        Recommendations without a device_id are passed through untouched.
        """
        best: dict[str, ActionRecommendation] = {}
        passthrough: list[ActionRecommendation] = []
        for rec in recs:
            device = rec.one_click_payload.get("device_id") if rec.one_click_payload else None
            if not device:
                passthrough.append(rec)
                continue
            current = best.get(device)
            if current is None or rec.impact_inr_month > current.impact_inr_month:
                best[device] = rec
        return list(best.values()) + passthrough

    def _rank(self, recs: list[ActionRecommendation]) -> list[ActionRecommendation]:
        """Sort by impact_inr_month * confidence, descending; stable."""
        return sorted(
            recs,
            key=lambda r: r.impact_inr_month * r.confidence,
            reverse=True,
        )
