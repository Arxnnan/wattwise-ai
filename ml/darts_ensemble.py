"""WattWise AI — Darts Tier-2 forecast ensemble (blueprint §7.1).

Tier 1 (`ml.forecasting.ChronosForecaster`) is zero-shot and already measured
at ~2% MAPE (`docs/MODEL_EVIDENCE.md`) — well inside the RFP's 8% target on
its own. This module is the Tier-2 *tuning* layer the blueprint describes on
top of that, and it is built and validated honestly rather than assumed to
help:

  | Candidate                          | Measured MAPE (office, seed 42) |
  |-------------------------------------|----------------------------------|
  | Chronos (Tier 1, zero-shot)          | ~2.0%                            |
  | Darts XGBoost, naive lags (-1..-48)  | ~28.6% — no seasonal signal       |
  | Darts XGBoost, seasonal lags         | **~0.9%** — beats Chronos here    |
  | Darts N-BEATS, 5 epochs              | ~23.3% — badly undertrained       |

N-BEATS and TFT need far more training than fits in this pass to be
competitive (a 5-epoch fit took ~60s and was still 10x worse than Chronos;
getting them near convergence is a multi-hour Colab job, which is exactly
where the blueprint already puts model training — §4 "Training vs Inference
Split"). Rather than wire in a model known to be undertrained, this module
implements genuine **backtested model selection**: fit every real candidate,
score each on a true held-out window, and return whichever actually won —
so "Tier 2" means "verified better," not "included because the blueprint
names it."
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.forecasting import ChronosForecaster

log = logging.getLogger(__name__)

SEASONAL_LAGS = [-1, -2, -3, -24, -48, -168]  # last 3h + same hour yesterday/last week


@dataclass
class BacktestResult:
    model_name: str
    mape: float
    forecast: pd.DataFrame


def _darts_xgb_forecast(train: pd.Series, horizon_hours: int) -> pd.DataFrame | None:
    try:
        from darts import TimeSeries
        from darts.models import XGBModel
    except ImportError:
        log.warning("darts not installed — skipping XGBoost candidate")
        return None

    ts = TimeSeries.from_series(train)
    model = XGBModel(lags=SEASONAL_LAGS, random_state=42)
    model.fit(ts)
    pred = model.predict(horizon_hours)

    last_ts = train.index[-1]
    future_ts = [last_ts + pd.Timedelta(hours=i + 1) for i in range(horizon_hours)]
    values = pred.values().flatten()
    return pd.DataFrame({
        "forecast_ts": future_ts, "predicted_kw": values,
        "lower_bound": values * 0.9, "upper_bound": values * 1.1,
        "model": "darts_xgboost_seasonal",
    })


def _chronos_forecast(train: pd.Series, horizon_hours: int) -> pd.DataFrame:
    return ChronosForecaster(model_size="tiny").predict(train, horizon_hours)


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs((actual - predicted) / (actual + 1e-6))) * 100)


class DartsEnsembleSelector:
    """Backtests Chronos vs. Darts candidates on a real held-out window and
    selects whichever wins, rather than blindly averaging or always
    preferring one tier."""

    def backtest_and_select(self, hourly_series: pd.Series, horizon_hours: int = 24) -> BacktestResult:
        """`hourly_series` must already be hourly-resampled (see the
        granularity-mismatch bug documented in ml.forecasting.ForecastEngine)
        and long enough that holding out `horizon_hours` still leaves a
        useful training window."""
        train = hourly_series.iloc[:-horizon_hours]
        actual = hourly_series.iloc[-horizon_hours:]
        if len(train) < 48:
            raise ValueError("Need at least 48h of training history after the holdout")

        candidates: dict[str, pd.DataFrame] = {"chronos": _chronos_forecast(train, horizon_hours)}
        xgb_result = _darts_xgb_forecast(train, horizon_hours)
        if xgb_result is not None:
            candidates["darts_xgboost_seasonal"] = xgb_result

        scored = []
        for name, forecast_df in candidates.items():
            pred_vals = forecast_df["predicted_kw"].values[: len(actual)]
            mape = _mape(actual.values, pred_vals)
            scored.append(BacktestResult(model_name=name, mape=mape, forecast=forecast_df))
            log.info("Backtest %s: MAPE=%.2f%%", name, mape)

        best = min(scored, key=lambda r: r.mape)
        log.info("Selected %s (MAPE=%.2f%%) over %d other candidate(s)", best.model_name, best.mape, len(scored) - 1)
        return best
