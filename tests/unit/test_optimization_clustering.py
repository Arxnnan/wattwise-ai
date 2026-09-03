"""Unit tests — ml/optimization_clustering.py (k-means optimization scenario)."""
from __future__ import annotations
import pytest

from ml.optimization_clustering import (
    build_daily_load_shapes,
    LoadShapeClusterer,
    build_optimization_narrative_context,
    ClusterOpportunity,
)


class TestBuildDailyLoadShapes:

    def test_produces_24_hour_columns(self, historical_df):
        shapes = build_daily_load_shapes(historical_df)
        hour_cols = [c for c in shapes.columns if c.startswith("hour_")]
        assert len(hour_cols) == 24

    def test_includes_load_factor_between_0_and_1(self, historical_df):
        shapes = build_daily_load_shapes(historical_df)
        assert (shapes["load_factor"] > 0).all()
        assert (shapes["load_factor"] <= 1.0).all()

    def test_one_row_per_facility_per_day(self, historical_df):
        shapes = build_daily_load_shapes(historical_df)
        assert shapes.groupby(["facility_id", "date"]).size().max() == 1


class TestLoadShapeClusterer:

    def test_fit_returns_cluster_load_factors(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        result = clusterer.fit(historical_df)
        assert len(result["cluster_load_factors"]) == 3
        assert all(0 < v <= 1.0 for v in result["cluster_load_factors"].values())

    def test_raises_with_too_few_days(self):
        import pandas as pd
        tiny_df = pd.DataFrame({
            "facility_id": ["office"], "device_class": ["main_meter"], "domain": ["demand"],
            "ts": pd.to_datetime(["2026-01-01T00:00:00Z"]), "value": [10.0],
        })
        clusterer = LoadShapeClusterer(n_clusters=4)
        with pytest.raises(ValueError, match="complete facility-days"):
            clusterer.fit(tiny_df)

    def test_label_days_requires_fit(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        with pytest.raises(AssertionError, match="fit"):
            clusterer.label_days(historical_df)

    def test_label_days_assigns_valid_cluster_ids(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        clusterer.fit(historical_df)
        labeled = clusterer.label_days(historical_df)
        assert labeled["cluster"].isin(range(3)).all()

    def test_opportunity_report_covers_all_facilities(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        clusterer.fit(historical_df)
        report = clusterer.opportunity_report(historical_df)
        assert {opp.facility_id for opp in report} == {"office", "warehouse", "datacentre"}

    def test_opportunity_report_sorted_by_savings_descending(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        clusterer.fit(historical_df)
        report = clusterer.opportunity_report(historical_df)
        savings = [o.estimated_monthly_demand_charge_savings_inr for o in report]
        assert savings == sorted(savings, reverse=True)

    def test_gap_is_never_negative(self, historical_df):
        clusterer = LoadShapeClusterer(n_clusters=3)
        clusterer.fit(historical_df)
        report = clusterer.opportunity_report(historical_df)
        assert all(o.load_factor_gap >= 0 for o in report)


class TestBuildOptimizationNarrativeContext:

    def test_produces_readable_text_with_key_numbers(self):
        opp = ClusterOpportunity(
            facility_id="office", dominant_cluster=2, facility_load_factor=0.53,
            best_cluster_load_factor=0.85, load_factor_gap=0.32, avg_peak_kw=62.2,
            estimated_peak_reduction_kw=23.7, estimated_monthly_demand_charge_savings_inr=3561.0,
        )
        text = build_optimization_narrative_context(opp)
        assert "0.53" in text
        assert "0.85" in text
        assert "23.7" in text
        assert "3561" in text
