"""Unit tests — historical data generator."""
import pytest
import pandas as pd


class TestDataGenerator:

    def test_generates_correct_row_count(self):
        from ml.data_generator import generate_historical
        # 1 day, 15-min interval = ~97 intervals (inclusive end)
        # 3 facilities x 6 devices x 3 domains = 54 per interval
        df = generate_historical(days=1, interval_minutes=15)
        # Allow ±2 intervals for boundary inclusivity
        assert 54 * 95 <= len(df) <= 54 * 99

    def test_all_three_domains_present(self, historical_df):
        domains = set(historical_df["domain"].unique())
        assert domains == {"consumption", "demand", "cost"}

    def test_all_three_facilities_present(self, historical_df):
        facilities = set(historical_df["facility_id"].unique())
        assert facilities == {"office", "warehouse", "datacentre"}

    def test_no_negative_values(self, historical_df):
        assert (historical_df["value"] >= 0).all()

    def test_consumption_unit_is_kwh(self, historical_df):
        cons = historical_df[historical_df["domain"] == "consumption"]
        assert (cons["unit"] == "kWh").all()

    def test_demand_unit_is_kw(self, historical_df):
        dem = historical_df[historical_df["domain"] == "demand"]
        assert (dem["unit"] == "kW").all()

    def test_cost_unit_is_inr(self, historical_df):
        cost = historical_df[historical_df["domain"] == "cost"]
        assert (cost["unit"] == "INR").all()

    def test_anomaly_rate_near_target(self, historical_df):
        demand_df = historical_df[historical_df["domain"] == "demand"]
        rate = demand_df["is_anomaly"].mean()
        # Default rate is 2% — should be within 1%
        assert 0.01 <= rate <= 0.03, f"Anomaly rate {rate:.3f} out of expected range"

    def test_reproducible_with_seed(self):
        from ml.data_generator import generate_historical
        df1 = generate_historical(days=3, seed=99)
        df2 = generate_historical(days=3, seed=99)
        assert df1["value"].sum() == df2["value"].sum()
