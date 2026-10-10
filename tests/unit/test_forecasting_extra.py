"""Additional unit tests — forecasting engine coverage boost.

Mocks heavy deps (chronos/torch/transformers/prophet/mlflow) so no model loads.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_series(n: int = 48, start: str = "2026-01-01", tz=None) -> pd.Series:
    """Hourly indexed series of synthetic kW values."""
    idx = pd.date_range(start=start, periods=n, freq="h", tz=tz)
    values = np.linspace(10.0, 50.0, n) + np.sin(np.arange(n))
    return pd.Series(values, index=idx)


# ---------------------------------------------------------------------------
# ChronosForecaster._try_load
# ---------------------------------------------------------------------------


class TestChronosTryLoad:
    def test_import_error_branch(self):
        """When `chronos` is unimportable, available stays False."""
        from ml.forecasting import ChronosForecaster

        # Ensure a cached dummy doesn't short-circuit.
        with patch.dict(sys.modules, {"chronos": None}):
            fc = ChronosForecaster(model_size="tiny")
        assert fc._available is False
        assert fc._pipeline is None

    def test_successful_load(self):
        """A mocked chronos module makes `_available` True and pipeline is set."""
        from ml import forecasting

        fake_pipeline_instance = MagicMock(name="pipeline")
        fake_chronos_cls = MagicMock()
        fake_chronos_cls.from_pretrained.return_value = fake_pipeline_instance

        fake_chronos_mod = SimpleNamespace(ChronosPipeline=fake_chronos_cls)
        fake_torch = SimpleNamespace(bfloat16="bfloat16-sentinel")

        with patch.dict(sys.modules, {"chronos": fake_chronos_mod, "torch": fake_torch}):
            fc = forecasting.ChronosForecaster(model_size="small")

        assert fc._available is True
        assert fc._pipeline is fake_pipeline_instance
        fake_chronos_cls.from_pretrained.assert_called_once()
        args, kwargs = fake_chronos_cls.from_pretrained.call_args
        assert args[0] == "amazon/chronos-t5-small"
        assert kwargs["device_map"] == "cpu"
        assert kwargs["torch_dtype"] == "bfloat16-sentinel"

    def test_generic_exception_branch(self):
        """A non-ImportError during load should be caught and `_available=False`."""
        fake_chronos_cls = MagicMock()
        fake_chronos_cls.from_pretrained.side_effect = RuntimeError("boom")
        fake_chronos_mod = SimpleNamespace(ChronosPipeline=fake_chronos_cls)
        fake_torch = SimpleNamespace(bfloat16="bfloat16-sentinel")

        from ml.forecasting import ChronosForecaster

        with patch.dict(sys.modules, {"chronos": fake_chronos_mod, "torch": fake_torch}):
            fc = ChronosForecaster(model_size="tiny")

        assert fc._available is False
        assert fc._pipeline is None


# ---------------------------------------------------------------------------
# ChronosForecaster.predict / _chronos_predict / _statistical_fallback
# ---------------------------------------------------------------------------


class TestChronosPredict:
    def test_statistical_fallback_direct(self):
        """Direct call to _statistical_fallback produces correct shape + model tag."""
        from ml.forecasting import ChronosForecaster

        fc = ChronosForecaster.__new__(ChronosForecaster)  # bypass __init__
        fc.model_size = "tiny"
        fc._pipeline = None
        fc._available = False

        series = _make_series(72)
        horizon = 10
        out = fc._statistical_fallback(series, horizon_hours=horizon)
        assert list(out.columns) == [
            "forecast_ts", "predicted_kw", "lower_bound", "upper_bound", "model",
        ]
        assert len(out) == horizon
        assert (out["model"] == "seasonal_naive").all()
        assert (out["upper_bound"] >= out["lower_bound"]).all()
        # future timestamps start AFTER last observed index
        assert out["forecast_ts"].iloc[0] == series.index[-1] + timedelta(hours=1)

    def test_statistical_fallback_short_series(self):
        """When len(series) < 24, period clamps to series length."""
        from ml.forecasting import ChronosForecaster
        fc = ChronosForecaster.__new__(ChronosForecaster)
        fc._pipeline = None
        fc._available = False

        series = _make_series(5)
        out = fc._statistical_fallback(series, horizon_hours=3)
        assert len(out) == 3

    def test_predict_dispatches_to_fallback_when_unavailable(self):
        """predict() routes to statistical fallback if pipeline unavailable."""
        from ml.forecasting import ChronosForecaster
        fc = ChronosForecaster.__new__(ChronosForecaster)
        fc._available = False
        fc._pipeline = None

        series = _make_series(30)
        out = fc.predict(series, horizon_hours=4)
        assert len(out) == 4
        assert (out["model"] == "seasonal_naive").all()

    def test_predict_dispatches_to_chronos_when_available(self):
        """predict() routes to _chronos_predict when pipeline is loaded."""
        from ml.forecasting import ChronosForecaster
        fc = ChronosForecaster.__new__(ChronosForecaster)
        fc._available = True
        fc._pipeline = MagicMock()

        with patch.object(fc, "_chronos_predict", return_value=pd.DataFrame({"x": [1]})) as m:
            out = fc.predict(_make_series(10), horizon_hours=5)
        m.assert_called_once()
        assert list(out.columns) == ["x"]

    def test_chronos_predict_builds_dataframe(self):
        """_chronos_predict wires pipeline output into the expected DataFrame."""
        from ml.forecasting import ChronosForecaster

        # Fake torch module: tensor() returns an object with .unsqueeze() -> itself-ish.
        fake_tensor = MagicMock(name="context_tensor")
        fake_tensor.unsqueeze.return_value = fake_tensor
        fake_torch = MagicMock()
        fake_torch.tensor.return_value = fake_tensor
        fake_torch.float32 = "float32-sentinel"

        # Pipeline.predict returns a list-of-arrays-like; [0].numpy() -> 2D (samples, horizon)
        horizon = 6
        samples = np.vstack([np.linspace(1, 6, horizon) + i for i in range(5)])
        inner = MagicMock()
        inner.numpy.return_value = samples
        forecast_out = [inner]

        fake_pipeline = MagicMock()
        fake_pipeline.predict.return_value = forecast_out

        fc = ChronosForecaster.__new__(ChronosForecaster)
        fc._available = True
        fc._pipeline = fake_pipeline

        series = _make_series(600)  # exercise [-512:] slice
        with patch.dict(sys.modules, {"torch": fake_torch}):
            out = fc._chronos_predict(series, horizon_hours=horizon)

        assert len(out) == horizon
        assert (out["model"] == "chronos").all()
        assert set(out.columns) == {
            "forecast_ts", "predicted_kw", "lower_bound", "upper_bound", "model",
        }
        # First forecast ts should be last_ts + 1h
        assert out["forecast_ts"].iloc[0] == series.index[-1] + timedelta(hours=1)
        fake_torch.tensor.assert_called_once()


# ---------------------------------------------------------------------------
# ProphetForecaster
# ---------------------------------------------------------------------------


class TestProphetForecaster:
    def test_predict_returns_none_when_not_fitted(self):
        from ml.forecasting import ProphetForecaster
        pf = ProphetForecaster()
        assert pf.predict(horizon_hours=5) is None

    def test_fit_import_error(self):
        """Missing prophet should NOT raise — just log and leave _fitted False."""
        from ml.forecasting import ProphetForecaster
        pf = ProphetForecaster()
        with patch.dict(sys.modules, {"prophet": None}):
            pf.fit(_make_series(48))
        assert pf._fitted is False
        assert pf._model is None

    def test_fit_success_strips_timezone(self):
        """A tz-aware series gets tz_localize(None) before fitting."""
        from ml.forecasting import ProphetForecaster
        fake_model = MagicMock()
        fake_prophet_cls = MagicMock(return_value=fake_model)
        fake_prophet_mod = SimpleNamespace(Prophet=fake_prophet_cls)

        pf = ProphetForecaster()
        series = _make_series(48, tz="UTC")
        with patch.dict(sys.modules, {"prophet": fake_prophet_mod}):
            pf.fit(series)

        assert pf._fitted is True
        assert pf._model is fake_model
        fake_prophet_cls.assert_called_once()
        fake_model.fit.assert_called_once()
        passed_df = fake_model.fit.call_args[0][0]
        assert passed_df["ds"].dt.tz is None

    def test_fit_success_tz_naive_series(self):
        """A tz-naive series skips the tz_localize branch."""
        from ml.forecasting import ProphetForecaster
        fake_model = MagicMock()
        fake_prophet_mod = SimpleNamespace(Prophet=MagicMock(return_value=fake_model))
        pf = ProphetForecaster()
        with patch.dict(sys.modules, {"prophet": fake_prophet_mod}):
            pf.fit(_make_series(48, tz=None))
        assert pf._fitted is True
        fake_model.fit.assert_called_once()

    def test_predict_returns_dataframe(self):
        """A fitted ProphetForecaster returns the expected DataFrame."""
        from ml.forecasting import ProphetForecaster
        horizon = 4
        now = datetime(2026, 1, 2)
        future_df = pd.DataFrame({"ds": pd.date_range(now, periods=20, freq="h")})
        tail_rows = horizon + 10  # enough to supply .tail(horizon)
        forecast_df = pd.DataFrame({
            "ds": pd.date_range(now, periods=tail_rows, freq="h"),
            "yhat": np.arange(tail_rows, dtype=float),
            "yhat_lower": np.arange(tail_rows, dtype=float) - 1,
            "yhat_upper": np.arange(tail_rows, dtype=float) + 1,
        })
        fake_model = MagicMock()
        fake_model.make_future_dataframe.return_value = future_df
        fake_model.predict.return_value = forecast_df

        pf = ProphetForecaster()
        pf._model = fake_model
        pf._fitted = True
        out = pf.predict(horizon_hours=horizon)

        assert isinstance(out, pd.DataFrame)
        assert len(out) == horizon
        assert (out["model"] == "prophet").all()
        assert set(out.columns) == {
            "forecast_ts", "predicted_kw", "lower_bound", "upper_bound", "model",
        }
        fake_model.make_future_dataframe.assert_called_once_with(periods=horizon, freq="h")


# ---------------------------------------------------------------------------
# ForecastEngine
# ---------------------------------------------------------------------------


class TestForecastEngine:
    def test_fit_prophet_stores_forecaster(self):
        """fit_prophet() delegates to ProphetForecaster and caches it per facility."""
        from ml import forecasting

        engine = forecasting.ForecastEngine.__new__(forecasting.ForecastEngine)
        engine.chronos = MagicMock()
        engine.prophet = {}

        with patch.object(forecasting, "ProphetForecaster") as PF:
            instance = PF.return_value
            engine.fit_prophet("office", _make_series(48))

        PF.assert_called_once_with()
        instance.fit.assert_called_once()
        assert engine.prophet["office"] is instance

    def test_forecast_resamples_and_logs_mlflow(self):
        """forecast() resamples sub-hourly data, uses chronos, and logs params."""
        from ml import forecasting

        engine = forecasting.ForecastEngine.__new__(forecasting.ForecastEngine)
        engine.chronos = MagicMock()
        engine.prophet = {}

        result = pd.DataFrame({
            "forecast_ts": pd.date_range("2026-01-02", periods=3, freq="h"),
            "predicted_kw": [1.0, 2.0, 3.0],
            "lower_bound": [0.5, 1.5, 2.5],
            "upper_bound": [1.5, 2.5, 3.5],
            "model": ["chronos", "chronos", "chronos"],
        })
        engine.chronos.predict.return_value = result

        # 15-min series collapses to hourly after resample().mean().
        idx = pd.date_range("2026-01-01", periods=96, freq="15min")
        series = pd.Series(np.arange(96, dtype=float), index=idx)

        with patch.object(forecasting, "mlflow") as mlf:
            mlf.start_run.return_value.__enter__ = lambda self_: None
            mlf.start_run.return_value.__exit__ = lambda self_, *a: False
            out = engine.forecast("facility-A", series, horizon_hours=3)

        # Chronos must have been called with the hourly resampled series.
        resampled = engine.chronos.predict.call_args[0][0]
        assert resampled.index.freqstr in ("h", "H")
        # ~24 hourly points from 96x 15-min samples
        assert 20 <= len(resampled) <= 24

        # DataFrame returned is the chronos result.
        assert out is result

        # mlflow params were logged.
        logged_keys = {c.args[0] for c in mlf.log_param.call_args_list}
        assert {"facility_id", "horizon_hours", "series_length", "model_used"} <= logged_keys

    def test_peak_warning_mixed(self):
        """peak_warning should flag only the rows that exceed warn_threshold."""
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine.__new__(ForecastEngine)

        df = pd.DataFrame({
            "forecast_ts": pd.date_range("2026-01-01", periods=4, freq="h"),
            "predicted_kw": [10.0, 50.0, 100.0, 25.0],
            "lower_bound": [0, 0, 0, 0],
            "upper_bound": [0, 0, 0, 0],
            "model": ["chronos"] * 4,
        })
        out = engine.peak_warning(df, threshold_kw=100.0, warn_ratio=0.5)
        # warn threshold = 50 -> rows 1,2 flagged; others not.
        assert out["peak_warning"].tolist() == [False, True, True, False]
        # Original df untouched (copy).
        assert "peak_warning" not in df.columns
        assert (out["peak_threshold_kw"] == 100.0).all()
        assert (out["warn_threshold_kw"] == 50.0).all()

    def test_peak_warning_default_ratio(self):
        """Default warn_ratio=0.90 applied when not specified."""
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine.__new__(ForecastEngine)
        df = pd.DataFrame({
            "forecast_ts": pd.date_range("2026-01-01", periods=2, freq="h"),
            "predicted_kw": [89.0, 91.0],
            "lower_bound": [0, 0], "upper_bound": [0, 0],
            "model": ["chronos", "chronos"],
        })
        out = engine.peak_warning(df, threshold_kw=100.0)
        assert out["warn_threshold_kw"].iloc[0] == pytest.approx(90.0)
        assert out["peak_warning"].tolist() == [False, True]
