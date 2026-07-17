"""WattWise AI — historical telemetry generator.

Generates 90+ days of realistic energy telemetry grounded in real-world
consumption patterns (daily/weekly cycles, seasonality, anomaly injection).
Used to train ML models without needing accumulated production data.
"""
from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Generator

import pandas as pd
import numpy as np

from ingestion.schema import TelemetryReading, DOMAIN_UNITS, TOU_RATE_PER_KWH
from ingestion.simulator import FACILITIES, _demand_kw


def generate_historical(
    days: int = 90,
    interval_minutes: int = 5,
    end_time: datetime | None = None,
    anomaly_rate: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a historical telemetry DataFrame.

    Args:
        days: How many days of history to generate.
        interval_minutes: Reading cadence.
        end_time: End timestamp (defaults to now UTC).
        anomaly_rate: Fraction of readings to inject as anomalies.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns matching the ClickHouse telemetry schema.
    """
    random.seed(seed)
    np.random.seed(seed)

    if end_time is None:
        end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    records = []
    ts = start_time
    step = timedelta(minutes=interval_minutes)
    interval_hours = interval_minutes / 60

    while ts <= end_time:
        for facility_id, cfg in FACILITIES.items():
            for device in cfg["devices"]:
                demand = _demand_kw(facility_id, device, ts)

                # Inject anomaly — spike 2-4x normal demand
                is_anomaly = random.random() < anomaly_rate
                if is_anomaly and device["class"] in ("main_meter", "sub_meter", "hvac"):
                    demand *= random.uniform(2.0, 4.0)

                consumption = round(demand * interval_hours, 5)
                cost = round(consumption * TOU_RATE_PER_KWH, 4)

                for domain, value, unit in [
                    ("consumption", consumption, "kWh"),
                    ("demand", demand, "kW"),
                    ("cost", cost, "INR"),
                ]:
                    records.append({
                        "facility_id": facility_id,
                        "device_id": device["id"],
                        "device_class": device["class"],
                        "domain": domain,
                        "ts": ts,
                        "value": value,
                        "unit": unit,
                        "is_anomaly": is_anomaly and domain == "demand",
                    })
        ts += step

    df = pd.DataFrame(records)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def get_facility_demand_series(
    df: pd.DataFrame,
    facility_id: str,
    device_class: str = "main_meter",
) -> pd.Series:
    """Extract a demand time series for one facility's main meter."""
    mask = (
        (df["facility_id"] == facility_id)
        & (df["device_class"] == device_class)
        & (df["domain"] == "demand")
    )
    series = df[mask].set_index("ts")["value"].sort_index()
    return series


def generate_with_cost(days: int = 90, interval_minutes: int = 15,
                       seed: int = 42) -> pd.DataFrame:
    """Generate historical data including the Cost domain via ToU engine."""
    from ml.cost_engine import add_cost_domain
    df = generate_historical(days=days, interval_minutes=interval_minutes, seed=seed)
    df = add_cost_domain(df)
    return df


if __name__ == "__main__":
    print("Generating 90 days of historical data (with cost domain)...")
    df = generate_with_cost(days=90)
    print(f"Generated {len(df):,} records")
    print(df.groupby(["facility_id", "domain"])["value"].describe().round(3))
    anomalies = df[df["is_anomaly"]].shape[0]
    print(f"\nAnomalies injected: {anomalies} ({anomalies/len(df)*100:.1f}%)")
    print(f"\nDomains: {sorted(df['domain'].unique())}")
