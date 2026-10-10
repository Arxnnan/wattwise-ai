"""Unit tests for ``ml.analytics.severity``.

Covers composite-score weighting, threshold boundaries, facility criticality,
cost-impact log normalization, repeat-count cap, unknown facilities, the
rank_anomalies DataFrame helper and the color/label mapping.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from ml.analytics.severity import (
    FACILITY_CRITICALITY,
    SeverityResult,
    classify_severity,
    rank_anomalies,
)


# ---------------------------------------------------------------------------
# 1. Each weighting component contributes correctly
# ---------------------------------------------------------------------------


def test_components_are_reported_and_weighted():
    # pyod=1.0, datacentre=1.0, cost=10_000 -> 0.5, repeat=5 -> 1.0.
    result = classify_severity(
        pyod_score=1.0,
        facility_id="datacentre",
        estimated_cost_inr=10_000,
        repeat_count=5,
    )
    assert result.components == {
        "pyod": 1.0,
        "facility": 1.0,
        "cost_impact": pytest.approx(0.5, abs=1e-9),
        "repeat": 1.0,
    }
    # 0.4*1 + 0.2*1 + 0.3*0.5 + 0.1*1 = 0.85
    assert result.composite_score == pytest.approx(0.85, abs=1e-9)


def test_pyod_only_contribution():
    result = classify_severity(pyod_score=1.0, facility_id="unknown")
    # 0.4*1 + 0.2*0.3 + 0 + 0 = 0.46
    assert result.composite_score == pytest.approx(0.46, abs=1e-9)
    assert result.components["pyod"] == 1.0


def test_pyod_score_is_clamped():
    low = classify_severity(pyod_score=-0.5, facility_id="office")
    high = classify_severity(pyod_score=2.0, facility_id="office")
    assert low.components["pyod"] == 0.0
    assert high.components["pyod"] == 1.0


# ---------------------------------------------------------------------------
# 2. critical / major / minor threshold boundaries
# ---------------------------------------------------------------------------


def test_critical_threshold_boundary_at_0_75():
    # pyod=1, datacentre=1, cost=10k->0.5, repeat=0 ==> 0.75 exactly.
    result = classify_severity(
        pyod_score=1.0,
        facility_id="datacentre",
        estimated_cost_inr=10_000,
    )
    assert result.composite_score == pytest.approx(0.75, abs=1e-9)
    assert result.severity == "critical"


def test_just_below_critical_is_major():
    result = classify_severity(
        pyod_score=0.99,
        facility_id="datacentre",
        estimated_cost_inr=10_000,
    )
    assert result.composite_score < 0.75
    assert result.severity == "major"


def test_major_threshold_boundary_at_0_45():
    # pyod=0.725, office=0.3, cost=0, repeat=5 -> 0.29 + 0.06 + 0.1 = 0.45
    result = classify_severity(
        pyod_score=0.725,
        facility_id="office",
        estimated_cost_inr=0,
        repeat_count=5,
    )
    assert result.composite_score == pytest.approx(0.45, abs=1e-6)
    assert result.severity == "major"


def test_just_below_major_is_minor():
    result = classify_severity(
        pyod_score=0.725,
        facility_id="office",
        estimated_cost_inr=0,
        repeat_count=4,
    )
    assert result.composite_score < 0.45
    assert result.severity == "minor"


def test_all_zero_is_minor():
    result = classify_severity(pyod_score=0.0, facility_id="office")
    assert result.severity == "minor"
    assert result.composite_score == pytest.approx(0.06, abs=1e-9)


# ---------------------------------------------------------------------------
# 3. Facility criticality ordering (datacentre > warehouse > office)
# ---------------------------------------------------------------------------


def test_facility_criticality_ordering():
    assert FACILITY_CRITICALITY["datacentre"] > FACILITY_CRITICALITY["warehouse"]
    assert FACILITY_CRITICALITY["warehouse"] > FACILITY_CRITICALITY["office"]

    dc = classify_severity(pyod_score=0.5, facility_id="datacentre")
    wh = classify_severity(pyod_score=0.5, facility_id="warehouse")
    of = classify_severity(pyod_score=0.5, facility_id="office")
    assert dc.composite_score > wh.composite_score > of.composite_score
    assert dc.components["facility"] == 1.0
    assert wh.components["facility"] == 0.6
    assert of.components["facility"] == 0.3


# ---------------------------------------------------------------------------
# 4. Cost impact log normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cost, expected",
    [
        (0, 0.0),
        (10_000, 0.5),
        (100_000, 1.0),
        (1_000_000, 1.0),  # saturates
    ],
)
def test_cost_impact_log_scale(cost, expected):
    result = classify_severity(
        pyod_score=0.0,
        facility_id="office",
        estimated_cost_inr=cost,
    )
    assert result.components["cost_impact"] == pytest.approx(expected, abs=1e-9)


def test_cost_impact_intermediate_value_is_monotonic():
    low = classify_severity(0.0, "office", estimated_cost_inr=1_000)
    mid = classify_severity(0.0, "office", estimated_cost_inr=30_000)
    high = classify_severity(0.0, "office", estimated_cost_inr=80_000)
    assert low.components["cost_impact"] < mid.components["cost_impact"] < high.components["cost_impact"]


# ---------------------------------------------------------------------------
# 5. Repeat count cap at 5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count, expected",
    [
        (0, 0.0),
        (3, 0.6),
        (5, 1.0),
        (10, 1.0),  # capped
        (-2, 0.0),  # negatives ignored
    ],
)
def test_repeat_bonus_cap(count, expected):
    result = classify_severity(
        pyod_score=0.0,
        facility_id="office",
        repeat_count=count,
    )
    assert result.components["repeat"] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# 6. Unknown facility_id defaults to 0.3 (office-level)
# ---------------------------------------------------------------------------


def test_unknown_facility_defaults_to_office_level():
    unknown = classify_severity(pyod_score=0.5, facility_id="atlantis")
    office = classify_severity(pyod_score=0.5, facility_id="office")
    assert unknown.components["facility"] == 0.3
    assert unknown.composite_score == pytest.approx(office.composite_score, abs=1e-9)


# ---------------------------------------------------------------------------
# 7. Zero PyOD + high cost still can be major
# ---------------------------------------------------------------------------


def test_zero_pyod_with_high_cost_can_be_major():
    result = classify_severity(
        pyod_score=0.0,
        facility_id="datacentre",
        estimated_cost_inr=1_000_000,  # cost component saturates to 1.0
    )
    # 0 + 0.2*1 + 0.3*1 + 0 = 0.5
    assert result.composite_score == pytest.approx(0.5, abs=1e-9)
    assert result.severity == "major"


# ---------------------------------------------------------------------------
# 8. rank_anomalies with empty DataFrame
# ---------------------------------------------------------------------------


def test_rank_anomalies_empty_dataframe():
    empty = pd.DataFrame(columns=["pyod_score", "facility_id"])
    out = rank_anomalies(empty)
    assert out.empty
    assert "severity" in out.columns
    assert "severity_score" in out.columns


def test_rank_anomalies_none_input():
    out = rank_anomalies(None)
    assert out.empty
    assert list(out.columns) == ["severity", "severity_score"]


# ---------------------------------------------------------------------------
# 9. rank_anomalies ordering (highest severity first)
# ---------------------------------------------------------------------------


def test_rank_anomalies_sorts_descending_and_adds_columns():
    df = pd.DataFrame(
        [
            {
                "id": "a-low",
                "pyod_score": 0.1,
                "facility_id": "office",
                "estimated_cost_inr": 0,
                "repeat_count": 0,
            },
            {
                "id": "a-high",
                "pyod_score": 1.0,
                "facility_id": "datacentre",
                "estimated_cost_inr": 100_000,
                "repeat_count": 5,
            },
            {
                "id": "a-mid",
                "pyod_score": 0.7,
                "facility_id": "warehouse",
                "estimated_cost_inr": 10_000,
                "repeat_count": 1,
            },
        ]
    )
    out = rank_anomalies(df)
    # Preserved id column and sorted descending by severity_score.
    assert list(out["id"]) == ["a-high", "a-mid", "a-low"]
    assert list(out["severity"]) == ["critical", "major", "minor"]
    assert out["severity_score"].is_monotonic_decreasing


def test_rank_anomalies_missing_optional_columns_default_to_zero():
    df = pd.DataFrame(
        [
            {"pyod_score": 0.9, "facility_id": "datacentre"},
            {"pyod_score": 0.1, "facility_id": "office"},
        ]
    )
    out = rank_anomalies(df)
    assert len(out) == 2
    assert out["severity_score"].iloc[0] > out["severity_score"].iloc[1]


def test_rank_anomalies_handles_none_optional_values():
    df = pd.DataFrame(
        [
            {
                "pyod_score": None,
                "facility_id": "office",
                "estimated_cost_inr": None,
                "repeat_count": None,
            }
        ]
    )
    out = rank_anomalies(df)
    # All optional components default to zero; office facility => 0.06 composite.
    assert out["severity_score"].iloc[0] == pytest.approx(0.06, abs=1e-9)
    assert out["severity"].iloc[0] == "minor"


def test_rank_anomalies_handles_garbage_optional_values():
    df = pd.DataFrame(
        [
            {
                "pyod_score": 0.9,
                "facility_id": "datacentre",
                "estimated_cost_inr": "not-a-number",
                "repeat_count": "nope",
            }
        ]
    )
    out = rank_anomalies(df)
    # Unparseable optional cells default to 0 -> 0.4*0.9 + 0.2*1.0 = 0.56 major.
    assert out["severity_score"].iloc[0] == pytest.approx(0.56, abs=1e-9)
    assert out["severity"].iloc[0] == "major"


def test_rank_anomalies_handles_nan_optional_values():
    df = pd.DataFrame(
        [
            {
                "pyod_score": 0.8,
                "facility_id": "datacentre",
                "estimated_cost_inr": math.nan,
                "repeat_count": math.nan,
            }
        ]
    )
    out = rank_anomalies(df)
    # NaN cost / repeat must coerce to zero without blowing up.
    assert len(out) == 1
    assert out["severity"].iloc[0] in {"critical", "major", "minor"}


# ---------------------------------------------------------------------------
# 10. Color + label mapping for each severity
# ---------------------------------------------------------------------------


def test_critical_color_and_label():
    result = classify_severity(
        pyod_score=1.0,
        facility_id="datacentre",
        estimated_cost_inr=100_000,
        repeat_count=5,
    )
    assert result.severity == "critical"
    assert result.color == "#e85d4f"
    assert result.label == "Critical"
    assert "critical" in result.reason
    assert "datacentre" in result.reason


def test_major_color_and_label():
    result = classify_severity(
        pyod_score=0.0,
        facility_id="datacentre",
        estimated_cost_inr=1_000_000,
    )
    assert result.severity == "major"
    assert result.color == "#e0a93d"
    assert result.label == "Major"
    assert "major" in result.reason


def test_minor_color_and_label():
    result = classify_severity(pyod_score=0.0, facility_id="office")
    assert result.severity == "minor"
    assert result.color == "#8ca0a0"
    assert result.label == "Minor"
    assert "minor" in result.reason


def test_severity_result_is_dataclass_instance():
    result = classify_severity(pyod_score=0.5, facility_id="office")
    assert isinstance(result, SeverityResult)
    assert 0.0 <= result.composite_score <= 1.0
