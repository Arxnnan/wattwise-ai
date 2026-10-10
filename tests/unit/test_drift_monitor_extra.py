"""Additional unit tests for ml.drift_monitor — covers the Evidently branch,
the import-detection helper, and edge-cases not exercised by the base suite.

All file I/O and the Evidently dependency are mocked, so these tests are
hermetic and stay well under the 2-second budget each."""
from __future__ import annotations

import builtins
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from ml.drift_monitor import DriftMonitor, _try_evidently


# ---------------------------------------------------------------------------
# _try_evidently helper
# ---------------------------------------------------------------------------
class TestTryEvidently:

    def test_returns_true_when_evidently_importable(self, monkeypatch):
        # Install stub modules so the three `from evidently... import ...`
        # statements in `_try_evidently` succeed deterministically, regardless
        # of whether the real `evidently` package is present / what version it
        # is in this environment.
        fake_evidently = types.ModuleType("evidently")
        fake_evidently.ColumnMapping = MagicMock()
        fake_report = types.ModuleType("evidently.report")
        fake_report.Report = MagicMock()
        fake_preset = types.ModuleType("evidently.metric_preset")
        fake_preset.DataDriftPreset = MagicMock()
        fake_preset.DataQualityPreset = MagicMock()
        monkeypatch.setitem(sys.modules, "evidently", fake_evidently)
        monkeypatch.setitem(sys.modules, "evidently.report", fake_report)
        monkeypatch.setitem(sys.modules, "evidently.metric_preset", fake_preset)
        assert _try_evidently() is True

    def test_returns_false_when_import_raises(self, caplog):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("evidently"):
                raise ImportError("simulated: evidently missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with caplog.at_level("WARNING", logger="ml.drift_monitor"):
                assert _try_evidently() is False
        assert any("Evidently not installed" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------
class TestConstructor:

    def test_stores_config_and_detects_evidently(self):
        with patch("ml.drift_monitor._try_evidently", return_value=True):
            m = DriftMonitor(reference_window_days=3, drift_threshold=0.1)
        assert m.reference_window_days == 3
        assert m.drift_threshold == 0.1
        assert m._has_evidently is True

    def test_defaults(self):
        with patch("ml.drift_monitor._try_evidently", return_value=False):
            m = DriftMonitor()
        assert m.reference_window_days == 7
        assert m.drift_threshold == 0.05
        assert m._has_evidently is False


# ---------------------------------------------------------------------------
# Evidently drift path
# ---------------------------------------------------------------------------
def _install_fake_evidently(monkeypatch, drift_detected=True, share=0.75):
    """Install fake `evidently`, `evidently.report`, `evidently.metric_preset`
    modules in sys.modules so the lazy imports inside `_evidently_drift` work.
    Returns the fake `Report` class so tests can inspect .run calls.
    """
    fake_report_instance = MagicMock()
    fake_report_instance.as_dict.return_value = {
        "metrics": [
            {"result": {"dataset_drift": drift_detected,
                        "share_of_drifted_columns": share}}
        ]
    }

    fake_report_cls = MagicMock(return_value=fake_report_instance)
    fake_column_mapping = MagicMock()
    fake_preset = MagicMock()

    fake_evidently = types.ModuleType("evidently")
    fake_evidently.ColumnMapping = fake_column_mapping

    fake_report_mod = types.ModuleType("evidently.report")
    fake_report_mod.Report = fake_report_cls

    fake_preset_mod = types.ModuleType("evidently.metric_preset")
    fake_preset_mod.DataDriftPreset = fake_preset
    fake_preset_mod.DataQualityPreset = MagicMock()

    monkeypatch.setitem(sys.modules, "evidently", fake_evidently)
    monkeypatch.setitem(sys.modules, "evidently.report", fake_report_mod)
    monkeypatch.setitem(sys.modules, "evidently.metric_preset", fake_preset_mod)

    return fake_report_cls, fake_report_instance


class TestEvidentlyDriftBranch:

    def test_check_data_drift_dispatches_to_evidently(self, monkeypatch):
        _install_fake_evidently(monkeypatch, drift_detected=True, share=0.5)
        with patch("ml.drift_monitor._try_evidently", return_value=True):
            m = DriftMonitor()

        ref = pd.DataFrame({"demand_kw": np.arange(20.0)})
        cur = pd.DataFrame({"demand_kw": np.arange(20.0) + 100})
        result = m.check_data_drift(ref, cur, ["demand_kw"])

        assert result["method"] == "evidently"
        assert result["drift_detected"] is True
        assert result["drifted_columns_share"] == 0.5
        assert "timestamp" in result

    def test_evidently_drift_no_drift_detected(self, monkeypatch):
        fake_cls, fake_inst = _install_fake_evidently(
            monkeypatch, drift_detected=False, share=0.0
        )
        with patch("ml.drift_monitor._try_evidently", return_value=True):
            m = DriftMonitor()

        ref = pd.DataFrame({"f1": np.arange(10.0), "f2": np.arange(10.0)})
        cur = pd.DataFrame({"f1": np.arange(10.0), "f2": np.arange(10.0)})
        result = m._evidently_drift(ref, cur, ["f1", "f2"])

        assert result["drift_detected"] is False
        assert result["drifted_columns_share"] == 0.0
        fake_cls.assert_called_once()         # Report(metrics=[...])
        fake_inst.run.assert_called_once()    # report.run(...)

    def test_evidently_drift_passes_feature_subset(self, monkeypatch):
        _, fake_inst = _install_fake_evidently(monkeypatch)
        with patch("ml.drift_monitor._try_evidently", return_value=True):
            m = DriftMonitor()

        ref = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "ignored": [7, 8, 9]})
        cur = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "ignored": [7, 8, 9]})
        m._evidently_drift(ref, cur, ["a", "b"])

        kwargs = fake_inst.run.call_args.kwargs
        assert list(kwargs["reference_data"].columns) == ["a", "b"]
        assert list(kwargs["current_data"].columns) == ["a", "b"]


# ---------------------------------------------------------------------------
# Statistical fallback edge cases not covered by the base suite
# ---------------------------------------------------------------------------
@pytest.fixture
def ks_monitor():
    with patch("ml.drift_monitor._try_evidently", return_value=False):
        return DriftMonitor(reference_window_days=7, drift_threshold=0.05)


class TestStatisticalEdges:

    def test_empty_dataframes(self, ks_monitor):
        ref = pd.DataFrame({"demand_kw": []})
        cur = pd.DataFrame({"demand_kw": []})
        result = ks_monitor.check_data_drift(ref, cur, ["demand_kw"])
        assert result["drift_detected"] is False
        assert result["drifted_columns"] == []

    def test_single_row_dataframes(self, ks_monitor):
        ref = pd.DataFrame({"demand_kw": [1.0]})
        cur = pd.DataFrame({"demand_kw": [100.0]})
        result = ks_monitor.check_data_drift(ref, cur, ["demand_kw"])
        # fewer than 10 samples -> skipped, no drift
        assert result["drift_detected"] is False

    def test_all_nan_values_skipped(self, ks_monitor):
        ref = pd.DataFrame({"demand_kw": [np.nan] * 50})
        cur = pd.DataFrame({"demand_kw": [np.nan] * 50})
        result = ks_monitor.check_data_drift(ref, cur, ["demand_kw"])
        # dropna leaves 0 values; column is skipped and no drift reported
        assert result["drift_detected"] is False
        assert result["drifted_columns"] == []

    def test_column_missing_only_in_current(self, ks_monitor):
        rng = np.random.default_rng(2)
        ref = pd.DataFrame({"a": rng.normal(0, 1, 50), "b": rng.normal(0, 1, 50)})
        cur = pd.DataFrame({"a": rng.normal(0, 1, 50)})  # no 'b'
        result = ks_monitor.check_data_drift(ref, cur, ["a", "b"])
        # 'b' missing -> skipped; 'a' matches -> no drift
        assert result["drift_detected"] is False

    def test_empty_feature_list_share_is_zero(self, ks_monitor):
        ref = pd.DataFrame({"demand_kw": [1.0, 2.0]})
        cur = pd.DataFrame({"demand_kw": [1.0, 2.0]})
        result = ks_monitor.check_data_drift(ref, cur, [])
        # max(len([]), 1) == 1 guards against ZeroDivisionError
        assert result["drifted_columns_share"] == 0.0
        assert result["drift_detected"] is False

    def test_share_rounded_to_three_decimals(self, ks_monitor):
        rng = np.random.default_rng(42)
        # one of three columns drifts
        ref = pd.DataFrame({
            "x": rng.normal(0, 1, 200),
            "y": rng.normal(0, 1, 200),
            "z": rng.normal(0, 1, 200),
        })
        cur = pd.DataFrame({
            "x": rng.normal(0, 1, 200),
            "y": rng.normal(0, 1, 200),
            "z": rng.normal(50, 1, 200),  # big shift
        })
        result = ks_monitor.check_data_drift(ref, cur, ["x", "y", "z"])
        assert result["drifted_columns"] == ["z"]
        assert result["drifted_columns_share"] == round(1 / 3, 3)


# ---------------------------------------------------------------------------
# Forecast drift edge cases
# ---------------------------------------------------------------------------
class TestForecastDriftExtras:

    def test_partial_index_overlap_uses_common_index(self, ks_monitor):
        full_idx = pd.date_range("2026-01-01", periods=20, freq="h")
        actual = pd.Series(np.full(20, 100.0), index=full_idx)
        # predicted shares the last 15 timestamps with actual
        predicted = pd.Series(np.full(15, 200.0), index=full_idx[5:])
        result = ks_monitor.check_forecast_drift(actual, predicted)
        assert result["drift_detected"] is True
        # MAPE ≈ 100% on the 15 shared points
        assert result["mape"] == pytest.approx(100.0, rel=1e-3)

    def test_zero_actuals_do_not_crash(self, ks_monitor):
        idx = pd.date_range("2026-01-01", periods=12, freq="h")
        actual = pd.Series(np.zeros(12), index=idx)
        predicted = pd.Series(np.zeros(12), index=idx)
        result = ks_monitor.check_forecast_drift(actual, predicted)
        # 0/eps -> 0 MAPE, no drift
        assert result["mape"] == pytest.approx(0.0, abs=1e-6)
        assert result["drift_detected"] is False
        assert result["threshold_pct"] == 15.0


# ---------------------------------------------------------------------------
# run_nightly_report additional behaviour (mock the file write)
# ---------------------------------------------------------------------------
class TestNightlyReportExtras:

    def _telemetry(self, days: int) -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        rows = []
        for i in range(days * 24):
            ts = end - timedelta(hours=days * 24 - i)
            rows.append({"ts": ts, "domain": "demand", "value": 50.0 + (i % 5)})
        return pd.DataFrame(rows)

    def test_mocks_file_write_and_returns_payload(self, ks_monitor, tmp_path):
        df = self._telemetry(days=14)

        m_open = MagicMock()
        with patch("builtins.open", m_open), \
             patch("json.dump") as m_dump:
            result = ks_monitor.run_nightly_report(df, output_dir=str(tmp_path))

        assert result["method"] == "ks_test_fallback"
        assert result["reference_rows"] > 0
        assert result["current_rows"] > 0
        assert "report_date" in result
        m_open.assert_called_once()
        m_dump.assert_called_once()
        # dump payload is the same dict we returned
        dumped = m_dump.call_args.args[0]
        assert dumped is result

    def test_empty_reference_returns_insufficient(self, ks_monitor, tmp_path):
        # Only 1 row -> everything on one side of the cutoff
        now = datetime.now(timezone.utc)
        df = pd.DataFrame([{"ts": now, "domain": "demand", "value": 1.0}])
        with patch("builtins.open", MagicMock()), \
             patch("json.dump"):
            result = ks_monitor.run_nightly_report(df, output_dir=str(tmp_path))
        assert result == {"status": "insufficient_data"}

    def test_dispatches_through_evidently_when_available(self, monkeypatch, tmp_path):
        _install_fake_evidently(monkeypatch, drift_detected=False, share=0.0)
        with patch("ml.drift_monitor._try_evidently", return_value=True):
            m = DriftMonitor(reference_window_days=7)

        # Build 14 days of telemetry
        end = datetime.now(timezone.utc)
        rows = [{"ts": end - timedelta(hours=14 * 24 - i),
                 "domain": "demand", "value": float(i)}
                for i in range(14 * 24)]
        df = pd.DataFrame(rows)

        with patch("builtins.open", MagicMock()), \
             patch("json.dump"):
            result = m.run_nightly_report(df, output_dir=str(tmp_path))

        assert result["method"] == "evidently"
        assert result["drift_detected"] is False
