"""Unit tests — Cost domain (ToU rate engine)."""
import pytest
from datetime import datetime, timezone
import pandas as pd


class TestCostEngine:

    def test_peak_rate_higher_than_offpeak(self):
        from ml.cost_engine import get_rate, TouRateConfig
        cfg = TouRateConfig()
        peak_ts = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)  # Monday noon
        offpeak_ts = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)  # Monday 2am
        assert get_rate(peak_ts, cfg) > get_rate(offpeak_ts, cfg)

    def test_weekend_discount_applied(self):
        from ml.cost_engine import get_rate, TouRateConfig
        cfg = TouRateConfig()
        weekday = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)  # Monday
        weekend = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)  # Saturday
        assert get_rate(weekend, cfg) < get_rate(weekday, cfg)

    def test_consumption_to_cost_positive(self):
        from ml.cost_engine import consumption_to_cost
        ts = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        cost = consumption_to_cost(10.0, ts)
        assert cost > 0

    def test_cost_proportional_to_consumption(self):
        from ml.cost_engine import consumption_to_cost
        ts = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        cost1 = consumption_to_cost(10.0, ts)
        cost2 = consumption_to_cost(20.0, ts)
        assert abs(cost2 - 2 * cost1) < 0.001

    def test_add_cost_domain_adds_rows(self, historical_df):
        from ml.cost_engine import add_cost_domain
        df_with_cost = add_cost_domain(historical_df)
        assert "cost" in df_with_cost["domain"].unique()
        cost_rows = df_with_cost[df_with_cost["domain"] == "cost"]
        assert len(cost_rows) > 0
        assert (cost_rows["unit"] == "INR").all()
        assert (cost_rows["value"] >= 0).all()

    def test_monthly_cost_summary_shape(self, historical_df):
        from ml.cost_engine import add_cost_domain, monthly_cost_summary
        df = add_cost_domain(historical_df)
        summary = monthly_cost_summary(df[df["facility_id"] == "office"])
        assert "total_cost_inr" in summary.columns
        assert len(summary) > 0
        assert (summary["total_cost_inr"] >= 0).all()
