"""Unit tests — forecasting engine."""
import pytest
import pandas as pd


class TestForecastEngine:

    def test_forecast_returns_dataframe(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        result = engine.forecast("office", office_demand, horizon_hours=6)
        assert isinstance(result, pd.DataFrame)

    def test_forecast_has_required_columns(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        result = engine.forecast("office", office_demand, horizon_hours=6)
        required = {"forecast_ts", "predicted_kw", "lower_bound", "upper_bound", "model"}
        assert required.issubset(result.columns)

    def test_forecast_length(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        horizon = 12
        result = engine.forecast("office", office_demand, horizon_hours=horizon)
        assert len(result) == horizon

    def test_forecast_values_positive(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        result = engine.forecast("office", office_demand, horizon_hours=6)
        assert (result["predicted_kw"] >= 0).all()

    def test_confidence_interval_order(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        result = engine.forecast("office", office_demand, horizon_hours=6)
        assert (result["upper_bound"] >= result["lower_bound"]).all()

    def test_peak_warning_flags_exceedances(self, office_demand):
        from ml.forecasting import ForecastEngine
        engine = ForecastEngine()
        result = engine.forecast("office", office_demand, horizon_hours=24)
        threshold = result["predicted_kw"].min() - 1.0  # always trigger
        warned = engine.peak_warning(result, threshold_kw=threshold)
        assert warned["peak_warning"].all()
