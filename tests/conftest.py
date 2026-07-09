"""WattWise AI — shared test fixtures."""
import pytest
import pandas as pd
from datetime import datetime, timezone

from ingestion.schema import TelemetryReading
from ml.data_generator import generate_historical, get_facility_demand_series


@pytest.fixture(scope="session")
def sample_reading() -> TelemetryReading:
    return TelemetryReading(
        facility_id="office",
        device_id="off-main-01",
        device_class="main_meter",
        domain="demand",
        timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        value=42.5,
        unit="kW",
        metadata={"rolling_window_minutes": 15},
    )


@pytest.fixture(scope="session")
def historical_df() -> pd.DataFrame:
    """30 days of historical data (faster than 90 for tests)."""
    return generate_historical(days=30, interval_minutes=15, seed=42)


@pytest.fixture(scope="session")
def office_demand(historical_df) -> pd.Series:
    return get_facility_demand_series(historical_df, "office")


@pytest.fixture(scope="session")
def warehouse_demand(historical_df) -> pd.Series:
    return get_facility_demand_series(historical_df, "warehouse")
