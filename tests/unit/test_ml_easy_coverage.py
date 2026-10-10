"""Coverage closeout for ml.anomaly / ml.cost_engine / ml.data_generator /
ml.peak_optimizer — targets the small remaining uncovered branches
(save/load, empty-input guards, rule-based fallback, __main__ block)."""
from __future__ import annotations

import runpy
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# --------------------------------------------------------------------------- #
# ml.anomaly — save/load round-trip                                           #
# --------------------------------------------------------------------------- #
class TestAnomalySaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path, office_demand):
        from ml.anomaly import AnomalyDetector

        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)
        flags_before = detector.predict(office_demand)

        model_path = tmp_path / "nested" / "detector.pkl"
        detector.save(model_path)
        assert model_path.exists()

        loaded = AnomalyDetector.load(model_path)
        flags_after = loaded.predict(office_demand)
        # loaded detector should produce identical flags
        assert flags_after.equals(flags_before)

    def test_save_accepts_str_path(self, tmp_path, office_demand):
        from ml.anomaly import AnomalyDetector

        detector = AnomalyDetector(contamination=0.02)
        detector.fit(office_demand)
        p = str(tmp_path / "det_str.pkl")
        detector.save(p)
        loaded = AnomalyDetector.load(p)
        assert loaded._fitted is True


# --------------------------------------------------------------------------- #
# ml.cost_engine — empty-consumption guard & peak_demand_charge               #
# --------------------------------------------------------------------------- #
class TestCostEngineEdges:
    def test_add_cost_domain_returns_early_when_no_consumption(self):
        from ml.cost_engine import add_cost_domain

        df = pd.DataFrame(
            {
                "facility_id": ["office", "office"],
                "device_id": ["d1", "d1"],
                "device_class": ["main_meter", "main_meter"],
                "domain": ["demand", "demand"],
                "ts": pd.to_datetime(
                    ["2026-01-01T10:00:00Z", "2026-01-01T10:15:00Z"], utc=True
                ),
                "value": [30.0, 32.0],
                "unit": ["kW", "kW"],
                "is_anomaly": [False, False],
            }
        )
        out = add_cost_domain(df)
        # No consumption rows → function returns the (filtered) frame as-is,
        # no cost rows added.
        assert "cost" not in out["domain"].unique()
        assert len(out) == 2

    def test_peak_demand_charge_computes_per_facility_month(self):
        from ml.cost_engine import peak_demand_charge, TouRateConfig

        ts0 = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        rows = []
        # office: Jan peaks 50 kW, Feb peaks 80 kW
        rows.append({"facility_id": "office", "domain": "demand",
                     "ts": ts0, "value": 20.0})
        rows.append({"facility_id": "office", "domain": "demand",
                     "ts": ts0 + timedelta(hours=1), "value": 50.0})
        rows.append({"facility_id": "office", "domain": "demand",
                     "ts": ts0 + timedelta(days=20), "value": 80.0})
        # a non-demand row that must be filtered out
        rows.append({"facility_id": "office", "domain": "consumption",
                     "ts": ts0, "value": 999.0})
        df = pd.DataFrame(rows)

        cfg = TouRateConfig()
        charges = peak_demand_charge(df, cfg)

        assert set(["facility_id", "month", "peak_kw", "demand_charge_inr"]).issubset(
            charges.columns
        )
        assert len(charges) == 2  # Jan + Feb
        jan = charges[charges["month"].astype(str) == "2026-01"].iloc[0]
        feb = charges[charges["month"].astype(str) == "2026-02"].iloc[0]
        assert jan["peak_kw"] == 50.0
        assert feb["peak_kw"] == 80.0
        assert jan["demand_charge_inr"] == round(50.0 * cfg.demand_charge_per_kw, 2)
        assert feb["demand_charge_inr"] == round(80.0 * cfg.demand_charge_per_kw, 2)


# --------------------------------------------------------------------------- #
# ml.data_generator — generate_with_cost wrapper + __main__ block             #
# --------------------------------------------------------------------------- #
class TestDataGeneratorExtras:
    def test_generate_with_cost_returns_cost_domain(self):
        from ml.data_generator import generate_with_cost

        # Small range to keep this fast.
        df = generate_with_cost(days=1, interval_minutes=60, seed=1)
        assert "cost" in df["domain"].unique()
        cost_rows = df[df["domain"] == "cost"]
        assert (cost_rows["unit"] == "INR").all()

    def test_main_block_executes(self, capsys):
        """Run the module's __main__ guard with a mocked generator to keep
        it fast while still executing the print/describe lines."""
        small = pd.DataFrame(
            {
                "facility_id": ["office"] * 6,
                "device_id": ["d1"] * 6,
                "device_class": ["main_meter"] * 6,
                "domain": ["consumption", "demand", "cost"] * 2,
                "ts": pd.date_range(
                    "2026-01-01", periods=6, freq="h", tz="UTC"
                ),
                "value": [1.0, 10.0, 8.0, 1.0, 11.0, 8.5],
                "unit": ["kWh", "kW", "INR"] * 2,
                "is_anomaly": [False, True, False, False, False, False],
            }
        )
        with patch("ml.data_generator.generate_with_cost", return_value=small):
            runpy.run_module("ml.data_generator", run_name="__main__")
        out = capsys.readouterr().out
        assert "Generated" in out
        assert "Anomalies injected" in out
        assert "Domains:" in out


# --------------------------------------------------------------------------- #
# ml.peak_optimizer — fallback paths                                          #
# --------------------------------------------------------------------------- #
class TestPeakOptimizerFallbacks:
    def test_fit_falls_back_when_training_data_invalid(self):
        """Missing columns → XGBoost raises → except branch records fallback."""
        from ml.peak_optimizer import PeakOptimizer

        opt = PeakOptimizer()
        bad = pd.DataFrame({"not_the_right": [1, 2, 3]})
        result = opt.fit(bad)
        assert result == {"method": "rule_based_fallback"}
        assert opt._fitted is True
        assert opt._model is None

    def test_rank_loads_uses_rule_based_when_model_missing(self):
        """Without fit() the model is None → rule-based ranker is exercised."""
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad

        opt = PeakOptimizer(peak_threshold_kw=100.0)
        loads = [
            ControllableLoad("A", "hvac", "office", 40.0, "high", 0.1, 2.0),
            ControllableLoad("B", "lighting", "office", 10.0, "medium", 0.5, 5.0),
            ControllableLoad("C", "server", "office", 60.0, "low", 0.95, 30.0),
            # unknown class exercises the defer_weight.get(..., 0.5) default
            ControllableLoad("D", "misc", "office", 5.0, "unknown", 0.2, 10.0),
        ]
        recs = opt.rank_loads(loads, current_demand_kw=120.0,
                              target_reduction_kw=40.0)
        assert len(recs) >= 1
        # Highest-score load is ranked first and gets DEFER (high deferrability).
        assert recs[0].rank == 1
        assert recs[0].load_id == "A"
        assert recs[0].action == "DEFER"
        # Loop stops once cumulative kw saved >= target_reduction_kw.
        total = sum(r.current_kw for r in recs)
        assert total >= 40.0

    def test_rank_loads_rule_based_reduce_action(self):
        """Covers the 'REDUCE' branch (non-high deferrability) with
        estimated_kw_saved = current_kw * 0.5."""
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad

        opt = PeakOptimizer()
        loads = [
            ControllableLoad("X", "hvac", "office", 20.0, "medium", 0.3, 3.0),
        ]
        recs = opt.rank_loads(loads, current_demand_kw=80.0,
                              target_reduction_kw=5.0)
        assert len(recs) == 1
        assert recs[0].action == "REDUCE"
        assert recs[0].estimated_kw_saved == pytest.approx(10.0)
