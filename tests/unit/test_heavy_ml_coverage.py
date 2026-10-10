"""Coverage tests for heavy-ML modules.

Mocks `tensorflow`, `tensorflow.keras.*`, `darts`, and `darts.models` so no
real training happens — every test runs in milliseconds. The goal is to
exercise the import-fallback branches, save/load, candidate-flag merging,
Z-score fallback, and darts/chronos candidate pipelines.
"""
from __future__ import annotations

import importlib
import pickle
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# ----------------------------------------------------------------------
# Fake TensorFlow + Keras modules.
# ----------------------------------------------------------------------
def _make_fake_tf_modules():
    """Build a fake tensorflow package tree deterministic predict/fit/save."""
    tf = types.ModuleType("tensorflow")
    tf_keras = types.ModuleType("tensorflow.keras")
    tf_layers = types.ModuleType("tensorflow.keras.layers")
    tf_utils = types.ModuleType("tensorflow.keras.utils")
    tf_models = types.ModuleType("tensorflow.keras.models")
    tf_config = types.ModuleType("tensorflow.config")
    tf_config_exp = types.ModuleType("tensorflow.config.experimental")

    class FakeModel:
        def __init__(self, *a, **kw):
            self.compiled = False
            self.fitted = False

        def compile(self, **kw):
            self.compiled = True

        def fit(self, X, y, **kw):
            self.fitted = True
            self._shape = X.shape

        def predict(self, X, **kw):
            # Deterministic perfect-reconstruction + tiny noise so there's a
            # non-trivial percentile at line 100.
            arr = np.asarray(X, dtype=np.float32)
            noise = np.linspace(0.0, 0.05, arr.size, dtype=np.float32).reshape(arr.shape)
            return arr + noise

        def save(self, path):
            Path(path).write_bytes(b"fake-keras-model")

    class FakeLayer:
        """Universal stand-in for LSTM/Dense/RepeatVector/TimeDistributed."""
        def __init__(self, *a, **kw):
            pass

        def __call__(self, x):
            return x

    tf_layers.LSTM = FakeLayer
    tf_layers.Dense = FakeLayer
    tf_layers.RepeatVector = FakeLayer
    tf_layers.TimeDistributed = FakeLayer

    tf_keras.layers = tf_layers
    tf_keras.Input = lambda **kw: "fake-input-tensor"
    tf_keras.Model = lambda inputs, outputs: FakeModel()

    tf_utils.set_random_seed = lambda s: None
    tf_keras.utils = tf_utils

    tf_models.load_model = lambda p: FakeModel()
    tf_keras.models = tf_models

    tf_config_exp.enable_op_determinism = lambda: None
    tf_config.experimental = tf_config_exp

    tf.keras = tf_keras
    tf.config = tf_config

    return {
        "tensorflow": tf,
        "tensorflow.keras": tf_keras,
        "tensorflow.keras.layers": tf_layers,
        "tensorflow.keras.utils": tf_utils,
        "tensorflow.keras.models": tf_models,
        "tensorflow.config": tf_config,
        "tensorflow.config.experimental": tf_config_exp,
    }, FakeModel


@pytest.fixture
def fake_tf():
    mods, FakeModel = _make_fake_tf_modules()
    with patch.dict(sys.modules, mods):
        yield FakeModel


@pytest.fixture
def no_tf():
    """Make `import tensorflow` raise ImportError."""
    # Set the entry to None, which raises ImportError on `import tensorflow`.
    bad = {
        "tensorflow": None,
        "tensorflow.keras": None,
    }
    with patch.dict(sys.modules, bad):
        yield


@pytest.fixture
def demand_series():
    idx = pd.date_range("2026-01-01", periods=50, freq="h")
    return pd.Series(np.linspace(10.0, 20.0, 50), index=idx, name="kw")


# ----------------------------------------------------------------------
# ml.lstm_autoencoder — Z-score fallback branches
# ----------------------------------------------------------------------
class TestLSTMFallback:

    def test_build_model_returns_none_when_tf_import_fails(self, no_tf, demand_series):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        meta = ae.fit(demand_series)
        assert meta["method"] == "zscore_fallback"
        assert ae._using_fallback is True
        assert ae._fitted is True
        assert meta["threshold"] == pytest.approx(2.5)

    def test_zscore_predict_without_candidate_flags(self, no_tf, demand_series):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        ae.fit(demand_series)
        confirmed = ae.predict(demand_series)
        assert isinstance(confirmed, pd.Series)
        assert confirmed.name == "lstm_ae_anomaly"
        # Spike-free linear series -> no z > 2.5
        assert not confirmed.any()

    def test_zscore_predict_with_candidate_flags(self, no_tf, demand_series):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        # Create a spike so z-score crosses 2.5.
        spiked = demand_series.copy()
        spiked.iloc[25] = spiked.mean() * 20.0
        ae.fit(spiked)
        flags = pd.Series(True, index=spiked.index)
        confirmed = ae.predict(spiked, candidate_flags=flags)
        assert confirmed.any()  # exercises the AND-with-flags branch

    def test_zscore_reconstruction_error(self, no_tf, demand_series):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        ae.fit(demand_series)
        errors = ae.reconstruction_error(demand_series)
        assert isinstance(errors, pd.Series)
        assert errors.name == "recon_error"
        assert (errors >= 0).all()


# ----------------------------------------------------------------------
# ml.lstm_autoencoder — TF branch via fake tensorflow (fast)
# ----------------------------------------------------------------------
class TestLSTMFakeTF:

    def test_fit_predict_candidate_flags_branch(self, fake_tf, demand_series):
        """Exercise line 143: `confirmed & candidate_flags.reindex(...)`."""
        import ml.lstm_autoencoder as mod
        importlib.reload(mod)  # ensure fresh import of fake tf
        ae = mod.LSTMAutoencoder(seq_len=3, epochs=1, batch_size=4)
        ae.fit(demand_series)
        assert ae._fitted and not ae._using_fallback
        flags = pd.Series(True, index=demand_series.index)
        confirmed = ae.predict(demand_series, candidate_flags=flags)
        assert isinstance(confirmed, pd.Series)
        assert confirmed.name == "lstm_ae_anomaly"

    def test_reconstruction_error_tf_branch(self, fake_tf, demand_series):
        import ml.lstm_autoencoder as mod
        importlib.reload(mod)
        ae = mod.LSTMAutoencoder(seq_len=3, epochs=1, batch_size=4)
        ae.fit(demand_series)
        errors = ae.reconstruction_error(demand_series)
        assert isinstance(errors, pd.Series)
        assert len(errors) == len(demand_series) - 3

    def test_save_and_load_round_trip(self, fake_tf, demand_series, tmp_path):
        import ml.lstm_autoencoder as mod
        importlib.reload(mod)
        ae = mod.LSTMAutoencoder(seq_len=3, epochs=1, batch_size=4)
        ae.fit(demand_series)

        save_path = tmp_path / "ae_model"
        ae.save(save_path)
        assert (tmp_path / "ae_model.keras").exists()
        assert (tmp_path / "ae_model.pkl").exists()

        loaded = mod.LSTMAutoencoder.load(save_path)
        assert loaded._fitted is True
        assert loaded._using_fallback is False
        assert loaded._model is not None

    def test_load_except_branch_on_bad_keras_file(self, fake_tf, demand_series, tmp_path):
        """Covers lines 183-184: load_model raises -> fallback flag set."""
        import ml.lstm_autoencoder as mod
        importlib.reload(mod)
        ae = mod.LSTMAutoencoder(seq_len=3, epochs=1, batch_size=4)
        ae.fit(demand_series)
        save_path = tmp_path / "ae_model"
        ae.save(save_path)

        # Replace fake-tf.load_model with one that raises.
        bad_load = sys.modules["tensorflow.keras.models"]
        original = bad_load.load_model
        bad_load.load_model = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            loaded = mod.LSTMAutoencoder.load(save_path)
        finally:
            bad_load.load_model = original
        assert loaded._using_fallback is True


class TestLSTMSaveWithoutModel:
    """Covers the `if self._model:` false-branch (line 163 skipped cleanly)."""

    def test_save_in_fallback_mode_skips_keras_file(self, no_tf, demand_series, tmp_path):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        ae.fit(demand_series)  # fallback -> _model is None
        save_path = tmp_path / "fallback_model"
        ae.save(save_path)
        assert (tmp_path / "fallback_model.pkl").exists()
        assert not (tmp_path / "fallback_model.keras").exists()


class TestLSTMLoadWithoutKerasFile:

    def test_load_pkl_only(self, no_tf, demand_series, tmp_path):
        from ml.lstm_autoencoder import LSTMAutoencoder
        ae = LSTMAutoencoder(seq_len=3)
        ae.fit(demand_series)
        save_path = tmp_path / "pkl_only"
        ae.save(save_path)
        assert not (tmp_path / "pkl_only.keras").exists()
        loaded = LSTMAutoencoder.load(save_path)
        assert loaded._fitted
        assert loaded._using_fallback is True


# ----------------------------------------------------------------------
# ml.darts_ensemble — real _darts_xgb_forecast and _chronos_forecast
# ----------------------------------------------------------------------
def _make_fake_darts_modules():
    darts = types.ModuleType("darts")
    darts_models = types.ModuleType("darts.models")

    class FakeTimeSeries:
        def __init__(self, data=None):
            self._data = data

        @classmethod
        def from_series(cls, series):
            return cls(np.asarray(series.values, dtype=np.float32))

        def values(self):
            # Shape (horizon, 1) — real darts returns 2D array
            n = 24
            return np.linspace(45.0, 55.0, n, dtype=np.float32).reshape(-1, 1)

    class FakeXGBModel:
        def __init__(self, **kw):
            self.kw = kw

        def fit(self, ts):
            self._fit_ts = ts

        def predict(self, horizon):
            return FakeTimeSeries()

    darts.TimeSeries = FakeTimeSeries
    darts_models.XGBModel = FakeXGBModel
    return {"darts": darts, "darts.models": darts_models}


class TestDartsXGBForecast:

    def test_returns_none_when_darts_missing(self):
        """Covers the ImportError branch (darts isn't installed in this env)."""
        # Make sure darts is really unimportable.
        bad = {"darts": None, "darts.models": None}
        with patch.dict(sys.modules, bad):
            from ml.darts_ensemble import _darts_xgb_forecast
            idx = pd.date_range("2026-01-01", periods=60, freq="h")
            series = pd.Series(np.arange(60, dtype=float), index=idx)
            assert _darts_xgb_forecast(series, horizon_hours=24) is None

    def test_full_pipeline_with_fake_darts(self):
        """Covers the success path: TimeSeries.from_series, fit, predict, df."""
        mods = _make_fake_darts_modules()
        with patch.dict(sys.modules, mods):
            from ml.darts_ensemble import _darts_xgb_forecast
            idx = pd.date_range("2026-01-01", periods=60, freq="h")
            series = pd.Series(np.arange(60, dtype=float), index=idx)
            df = _darts_xgb_forecast(series, horizon_hours=24)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 24
        assert set(df.columns) == {
            "forecast_ts", "predicted_kw", "lower_bound", "upper_bound", "model",
        }
        assert (df["lower_bound"] <= df["predicted_kw"]).all()
        assert (df["upper_bound"] >= df["predicted_kw"]).all()
        assert df["model"].iloc[0] == "darts_xgboost_seasonal"
        # First forecast timestamp = last training ts + 1h
        assert df["forecast_ts"].iloc[0] == idx[-1] + pd.Timedelta(hours=1)


class TestChronosForecastWrapper:

    def test_chronos_forecast_delegates_to_chronos_forecaster(self):
        """Covers line 71: real call through _chronos_forecast."""
        import ml.darts_ensemble as de

        idx = pd.date_range("2026-01-01", periods=10, freq="h")
        series = pd.Series(np.arange(10, dtype=float), index=idx)
        expected = pd.DataFrame({
            "forecast_ts": idx, "predicted_kw": [1.0] * 10,
            "lower_bound": [0.9] * 10, "upper_bound": [1.1] * 10, "model": "chronos",
        })

        class FakeChronos:
            def __init__(self, model_size="tiny"):
                self.size = model_size

            def predict(self, train, horizon):
                return expected

        with patch.object(de, "ChronosForecaster", FakeChronos):
            out = de._chronos_forecast(series, horizon_hours=10)
        assert out is expected


class TestDartsSelectorEndToEnd:
    """Also exercises the real _darts_xgb_forecast via backtest_and_select."""

    def test_backtest_runs_both_candidates_with_fakes(self):
        mods = _make_fake_darts_modules()
        with patch.dict(sys.modules, mods):
            import ml.darts_ensemble as de

            idx = pd.date_range("2026-01-01", periods=120, freq="h")
            series = pd.Series(50.0 + np.sin(np.arange(120)), index=idx)

            fake_chronos_df = pd.DataFrame({
                "forecast_ts": idx[-24:],
                "predicted_kw": [40.0] * 24,  # worse than fake xgb linspace(45..55)
                "lower_bound": [36.0] * 24, "upper_bound": [44.0] * 24,
                "model": "chronos",
            })

            class FakeChronos:
                def __init__(self, model_size="tiny"):
                    pass

                def predict(self, train, horizon):
                    return fake_chronos_df

            with patch.object(de, "ChronosForecaster", FakeChronos):
                result = de.DartsEnsembleSelector().backtest_and_select(
                    series, horizon_hours=24
                )
        assert isinstance(result, de.BacktestResult)
        assert result.model_name in {"chronos", "darts_xgboost_seasonal"}
