"""Unit tests — Evidently drift monitor. Forces the statistical (KS-test)
fallback path deterministically rather than depending on whether `evidently`
happens to be importable in the environment running the suite."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def monitor(mocker):
    from ml.drift_monitor import DriftMonitor
    mocker.patch("ml.drift_monitor._try_evidently", return_value=False)
    return DriftMonitor(reference_window_days=7, drift_threshold=0.05)


class TestStatisticalDriftFallback:

    def test_no_drift_when_distributions_match(self, monitor):
        rng = np.random.default_rng(0)
        reference = pd.DataFrame({"demand_kw": rng.normal(50, 5, 500)})
        current = pd.DataFrame({"demand_kw": rng.normal(50, 5, 500)})
        result = monitor.check_data_drift(reference, current, ["demand_kw"])
        assert result["method"] == "ks_test_fallback"
        assert result["drift_detected"] is False
        assert result["drifted_columns"] == []

    def test_drift_detected_on_shifted_distribution(self, monitor):
        rng = np.random.default_rng(0)
        reference = pd.DataFrame({"demand_kw": rng.normal(50, 5, 500)})
        current = pd.DataFrame({"demand_kw": rng.normal(90, 5, 500)})  # big shift
        result = monitor.check_data_drift(reference, current, ["demand_kw"])
        assert result["drift_detected"] is True
        assert "demand_kw" in result["drifted_columns"]
        assert result["drifted_columns_share"] == 1.0

    def test_missing_column_is_skipped_not_raised(self, monitor):
        reference = pd.DataFrame({"demand_kw": np.random.default_rng(0).normal(50, 5, 50)})
        current = pd.DataFrame({"demand_kw": np.random.default_rng(1).normal(50, 5, 50)})
        result = monitor.check_data_drift(reference, current, ["demand_kw", "missing_col"])
        assert result["drifted_columns_share"] <= 0.5  # missing_col contributes no drift

    def test_too_few_samples_are_skipped(self, monitor):
        reference = pd.DataFrame({"demand_kw": [1.0, 2.0, 3.0]})  # < 10 samples
        current = pd.DataFrame({"demand_kw": [1.0, 2.0, 3.0]})
        result = monitor.check_data_drift(reference, current, ["demand_kw"])
        assert result["drift_detected"] is False
        assert result["drifted_columns"] == []


class TestForecastDrift:

    def test_low_error_is_not_drift(self, monitor):
        idx = pd.date_range("2026-01-01", periods=24, freq="h")
        actual = pd.Series(np.full(24, 100.0), index=idx)
        predicted = pd.Series(np.full(24, 102.0), index=idx)  # 2% error
        result = monitor.check_forecast_drift(actual, predicted)
        assert result["drift_detected"] is False
        assert result["mape"] < 15.0

    def test_high_error_is_drift(self, monitor):
        idx = pd.date_range("2026-01-01", periods=24, freq="h")
        actual = pd.Series(np.full(24, 100.0), index=idx)
        predicted = pd.Series(np.full(24, 150.0), index=idx)  # 50% error
        result = monitor.check_forecast_drift(actual, predicted)
        assert result["drift_detected"] is True
        assert result["mape"] > 15.0

    def test_insufficient_overlap_returns_early(self, monitor):
        actual = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2, freq="h"))
        predicted = pd.Series([1.0, 2.0], index=pd.date_range("2027-01-01", periods=2, freq="h"))
        result = monitor.check_forecast_drift(actual, predicted)
        assert result == {"drift_detected": False, "reason": "insufficient data"}


class TestNightlyReport:

    def _telemetry_df(self, days: int) -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        rows = []
        for i in range(days * 24):
            ts = end - timedelta(hours=days * 24 - i)
            rows.append({"ts": ts, "domain": "demand", "value": 50.0 + (i % 5)})
        return pd.DataFrame(rows)

    def test_writes_json_report(self, monitor, tmp_path):
        df = self._telemetry_df(days=14)
        result = monitor.run_nightly_report(df, output_dir=str(tmp_path))
        assert result["method"] == "ks_test_fallback"
        assert "reference_rows" in result and "current_rows" in result

        report_files = list(tmp_path.glob("drift_*.json"))
        assert len(report_files) == 1

    def test_insufficient_data_status(self, monitor, tmp_path):
        # Everything falls in the "current" window -> empty reference split
        df = self._telemetry_df(days=3)
        result = monitor.run_nightly_report(df, output_dir=str(tmp_path))
        assert result["status"] == "insufficient_data"
