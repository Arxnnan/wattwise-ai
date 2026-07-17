"""WattWise AI — Cost domain (3rd energy domain).

Time-of-Use (ToU) rate engine converts consumption (kWh) → cost (INR).
Covers: flat rate, peak/off-peak ToU, demand charge component.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import pandas as pd
import numpy as np


@dataclass
class TouRateConfig:
    """Time-of-Use rate configuration."""
    flat_rate_per_kwh: float = 8.0          # Rs/kWh flat rate
    peak_rate_per_kwh: float = 12.0         # Rs/kWh during peak hours
    offpeak_rate_per_kwh: float = 5.5       # Rs/kWh off-peak
    peak_hours: tuple = (9, 18)             # 9 AM to 6 PM
    demand_charge_per_kw: float = 150.0     # Rs/kW for peak demand
    weekend_discount: float = 0.15          # 15% discount on weekends


RATE_CONFIG = TouRateConfig()


def get_rate(ts: datetime, config: TouRateConfig = RATE_CONFIG) -> float:
    """Return Rs/kWh rate for a given timestamp."""
    hour = ts.hour
    is_weekend = ts.weekday() >= 5
    peak_start, peak_end = config.peak_hours

    if peak_start <= hour < peak_end and not is_weekend:
        rate = config.peak_rate_per_kwh
    else:
        rate = config.offpeak_rate_per_kwh

    if is_weekend:
        rate *= (1 - config.weekend_discount)

    return round(rate, 4)


def consumption_to_cost(consumption_kwh: float, ts: datetime,
                        config: TouRateConfig = RATE_CONFIG) -> float:
    """Convert kWh consumption to INR cost using ToU rates."""
    rate = get_rate(ts, config)
    return round(consumption_kwh * rate, 4)


def add_cost_domain(df: pd.DataFrame,
                    config: TouRateConfig = RATE_CONFIG) -> pd.DataFrame:
    """Add cost rows to a telemetry DataFrame that has consumption rows."""
    consumption_rows = df[df["domain"] == "consumption"].copy()
    if consumption_rows.empty:
        return df

    cost_rows = consumption_rows.copy()
    cost_rows["domain"] = "cost"
    cost_rows["unit"] = "INR"

    def calc_cost(row):
        ts = row["ts"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        return consumption_to_cost(row["value"], ts, config)

    cost_rows["value"] = cost_rows.apply(calc_cost, axis=1)
    result = pd.concat([df, cost_rows], ignore_index=True)
    return result.sort_values(["facility_id", "device_id", "domain", "ts"]).reset_index(drop=True)


def monthly_cost_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise monthly cost per facility."""
    cost_df = df[df["domain"] == "cost"].copy()
    cost_df["month"] = pd.to_datetime(cost_df["ts"]).dt.to_period("M")
    summary = (
        cost_df.groupby(["facility_id", "month"])["value"]
        .sum()
        .reset_index()
        .rename(columns={"value": "total_cost_inr"})
    )
    summary["total_cost_inr"] = summary["total_cost_inr"].round(2)
    return summary


def peak_demand_charge(df: pd.DataFrame,
                       config: TouRateConfig = RATE_CONFIG) -> pd.DataFrame:
    """Calculate peak demand charge per facility per month."""
    demand_df = df[df["domain"] == "demand"].copy()
    demand_df["month"] = pd.to_datetime(demand_df["ts"]).dt.to_period("M")
    peak = (
        demand_df.groupby(["facility_id", "month"])["value"]
        .max()
        .reset_index()
        .rename(columns={"value": "peak_kw"})
    )
    peak["demand_charge_inr"] = (peak["peak_kw"] * config.demand_charge_per_kw).round(2)
    return peak
