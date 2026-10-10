"""Vs-prior-period comparator for KPI deltas.

Pure data math — no ML, no LLM. Given a time-series dataframe (or a pair of
pre-split series), compute the change versus the equivalent prior period and
decorate it with direction / sentiment / display label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class DeltaResult:
    current: float
    prior: float
    pct_change: float
    abs_change: float
    direction: Literal["up", "down", "flat"]
    sentiment: Literal["good", "bad", "neutral"]
    arrow: str
    label: str


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


# Movements smaller than this are treated as "flat" (direction classification
# tolerance, expressed in percent).
_FLAT_TOLERANCE_PCT = 0.01

_ARROWS = {"up": "↗", "down": "↘", "flat": "→"}

_PERIOD_LABELS = {
    "day": "yesterday",
    "week": "last week",
    "month": "last month",
    "quarter": "last quarter",
    "year": "last year",
}


def _empty_result() -> DeltaResult:
    return DeltaResult(
        current=0.0,
        prior=0.0,
        pct_change=0.0,
        abs_change=0.0,
        direction="flat",
        sentiment="neutral",
        arrow=_ARROWS["flat"],
        label="0.0% vs last period",
    )


def _format_pct(pct_change: float) -> str:
    if pct_change == float("inf"):
        return "+∞%"
    if pct_change == float("-inf"):
        return "-∞%"
    sign = "+" if pct_change >= 0 else ""
    return f"{sign}{pct_change:.1f}%"


def _classify(
    current: float,
    prior: float,
    higher_is: str,
    period_label: str,
) -> DeltaResult:
    abs_change = current - prior

    if prior == 0:
        if current == 0:
            pct_change = 0.0
            direction: Literal["up", "down", "flat"] = "flat"
        elif current > 0:
            pct_change = float("inf")
            direction = "up"
        else:
            pct_change = float("-inf")
            direction = "down"
    else:
        pct_change = (abs_change / abs(prior)) * 100.0
        if abs(pct_change) < _FLAT_TOLERANCE_PCT:
            direction = "flat"
        elif current > prior:
            direction = "up"
        else:
            direction = "down"

    if direction == "flat":
        sentiment: Literal["good", "bad", "neutral"] = "neutral"
    elif direction == "up":
        sentiment = "good" if higher_is == "good" else "bad"
    else:
        sentiment = "bad" if higher_is == "good" else "good"

    arrow = _ARROWS[direction]
    label = f"{_format_pct(pct_change)} vs {period_label}"

    return DeltaResult(
        current=float(current),
        prior=float(prior),
        pct_change=pct_change,
        abs_change=float(abs_change),
        direction=direction,
        sentiment=sentiment,
        arrow=arrow,
        label=label,
    )


def _period_ranges(now: pd.Timestamp, period: str):
    """Return (cur_start, cur_end, prior_start, prior_end) half-open ranges."""

    if period == "day":
        cur_start = now.normalize()
        cur_end = cur_start + pd.Timedelta(days=1)
        prior_start = cur_start - pd.Timedelta(days=1)
        prior_end = cur_start
    elif period == "week":
        cur_start = (now - pd.Timedelta(days=now.weekday())).normalize()
        cur_end = cur_start + pd.Timedelta(days=7)
        prior_start = cur_start - pd.Timedelta(days=7)
        prior_end = cur_start
    elif period == "month":
        cur_start = now.normalize().replace(day=1)
        if cur_start.month == 12:
            cur_end = cur_start.replace(year=cur_start.year + 1, month=1)
        else:
            cur_end = cur_start.replace(month=cur_start.month + 1)
        if cur_start.month == 1:
            prior_start = cur_start.replace(year=cur_start.year - 1, month=12)
        else:
            prior_start = cur_start.replace(month=cur_start.month - 1)
        prior_end = cur_start
    elif period == "quarter":
        quarter = (now.month - 1) // 3  # 0..3
        cur_start = now.normalize().replace(month=quarter * 3 + 1, day=1)
        if quarter == 3:
            cur_end = cur_start.replace(year=cur_start.year + 1, month=1)
        else:
            cur_end = cur_start.replace(month=(quarter + 1) * 3 + 1)
        if quarter == 0:
            prior_start = cur_start.replace(year=cur_start.year - 1, month=10)
        else:
            prior_start = cur_start.replace(month=(quarter - 1) * 3 + 1)
        prior_end = cur_start
    elif period == "year":
        cur_start = now.normalize().replace(month=1, day=1)
        cur_end = cur_start.replace(year=cur_start.year + 1)
        prior_start = cur_start.replace(year=cur_start.year - 1)
        prior_end = cur_start
    else:
        raise ValueError(f"Unknown period: {period!r}")

    return cur_start, cur_end, prior_start, prior_end


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_delta(
    df: pd.DataFrame,
    period: Literal["day", "week", "month", "quarter", "year"] = "month",
    higher_is: Literal["good", "bad"] = "bad",
    now: Optional[pd.Timestamp] = None,
) -> DeltaResult:
    """Compute delta of ``df['value']`` for the current ``period`` vs the prior one."""

    if df is None or len(df) == 0:
        return _empty_result()

    if now is None:
        now = pd.Timestamp.now()

    ts = pd.to_datetime(df["ts"])
    values = df["value"].astype(float).reset_index(drop=True)
    ts = ts.reset_index(drop=True)

    # Normalize tz: align the series and `now` so comparisons never raise.
    if ts.dt.tz is not None and now.tz is None:
        now = now.tz_localize(ts.dt.tz)
    elif ts.dt.tz is None and now.tz is not None:
        ts = ts.dt.tz_localize(now.tz)

    cur_start, cur_end, prior_start, prior_end = _period_ranges(now, period)

    cur_mask = (ts >= cur_start) & (ts < cur_end)
    prior_mask = (ts >= prior_start) & (ts < prior_end)

    current = float(values[cur_mask].sum())
    prior = float(values[prior_mask].sum())

    return _classify(current, prior, higher_is, _PERIOD_LABELS[period])


def compute_series_delta(
    current: pd.Series,
    prior: pd.Series,
    higher_is: Literal["good", "bad"] = "bad",
) -> DeltaResult:
    """Compute delta from two pre-split series (sums each)."""

    cur_val = float(pd.Series(current, dtype=float).sum())
    prior_val = float(pd.Series(prior, dtype=float).sum())
    return _classify(cur_val, prior_val, higher_is, "last period")


def format_delta_pill(d: DeltaResult) -> str:
    """Return an HTML pill snippet for the given DeltaResult."""

    return (
        f'<span class="delta {d.arrow} {d.sentiment}">'
        f"{d.arrow} {d.label}</span>"
    )
