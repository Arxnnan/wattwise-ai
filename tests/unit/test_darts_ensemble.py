"""Unit tests — ml/darts_ensemble.py (backtested Tier-2 model selection)."""
from __future__ import annotations
import pandas as pd
import pytest

from ml.darts_ensemble import DartsEnsembleSelector, BacktestResult, _mape


class TestMape:

    def test_zero_error_is_zero_mape(self):
        import numpy as np
        actual = np.array([10.0, 20.0, 30.0])
        assert _mape(actual, actual) == pytest.approx(0.0, abs=1e-6)

    def test_known_error_matches_hand_calc(self):
        import numpy as np
        actual = np.array([100.0, 100.0])
        predicted = np.array([110.0, 90.0])
        assert _mape(actual, predicted) == pytest.approx(10.0, abs=1e-3)


class TestDartsEnsembleSelector:

    def test_raises_on_too_short_series(self):
        idx = pd.date_range("2026-01-01", periods=30, freq="h")
        series = pd.Series(range(30), index=idx, dtype=float)
        selector = DartsEnsembleSelector()
        with pytest.raises(ValueError, match="48h"):
            selector.backtest_and_select(series, horizon_hours=24)

    def test_selects_the_lower_mape_candidate(self, mocker):
        idx = pd.date_range("2026-01-01", periods=200, freq="h")
        series = pd.Series([50.0 + (i % 24) for i in range(200)], index=idx)

        good_forecast = pd.DataFrame({
            "forecast_ts": idx[-24:], "predicted_kw": series.values[-24:],
            "lower_bound": series.values[-24:] * 0.9, "upper_bound": series.values[-24:] * 1.1,
            "model": "darts_xgboost_seasonal",
        })
        bad_forecast = pd.DataFrame({
            "forecast_ts": idx[-24:], "predicted_kw": [0.0] * 24,
            "lower_bound": [0.0] * 24, "upper_bound": [0.0] * 24,
            "model": "chronos",
        })
        mocker.patch("ml.darts_ensemble._chronos_forecast", return_value=bad_forecast)
        mocker.patch("ml.darts_ensemble._darts_xgb_forecast", return_value=good_forecast)

        selector = DartsEnsembleSelector()
        result = selector.backtest_and_select(series, horizon_hours=24)

        assert isinstance(result, BacktestResult)
        assert result.model_name == "darts_xgboost_seasonal"
        assert result.mape < 1.0

    def test_falls_back_to_chronos_only_when_darts_unavailable(self, mocker):
        idx = pd.date_range("2026-01-01", periods=200, freq="h")
        series = pd.Series([50.0] * 200, index=idx)
        chronos_forecast = pd.DataFrame({
            "forecast_ts": idx[-24:], "predicted_kw": [50.0] * 24,
            "lower_bound": [45.0] * 24, "upper_bound": [55.0] * 24, "model": "chronos",
        })
        mocker.patch("ml.darts_ensemble._chronos_forecast", return_value=chronos_forecast)
        mocker.patch("ml.darts_ensemble._darts_xgb_forecast", return_value=None)

        selector = DartsEnsembleSelector()
        result = selector.backtest_and_select(series, horizon_hours=24)

        assert result.model_name == "chronos"
