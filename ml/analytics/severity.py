"""Severity ranking for raw anomalies.

Pure math (no AI/LLM): combines a PyOD outlier score, facility criticality,
estimated cost impact, and repeat-event bonus into a single 0-1 composite
score that maps to Critical / Major / Minor buckets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

Severity = Literal["critical", "major", "minor"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FACILITY_CRITICALITY: dict[str, float] = {
    "datacentre": 1.0,  # 24/7 critical - any anomaly matters
    "warehouse": 0.6,   # cold-storage matters, lighting doesn't
    "office": 0.3,      # mostly weekday comfort
}

# Default criticality applied when the facility_id is not registered above.
_DEFAULT_FACILITY_CRITICALITY = 0.3

# Composite-score weights (must sum to 1.0).
_W_PYOD = 0.40
_W_FACILITY = 0.20
_W_COST = 0.30
_W_REPEAT = 0.10

# Threshold boundaries on the composite score. A small epsilon absorbs the
# unavoidable float rounding (e.g. ``0.29 + 0.06 + 0.1`` -> ``0.4499...``)
# so that a composite that is mathematically equal to a threshold is still
# routed to the higher severity, per spec.
_THRESHOLD_CRITICAL = 0.75
_THRESHOLD_MAJOR = 0.45
_THRESHOLD_EPSILON = 1e-9

# Severity presentation.
_SEVERITY_COLOR: dict[str, str] = {
    "critical": "#e85d4f",
    "major": "#e0a93d",
    "minor": "#8ca0a0",
}
_SEVERITY_LABEL: dict[str, str] = {
    "critical": "Critical",
    "major": "Major",
    "minor": "Minor",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class SeverityResult:
    """Result of classifying a single anomaly."""

    severity: Severity
    composite_score: float
    components: dict
    color: str
    label: str
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp01(value: float) -> float:
    """Clamp a value into the [0, 1] range."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _facility_criticality(facility_id: str) -> float:
    """Return criticality for a facility; unknowns default to office-level."""
    return FACILITY_CRITICALITY.get(facility_id, _DEFAULT_FACILITY_CRITICALITY)


def _cost_impact(estimated_cost_inr: float) -> float:
    """Log-normalized cost impact.

    Anchor points: ``10_000`` -> ``0.5``, ``100_000`` -> ``1.0``.
    Values below ~316 return 0 and anything above ~1e5 saturates at 1.0.
    """
    safe_cost = max(float(estimated_cost_inr), 1.0)
    raw = 0.5 * math.log10(safe_cost) - 1.5
    return _clamp01(raw)


def _repeat_bonus(repeat_count: int) -> float:
    """Repeat bonus, capped at 1.0 when count >= 5."""
    if repeat_count <= 0:
        return 0.0
    return min(repeat_count / 5.0, 1.0)


def _bucket(score: float) -> Severity:
    if score >= _THRESHOLD_CRITICAL - _THRESHOLD_EPSILON:
        return "critical"
    if score >= _THRESHOLD_MAJOR - _THRESHOLD_EPSILON:
        return "major"
    return "minor"


def _coerce_float(value, default: float = 0.0) -> float:
    """Convert a cell to float, treating ``None``/``NaN``/garbage as default."""
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result):
        return default
    return result


def _coerce_int(value, default: int = 0) -> int:
    """Convert a cell to int, treating ``None``/``NaN``/garbage as default."""
    return int(_coerce_float(value, float(default)))


def _reason(severity: Severity, score: float, facility_id: str) -> str:
    descriptor = {
        "critical": "High score",
        "major": "Elevated score",
        "minor": "Low score",
    }[severity]
    return f"{descriptor} ({score:.2f}) on {severity} facility ({facility_id})"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_severity(
    pyod_score: float,
    facility_id: str,
    estimated_cost_inr: float = 0.0,
    repeat_count: int = 0,
) -> SeverityResult:
    """Classify a single anomaly into a severity bucket.

    Weights:
      - ``pyod_score``                           0.40
      - ``facility_criticality``                 0.20
      - ``cost_impact`` (log scale, 10k->0.5)    0.30
      - ``repeat_bonus`` (min(count/5, 1))       0.10

    Thresholds: ``>= 0.75`` -> critical, ``>= 0.45`` -> major, else minor.
    """
    pyod_component = _clamp01(float(pyod_score))
    facility_component = _facility_criticality(facility_id)
    cost_component = _cost_impact(estimated_cost_inr)
    repeat_component = _repeat_bonus(int(repeat_count))

    composite = (
        _W_PYOD * pyod_component
        + _W_FACILITY * facility_component
        + _W_COST * cost_component
        + _W_REPEAT * repeat_component
    )
    composite = _clamp01(composite)

    severity = _bucket(composite)
    components = {
        "pyod": pyod_component,
        "facility": facility_component,
        "cost_impact": cost_component,
        "repeat": repeat_component,
    }

    return SeverityResult(
        severity=severity,
        composite_score=composite,
        components=components,
        color=_SEVERITY_COLOR[severity],
        label=_SEVERITY_LABEL[severity],
        reason=_reason(severity, composite, facility_id),
    )


def rank_anomalies(anomaly_rows: pd.DataFrame) -> pd.DataFrame:
    """Append ``severity`` and ``severity_score`` columns, sort descending.

    Expected columns on the input DataFrame:
      - ``pyod_score``
      - ``facility_id``
      - ``estimated_cost_inr`` (optional, default 0.0)
      - ``repeat_count`` (optional, default 0)
    """
    if anomaly_rows is None or anomaly_rows.empty:
        out = anomaly_rows.copy() if anomaly_rows is not None else pd.DataFrame()
        out["severity"] = pd.Series(dtype="object")
        out["severity_score"] = pd.Series(dtype="float64")
        return out

    scores: list[float] = []
    severities: list[str] = []

    for _, row in anomaly_rows.iterrows():
        result = classify_severity(
            pyod_score=_coerce_float(row.get("pyod_score", 0.0)),
            facility_id=str(row.get("facility_id", "")),
            estimated_cost_inr=_coerce_float(row.get("estimated_cost_inr", 0.0)),
            repeat_count=_coerce_int(row.get("repeat_count", 0)),
        )
        scores.append(result.composite_score)
        severities.append(result.severity)

    out = anomaly_rows.copy()
    out["severity"] = severities
    out["severity_score"] = scores
    return out.sort_values("severity_score", ascending=False).reset_index(drop=True)
