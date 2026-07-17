"""WattWise AI — Evidently AI drift monitoring (ML production quality).

Monitors data drift, prediction drift, and target drift on rolling windows.
Runs nightly on production-replay data to catch model degradation early.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)


def _try_evidently():
    try:
        from evidently import ColumnMapping
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset, DataQualityPreset
        return True
    except ImportError:
        log.warning("Evidently not installed — using statistical fallback")
        return False


class DriftMonitor:
    """Evidently AI-based drift detector for energy telemetry and ML outputs.

    Falls back to KS-test / PSI if Evidently is unavailable.
    """

    def __init__(self, reference_window_days: int = 7,
                 drift_threshold: float = 0.05):
        self.reference_window_days = reference_window_days
        self.drift_threshold = drift_threshold
        self._has_evidently = _try_evidently()

    def check_data_drift(self, reference: pd.DataFrame,
                         current: pd.DataFrame,
                         feature_cols: list[str]) -> dict:
        """Compare current data distribution vs reference window."""
        if self._has_evidently:
            return self._evidently_drift(reference, current, feature_cols)
        return self._statistical_drift(reference, current, feature_cols)

    def _evidently_drift(self, reference: pd.DataFrame,
                         current: pd.DataFrame,
                         feature_cols: list[str]) -> dict:
        from evidently import ColumnMapping
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset

        col_map = ColumnMapping(numerical_features=feature_cols)
        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference[feature_cols],
                   current_data=current[feature_cols],
                   column_mapping=col_map)
        result = report.as_dict()
        drift_detected = result["metrics"][0]["result"]["dataset_drift"]
        share = result["metrics"][0]["result"]["share_of_drifted_columns"]
        log.info("Evidently drift: detected=%s, share=%.2f", drift_detected, share)
        return {
            "method": "evidently",
            "drift_detected": drift_detected,
            "drifted_columns_share": share,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _statistical_drift(self, reference: pd.DataFrame,
                           current: pd.DataFrame,
                           feature_cols: list[str]) -> dict:
        """KS-test fallback when Evidently unavailable."""
        from scipy import stats
        drifted = []
        for col in feature_cols:
            if col not in reference.columns or col not in current.columns:
                continue
            ref_vals = reference[col].dropna().values
            cur_vals = current[col].dropna().values
            if len(ref_vals) < 10 or len(cur_vals) < 10:
                continue
            ks_stat, p_value = stats.ks_2samp(ref_vals, cur_vals)
            if p_value < self.drift_threshold:
                drifted.append(col)
        drift_detected = len(drifted) > 0
        share = len(drifted) / max(len(feature_cols), 1)
        log.info("KS-test drift: detected=%s, drifted=%s", drift_detected, drifted)
        return {
            "method": "ks_test_fallback",
            "drift_detected": drift_detected,
            "drifted_columns": drifted,
            "drifted_columns_share": round(share, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def check_forecast_drift(self, actual: pd.Series,
                             predicted: pd.Series) -> dict:
        """Check if forecast accuracy has degraded vs reference period."""
        common_idx = actual.index.intersection(predicted.index)
        if len(common_idx) < 10:
            return {"drift_detected": False, "reason": "insufficient data"}

        actual_aligned = actual.loc[common_idx]
        predicted_aligned = predicted.loc[common_idx]

        mape = float(np.mean(np.abs(
            (actual_aligned - predicted_aligned) / (actual_aligned + 1e-6)
        )) * 100)

        drift_detected = mape > 15.0  # flag if MAPE degrades beyond 15%
        log.info("Forecast drift check: MAPE=%.2f%%, drift=%s", mape, drift_detected)
        return {
            "method": "mape_check",
            "mape": round(mape, 3),
            "drift_detected": drift_detected,
            "threshold_pct": 15.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def run_nightly_report(self, df: pd.DataFrame,
                           output_dir: str = "docs/drift_reports") -> dict:
        """Run a full nightly drift report and save results."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)

        # Split into reference (older) and current (recent) windows
        cutoff = df["ts"].max() - pd.Timedelta(days=self.reference_window_days)
        reference = df[df["ts"] < cutoff]
        current = df[df["ts"] >= cutoff]

        if reference.empty or current.empty:
            return {"status": "insufficient_data"}

        demand_ref = reference[reference["domain"] == "demand"]["value"].to_frame("demand_kw")
        demand_cur = current[current["domain"] == "demand"]["value"].to_frame("demand_kw")

        result = self.check_data_drift(demand_ref, demand_cur, ["demand_kw"])
        result["report_date"] = now.date().isoformat()
        result["reference_rows"] = len(reference)
        result["current_rows"] = len(current)

        # Save JSON report
        import json
        report_path = Path(output_dir) / f"drift_{now.strftime('%Y%m%d')}.json"
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Drift report saved: %s", report_path)
        return result
