"""WattWise AI — Forensic Drill-Down Agent.

When a user clicks on an anomaly dot in a chart, this agent produces a full
"forensic card" explaining:
    - WHY the anomaly was flagged (PyOD ensemble scores in plain English)
    - A hypothesis for the root cause (LLM-generated, template fallback)
    - A recommended action
    - A confidence note based on how well historical events match
    - A draft ServiceNow-style work-order description

The user reads this card and decides what to do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    import pandas as pd


# ───────────────────────────── Dataclass ─────────────────────────────

@dataclass
class ForensicCard:
    anomaly_id: str
    anomaly_timestamp: datetime
    facility_id: str
    device_id: str
    observed_value: float
    expected_value: float

    # The AI reasoning chain
    why_flagged: str = ""
    hypothesis: str = ""
    recommended_action: str = ""
    confidence_note: str = ""

    # Historical context
    similar_past_events: list[dict] = field(default_factory=list)
    repeat_count_90d: int = 0

    # Draft work order (for one-click copy)
    work_order_draft: str = ""

    # Metadata
    severity: Literal["critical", "major", "minor"] = "minor"
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    llm_source: Literal["llm", "template"] = "template"


# ───────────────────────────── Agent ─────────────────────────────

class ForensicAgent:
    """Produces drill-down forensic cards for individual anomalies."""

    def __init__(self, llm_provider=None):
        from ml.agents.llm_provider import get_llm_provider
        self._provider = llm_provider or get_llm_provider()

    # ----- public entry -----

    def forensic(
        self,
        anomaly_id: str,
        anomaly_timestamp: datetime,
        facility_id: str,
        device_id: str,
        observed_value: float,
        expected_value: float,
        pyod_scores: dict,
        historical_anomalies: "Optional[pd.DataFrame]" = None,
        severity: Literal["critical", "major", "minor"] = "minor",
    ) -> ForensicCard:
        """Main entry — produces the full forensic card."""
        similar_past = self._find_similar_past(device_id, observed_value, historical_anomalies)
        why = self._why_flagged(pyod_scores)

        # Try LLM, fall back to template
        hypothesis: str
        llm_source: Literal["llm", "template"] = "template"
        if self._provider is not None and getattr(self._provider, "is_available", lambda: False)():
            try:
                hypothesis = self._hypothesis_llm(
                    device_id, observed_value, expected_value, similar_past
                )
                llm_source = "llm"
            except Exception:
                hypothesis = self._hypothesis_template(device_id, observed_value, expected_value)
        else:
            hypothesis = self._hypothesis_template(device_id, observed_value, expected_value)

        action = self._recommended_action(hypothesis, device_id)
        confidence = self._confidence_note(similar_past)
        repeat_count = len(similar_past)

        card = ForensicCard(
            anomaly_id=anomaly_id,
            anomaly_timestamp=anomaly_timestamp,
            facility_id=facility_id,
            device_id=device_id,
            observed_value=observed_value,
            expected_value=expected_value,
            why_flagged=why,
            hypothesis=hypothesis,
            recommended_action=action,
            confidence_note=confidence,
            similar_past_events=similar_past,
            repeat_count_90d=repeat_count,
            severity=severity,
            llm_source=llm_source,
        )
        card.work_order_draft = self._work_order_draft(card)
        return card

    # ----- helpers -----

    def _find_similar_past(
        self,
        device_id: str,
        observed_value: float,
        historical: "Optional[pd.DataFrame]",
    ) -> list[dict]:
        """Return the top 3 similar past events (by device + value similarity)."""
        if historical is None or historical.empty:
            return []

        df = historical.copy()
        if "device_id" in df.columns:
            df = df[df["device_id"] == device_id]
        if df.empty:
            return []

        if "observed_value" in df.columns:
            df["_distance"] = (df["observed_value"] - observed_value).abs()
            df = df.sort_values("_distance")

        df = df.head(3)
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append({
                "id": row.get("id", ""),
                "date": row.get("date", ""),
                "resolution": row.get("resolution", ""),
                "resolved_by": row.get("resolved_by", ""),
            })
        return results

    def _why_flagged(self, pyod_scores: dict) -> str:
        """Plain-English explanation of the PyOD ensemble scores."""
        if not pyod_scores:
            return "PyOD ensemble flagged this point (no detailed scores available)."
        parts = [f"{name.upper()} {score:.2f}" for name, score in pyod_scores.items()]
        joined = ", ".join(parts)
        max_score = max(pyod_scores.values())
        return (
            f"PyOD ensemble triggered: {joined}. "
            f"Peak score {max_score:.2f} exceeds the 0.80 anomaly threshold, "
            f"indicating a statistically significant deviation."
        )

    def _hypothesis_llm(
        self,
        device_id: str,
        observed_value: float,
        expected_value: float,
        similar_past: list[dict],
    ) -> str:
        """LLM-generated hypothesis of root cause."""
        past_summary = "; ".join(
            f"{e.get('date', '?')}: {e.get('resolution', '?')}"
            for e in similar_past[:3]
        ) or "no similar past incidents on record"
        prompt = (
            f"You are a facility engineering assistant. Device '{device_id}' reported "
            f"an observed value of {observed_value:.2f} vs expected {expected_value:.2f}. "
            f"Similar past incidents: {past_summary}. "
            f"In 2-3 sentences, state the most likely root-cause hypothesis."
        )
        text = self._provider.generate(prompt)
        return (text or "").strip()

    def _hypothesis_template(
        self,
        device_id: str,
        observed_value: float,
        expected_value: float,
    ) -> str:
        """Fallback hypothesis using heuristic rules on the device id."""
        delta = observed_value - expected_value
        direction = "above" if delta >= 0 else "below"
        dev_lower = (device_id or "").lower()

        if "hvac" in dev_lower:
            root = (
                "Likely HVAC setpoint drift or clogged filter restricting airflow. "
                "Signature matches thermal-load imbalance seen on rooftop units."
            )
        elif "compressor" in dev_lower:
            root = (
                "Likely stuck compressor contactor or refrigerant short-cycling. "
                "Signature matches contactor-weld faults observed previously."
            )
        elif "pump" in dev_lower:
            root = (
                "Likely pump cavitation or impeller fouling. "
                "Signature matches reduced flow with elevated motor draw."
            )
        elif "chiller" in dev_lower:
            root = (
                "Likely chiller approach-temperature degradation or fouled condenser. "
                "Signature matches reduced heat-rejection capacity."
            )
        else:
            root = (
                "Likely sensor drift, equipment fault, or anomalous occupancy. "
                "Signature does not match a known device-specific failure mode."
            )
        return f"{root} Reading is {abs(delta):.2f} units {direction} the expected baseline."

    def _recommended_action(self, hypothesis: str, device_id: str) -> str:
        """Draft action text referencing the device and the hypothesis."""
        dev_lower = (device_id or "").lower()
        if "hvac" in dev_lower or "compressor" in dev_lower or "chiller" in dev_lower:
            crew = "HVAC technician"
        elif "pump" in dev_lower:
            crew = "mechanical maintenance technician"
        else:
            crew = "facilities technician"
        return (
            f"Dispatch {crew} to inspect {device_id}. "
            f"Context: {hypothesis}"
        )

    def _confidence_note(self, similar_past: list[dict]) -> str:
        """Self-assessed confidence based on past-event match rate.

        0 past events → low confidence (no prior evidence)
        1-2 past events → medium confidence
        3+ past events → high confidence
        """
        n = len(similar_past)
        if n == 0:
            return "Low confidence — no similar past incidents on record for this device."
        if n <= 2:
            resolved = sum(1 for e in similar_past if e.get("resolution"))
            return (
                f"Medium confidence — {resolved} of {n} similar past incidents "
                "were resolved via the suggested action."
            )
        resolved = sum(1 for e in similar_past if e.get("resolution"))
        return (
            f"High confidence — {resolved} of {n} similar past incidents "
            "match this signature and were resolved via the suggested action."
        )

    def _work_order_draft(self, card: ForensicCard) -> str:
        """Multi-line text ready to paste into ServiceNow."""
        ts = card.anomaly_timestamp.isoformat() if hasattr(card.anomaly_timestamp, "isoformat") else str(card.anomaly_timestamp)
        priority_map = {"critical": "P1", "major": "P2", "minor": "P3"}
        priority = priority_map.get(card.severity, "P3")
        return (
            f"Title: Anomaly {card.anomaly_id} on {card.device_id}\n"
            f"Facility: {card.facility_id}\n"
            f"Device: {card.device_id}\n"
            f"Timestamp: {ts}\n"
            f"Observed signature: observed={card.observed_value:.2f}, "
            f"expected={card.expected_value:.2f}\n"
            f"Why flagged: {card.why_flagged}\n"
            f"Hypothesis: {card.hypothesis}\n"
            f"Suggested fix: {card.recommended_action}\n"
            f"Confidence: {card.confidence_note}\n"
            f"Priority: {priority}"
        )
