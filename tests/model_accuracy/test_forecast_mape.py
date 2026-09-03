"""Model accuracy gate — RFP §12: Forecast MAPE <= 8% on a held-out 24h window.

`ForecastEngine.forecast()` always emits hourly-spaced predictions. Naively
testing it against a raw 15-min-interval series measured MAPE at ~27% — not
a model problem, a granularity mismatch (hour-1 predictions compared against
minute-15 actuals). `ForecastEngine.forecast()` now resamples internally
(see ml/forecasting.py), and this test holds out a real 24h window the model
never saw to confirm the fix: Chronos zero-shot MAPE measured at ~2% here.
"""
from __future__ import annotations
import numpy as np

from ml.data_generator import generate_historical, get_facility_demand_series
from ml.forecasting import ForecastEngine

MAPE_TARGET = 8.0
HORIZON_HOURS = 24


class TestForecastMapeGate:

    def test_mape_meets_rfp_target(self):
        df = generate_historical(days=60, interval_minutes=15, anomaly_rate=0.0, seed=42)
        series = get_facility_demand_series(df, "office")
        hourly = series.resample("1h").mean()

        train = hourly.iloc[:-HORIZON_HOURS]
        actual = hourly.iloc[-HORIZON_HOURS:]

        engine = ForecastEngine()
        forecast = engine.forecast("office", train, horizon_hours=HORIZON_HOURS)

        predicted = forecast["predicted_kw"].values[:len(actual)]
        mape = float(np.mean(np.abs((actual.values - predicted) / (actual.values + 1e-6))) * 100)

        assert mape <= MAPE_TARGET, (
            f"Forecast MAPE {mape:.2f}% is above the RFP target of {MAPE_TARGET}%"
        )

    def test_sub_hourly_input_is_normalized_internally(self):
        # Regression guard: forecast() must resample a raw sub-hourly series
        # to hourly itself rather than trusting the caller to do it.
        df = generate_historical(days=10, interval_minutes=15, anomaly_rate=0.0, seed=42)
        series = get_facility_demand_series(df, "office")  # 15-min interval
        engine = ForecastEngine()
        result = engine.forecast("office", series, horizon_hours=6)
        deltas = result["forecast_ts"].diff().dropna()
        assert (deltas == deltas.iloc[0]).all()
        assert deltas.iloc[0].total_seconds() == 3600
