"""Unit tests — XGBoost peak demand optimizer."""
import pytest


class TestPeakOptimizer:

    def test_should_activate_above_threshold(self):
        from ml.peak_optimizer import PeakOptimizer
        opt = PeakOptimizer(peak_threshold_kw=100.0, warn_ratio=0.90)
        assert opt.should_activate(95.0) is True
        assert opt.should_activate(80.0) is False

    def test_rank_loads_returns_list(self):
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad
        opt = PeakOptimizer(peak_threshold_kw=100.0)
        training = opt.generate_synthetic_training_data(n_events=100)
        opt.fit(training)
        loads = [
            ControllableLoad("L1", "hvac", "office", 40.0, "high", 0.2, 5.0),
            ControllableLoad("L2", "lighting", "office", 10.0, "high", 0.1, 1.0),
            ControllableLoad("L3", "main_meter", "office", 50.0, "low", 0.9, 30.0),
        ]
        recs = opt.rank_loads(loads, current_demand_kw=100.0, target_reduction_kw=30.0)
        assert len(recs) > 0
        assert recs[0].rank == 1

    def test_high_deferrability_ranked_first(self):
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad
        opt = PeakOptimizer(peak_threshold_kw=100.0)
        training = opt.generate_synthetic_training_data(n_events=200, seed=42)
        opt.fit(training)
        loads = [
            ControllableLoad("EV", "sub_meter", "office", 20.0, "high", 0.1, 1.0),
            ControllableLoad("Server", "main_meter", "office", 60.0, "low", 0.95, 30.0),
        ]
        recs = opt.rank_loads(loads, 80.0, 20.0)
        # EV (high deferrability) should rank before Server (low)
        ev_rank = next(r.rank for r in recs if r.load_id == "EV")
        server_rank = next((r.rank for r in recs if r.load_id == "Server"), 999)
        assert ev_rank < server_rank

    def test_synthetic_training_data_shape(self):
        from ml.peak_optimizer import PeakOptimizer
        opt = PeakOptimizer()
        df = opt.generate_synthetic_training_data(n_events=100)
        assert len(df) == 100
        assert "deferrability_class" in df.columns
        assert "was_shed_first" in df.columns
        assert df["was_shed_first"].isin([0, 1]).all()

    def test_empty_loads_returns_empty(self):
        from ml.peak_optimizer import PeakOptimizer
        opt = PeakOptimizer()
        recs = opt.rank_loads([], 100.0, 20.0)
        assert recs == []
