"""Unit tests for ml.analytics.comparator — targeting 100% coverage."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from ml.analytics.comparator import (
    DeltaResult,
    compute_delta,
    compute_series_delta,
    format_delta_pill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_df(records):
    """records: iterable of (iso_timestamp, value)."""
    return pd.DataFrame(
        {"ts": [pd.Timestamp(t) for t, _ in records], "value": [v for _, v in records]}
    )


# ---------------------------------------------------------------------------
# 1. day / week / month / quarter / year period math
# ---------------------------------------------------------------------------


def test_period_day():
    now = pd.Timestamp("2026-03-15 10:00:00")
    df = _mk_df([
        ("2026-03-15 02:00:00", 10),   # today -> current
        ("2026-03-15 20:00:00", 5),    # today -> current
        ("2026-03-14 09:00:00", 8),    # yesterday -> prior
        ("2026-03-13 09:00:00", 99),   # ignored
    ])
    r = compute_delta(df, period="day", now=now, higher_is="bad")
    assert r.current == 15.0
    assert r.prior == 8.0
    assert r.direction == "up"
    assert r.sentiment == "bad"  # higher_is=bad, so up is bad


def test_period_week():
    # 2026-03-15 is a Sunday; weekday()==6 so week starts Monday 2026-03-09.
    now = pd.Timestamp("2026-03-15 10:00:00")
    df = _mk_df([
        ("2026-03-09 09:00:00", 10),   # current week (Mon)
        ("2026-03-15 09:00:00", 4),    # current week (Sun)
        ("2026-03-02 09:00:00", 7),    # prior week
        ("2026-03-08 23:00:00", 3),    # prior week (last Sun)
        ("2026-02-23 09:00:00", 50),   # ignored
    ])
    r = compute_delta(df, period="week", now=now)
    assert r.current == 14.0
    assert r.prior == 10.0


def test_period_month_mid_year():
    now = pd.Timestamp("2026-07-20")
    df = _mk_df([
        ("2026-07-01", 10),
        ("2026-07-31 23:00:00", 5),
        ("2026-06-15", 20),
        ("2026-05-31", 999),
    ])
    r = compute_delta(df, period="month", now=now)
    assert r.current == 15.0
    assert r.prior == 20.0
    assert r.direction == "down"


def test_period_month_december_edge():
    """Dec current -> next period crosses into Jan+1; Nov is prior."""
    now = pd.Timestamp("2026-12-10")
    df = _mk_df([
        ("2026-12-05", 3),
        ("2026-11-28", 2),
        ("2027-01-01", 999),  # excluded
    ])
    r = compute_delta(df, period="month", now=now)
    assert r.current == 3.0
    assert r.prior == 2.0


def test_period_month_january_edge():
    """Jan current -> prior crosses into previous Dec."""
    now = pd.Timestamp("2026-01-15")
    df = _mk_df([
        ("2026-01-05", 7),
        ("2025-12-20", 4),
        ("2025-11-30", 999),  # excluded
    ])
    r = compute_delta(df, period="month", now=now)
    assert r.current == 7.0
    assert r.prior == 4.0


def test_period_quarter_q0():
    """Q1 (Jan-Mar); prior is Q4 of previous year."""
    now = pd.Timestamp("2026-02-10")
    df = _mk_df([
        ("2026-01-15", 10),
        ("2026-03-31", 5),
        ("2025-10-15", 2),
        ("2025-12-31", 3),
        ("2025-09-30", 999),  # excluded
    ])
    r = compute_delta(df, period="quarter", now=now)
    assert r.current == 15.0
    assert r.prior == 5.0


def test_period_quarter_mid():
    """Q2 (Apr-Jun); prior is Q1."""
    now = pd.Timestamp("2026-05-10")
    df = _mk_df([
        ("2026-04-01", 10),
        ("2026-06-30", 2),
        ("2026-01-15", 4),
        ("2026-03-31", 1),
    ])
    r = compute_delta(df, period="quarter", now=now)
    assert r.current == 12.0
    assert r.prior == 5.0


def test_period_quarter_q3():
    """Q4 (Oct-Dec); current crosses into next year."""
    now = pd.Timestamp("2026-11-05")
    df = _mk_df([
        ("2026-10-01", 6),
        ("2026-12-31", 4),
        ("2026-07-05", 5),  # prior Q3
    ])
    r = compute_delta(df, period="quarter", now=now)
    assert r.current == 10.0
    assert r.prior == 5.0


def test_period_year():
    now = pd.Timestamp("2026-07-04")
    df = _mk_df([
        ("2026-01-01", 10),
        ("2026-12-31", 5),
        ("2025-06-15", 20),
        ("2024-01-01", 999),
    ])
    r = compute_delta(df, period="year", now=now)
    assert r.current == 15.0
    assert r.prior == 20.0


def test_period_invalid_raises():
    now = pd.Timestamp("2026-07-04")
    df = _mk_df([("2026-07-01", 1)])
    with pytest.raises(ValueError):
        compute_delta(df, period="decade", now=now)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. higher_is="good" vs higher_is="bad" sentiment flipping
# ---------------------------------------------------------------------------


def test_higher_is_bad_up_is_bad():
    r = compute_series_delta(pd.Series([100.0]), pd.Series([50.0]), higher_is="bad")
    assert r.direction == "up"
    assert r.sentiment == "bad"


def test_higher_is_good_up_is_good():
    r = compute_series_delta(pd.Series([100.0]), pd.Series([50.0]), higher_is="good")
    assert r.direction == "up"
    assert r.sentiment == "good"


def test_higher_is_bad_down_is_good():
    r = compute_series_delta(pd.Series([50.0]), pd.Series([100.0]), higher_is="bad")
    assert r.direction == "down"
    assert r.sentiment == "good"


def test_higher_is_good_down_is_bad():
    r = compute_series_delta(pd.Series([50.0]), pd.Series([100.0]), higher_is="good")
    assert r.direction == "down"
    assert r.sentiment == "bad"


# ---------------------------------------------------------------------------
# 3. Division by zero (prior = 0)
# ---------------------------------------------------------------------------


def test_prior_zero_current_positive_inf():
    r = compute_series_delta(pd.Series([42.0]), pd.Series([0.0]), higher_is="bad")
    assert r.pct_change == float("inf")
    assert r.direction == "up"
    assert "∞" in r.label  # infinity sign in label


def test_prior_zero_current_negative_neginf():
    r = compute_series_delta(pd.Series([-7.0]), pd.Series([0.0]), higher_is="bad")
    assert r.pct_change == float("-inf")
    assert r.direction == "down"
    assert "-∞" in r.label


def test_prior_zero_current_zero_is_flat():
    r = compute_series_delta(pd.Series([0.0]), pd.Series([0.0]))
    assert r.pct_change == 0.0
    assert r.direction == "flat"
    assert r.sentiment == "neutral"


# ---------------------------------------------------------------------------
# 4. Empty dataframe
# ---------------------------------------------------------------------------


def test_empty_dataframe_returns_zeros():
    df = pd.DataFrame({"ts": [], "value": []})
    r = compute_delta(df)
    assert r.current == 0.0 and r.prior == 0.0
    assert r.direction == "flat"
    assert r.sentiment == "neutral"
    assert r.arrow == "→"


def test_none_dataframe_returns_zeros():
    r = compute_delta(None)  # type: ignore[arg-type]
    assert r.direction == "flat"
    assert r.sentiment == "neutral"


# ---------------------------------------------------------------------------
# 5. tz-aware vs tz-naive timestamps
# ---------------------------------------------------------------------------


def test_tz_aware_df_tz_naive_now():
    now = pd.Timestamp("2026-07-15")  # naive
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-07-05", "2026-06-10"], utc=True),
        "value": [3.0, 1.0],
    })
    r = compute_delta(df, period="month", now=now)
    assert r.current == 3.0
    assert r.prior == 1.0


def test_tz_naive_df_tz_aware_now():
    now = pd.Timestamp("2026-07-15", tz="UTC")
    df = _mk_df([("2026-07-05", 4), ("2026-06-10", 2)])
    r = compute_delta(df, period="month", now=now)
    assert r.current == 4.0
    assert r.prior == 2.0


def test_tz_aware_both():
    now = pd.Timestamp("2026-07-15", tz="UTC")
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-07-05", "2026-06-10"], utc=True),
        "value": [7.0, 3.0],
    })
    r = compute_delta(df, period="month", now=now)
    assert r.current == 7.0
    assert r.prior == 3.0


# ---------------------------------------------------------------------------
# 6. Negative values (cost reduction, etc.)
# ---------------------------------------------------------------------------


def test_negative_values_cost_reduction():
    # current=-20 (savings), prior=-10 → more negative = "down" numerically
    r = compute_series_delta(pd.Series([-20.0]), pd.Series([-10.0]), higher_is="bad")
    assert r.abs_change == -10.0
    assert r.direction == "down"
    assert r.sentiment == "good"  # higher_is=bad, so down is good
    # pct_change should be (-10 / 10) * 100 = -100
    assert r.pct_change == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# 7. format_delta_pill output HTML structure
# ---------------------------------------------------------------------------


def test_format_delta_pill_up_good():
    r = compute_series_delta(pd.Series([120.0]), pd.Series([100.0]), higher_is="good")
    html = format_delta_pill(r)
    assert html.startswith('<span class="delta ')
    assert html.endswith("</span>")
    assert "↗" in html  # up arrow
    assert "good" in html
    assert "+20.0% vs last period" in html


def test_format_delta_pill_down_bad():
    r = compute_series_delta(pd.Series([80.0]), pd.Series([100.0]), higher_is="good")
    html = format_delta_pill(r)
    assert "↘" in html  # down arrow
    assert "bad" in html


def test_format_delta_pill_flat_neutral():
    r = compute_series_delta(pd.Series([0.0]), pd.Series([0.0]))
    html = format_delta_pill(r)
    assert "→" in html
    assert "neutral" in html


# ---------------------------------------------------------------------------
# 8. Series-based variant (compute_series_delta)
# ---------------------------------------------------------------------------


def test_compute_series_delta_basic():
    r = compute_series_delta(pd.Series([10.0, 20.0]), pd.Series([5.0, 5.0]))
    assert r.current == 30.0
    assert r.prior == 10.0
    assert r.pct_change == pytest.approx(200.0)
    assert r.direction == "up"
    assert r.label == "+200.0% vs last period"


def test_compute_series_delta_empty_series():
    r = compute_series_delta(pd.Series([], dtype=float), pd.Series([], dtype=float))
    assert r.current == 0.0 and r.prior == 0.0
    assert r.direction == "flat"


# ---------------------------------------------------------------------------
# 9. `now` override for deterministic tests
# ---------------------------------------------------------------------------


def test_now_defaults_to_timestamp_now(monkeypatch):
    """When now=None, pd.Timestamp.now() is used — exercise that code path."""
    frozen = pd.Timestamp("2026-05-15")
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls: frozen))
    df = _mk_df([("2026-05-10", 5), ("2026-04-10", 2)])
    r = compute_delta(df, period="month")
    assert r.current == 5.0
    assert r.prior == 2.0


def test_now_override_is_deterministic():
    now = pd.Timestamp("2026-03-15")
    df = _mk_df([("2026-03-01", 1), ("2026-02-01", 1)])
    r1 = compute_delta(df, period="month", now=now)
    r2 = compute_delta(df, period="month", now=now)
    assert r1 == r2


# ---------------------------------------------------------------------------
# 10. Direction classification (up/down/flat with 0.01% tolerance)
# ---------------------------------------------------------------------------


def test_direction_flat_below_tolerance():
    # 0.005% change → below 0.01% threshold → flat
    r = compute_series_delta(pd.Series([100.005]), pd.Series([100.0]))
    assert r.direction == "flat"
    assert r.sentiment == "neutral"


def test_direction_up_above_tolerance():
    # 0.02% change → above threshold → up
    r = compute_series_delta(pd.Series([100.02]), pd.Series([100.0]))
    assert r.direction == "up"


def test_direction_down_above_tolerance():
    r = compute_series_delta(pd.Series([99.5]), pd.Series([100.0]))
    assert r.direction == "down"


def test_exact_equal_is_flat():
    r = compute_series_delta(pd.Series([50.0]), pd.Series([50.0]))
    assert r.direction == "flat"
    assert r.pct_change == 0.0


# ---------------------------------------------------------------------------
# Bonus: DeltaResult carries all fields
# ---------------------------------------------------------------------------


def test_delta_result_is_dataclass_with_expected_fields():
    r = compute_series_delta(pd.Series([110.0]), pd.Series([100.0]), higher_is="bad")
    assert isinstance(r, DeltaResult)
    assert r.current == 110.0
    assert r.prior == 100.0
    assert r.abs_change == 10.0
    assert math.isclose(r.pct_change, 10.0)
    assert r.direction == "up"
    assert r.sentiment == "bad"
    assert r.arrow == "↗"
    assert "vs last period" in r.label
