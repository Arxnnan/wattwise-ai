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

    def test_add_cost_domain_is_idempotent_not_additive(self, historical_df):
        # historical_df already has a flat-rate 'cost' domain from
        # generate_historical(); calling add_cost_domain() on it must
        # REPLACE those rows with ToU-priced ones, not add a second set —
        # regression guard for a bug where generate_with_cost() silently
        # produced two cost rows per reading with different values.
        from ml.cost_engine import add_cost_domain

        n_consumption = (historical_df["domain"] == "consumption").sum()
        n_cost_before = (historical_df["domain"] == "cost").sum()
        assert n_cost_before > 0  # sanity: fixture really does pre-seed a cost domain

        result = add_cost_domain(historical_df)
        n_cost_after = (result["domain"] == "cost").sum()

        assert n_cost_after == n_consumption
        dup_check = result[result["domain"] == "cost"].duplicated(
            subset=["facility_id", "device_id", "ts"]
        )
        assert not dup_check.any()

    def test_add_cost_domain_called_twice_is_stable(self, historical_df):
        from ml.cost_engine import add_cost_domain
        once = add_cost_domain(historical_df)
        twice = add_cost_domain(once)
        n_cost_once = (once["domain"] == "cost").sum()
        n_cost_twice = (twice["domain"] == "cost").sum()
        assert n_cost_once == n_cost_twice

    def test_monthly_cost_summary_shape(self, historical_df):
        from ml.cost_engine import add_cost_domain, monthly_cost_summary
        df = add_cost_domain(historical_df)
        summary = monthly_cost_summary(df[df["facility_id"] == "office"])
        assert "total_cost_inr" in summary.columns
        assert len(summary) > 0
        assert (summary["total_cost_inr"] >= 0).all()
