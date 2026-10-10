"""WattWise AI — Agent tools (callable functions agents can invoke).

Each tool wraps an existing ML module so agents can query data, run models,
and take actions through a standardized interface.
"""
from __future__ import annotations
import functools
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from ml.agents.base import AgentTool

_data_cache: dict[int, pd.DataFrame] = {}


def _get_data(days: int = 30) -> pd.DataFrame:
    if days not in _data_cache:
        from ml.data_generator import generate_with_cost
        _data_cache[days] = generate_with_cost(days=days, interval_minutes=15)
    return _data_cache[days]


def _get_series(facility_id: str, days: int = 30) -> pd.Series:
    from ml.data_generator import get_facility_demand_series
    df = _get_data(days)
    return get_facility_demand_series(df, facility_id)


# ── Data query tools ─────────────────────────────────────────

def query_facility_stats(facility_id: str = "office", days: int = 30) -> dict:
    """Get summary statistics for a facility."""
    df = _get_data(days)
    fdf = df[df["facility_id"] == facility_id]
    result = {}
    for domain in ["consumption", "demand", "cost"]:
        ddf = fdf[fdf["domain"] == domain]
        if not ddf.empty:
            result[domain] = {
                "total": round(float(ddf["value"].sum()), 2),
                "mean": round(float(ddf["value"].mean()), 4),
                "max": round(float(ddf["value"].max()), 2),
                "min": round(float(ddf["value"].min()), 4),
                "std": round(float(ddf["value"].std()), 4),
                "unit": ddf["unit"].iloc[0],
                "readings": len(ddf),
            }
    return result


def query_all_facilities(days: int = 30) -> dict:
    """Compare stats across all facilities."""
    result = {}
    for fid in ["office", "warehouse", "datacentre"]:
        result[fid] = query_facility_stats(fid, days)
    return result


def query_recent_readings(facility_id: str = "office", domain: str = "demand",
                           n: int = 10) -> list[dict]:
    """Get the N most recent readings for a facility/domain."""
    df = _get_data(30)
    fdf = df[(df["facility_id"] == facility_id) & (df["domain"] == domain)]
    recent = fdf.nlargest(n, "ts")[["ts", "device_class", "value", "unit"]]
    return recent.to_dict(orient="records")


def query_peak_hours(facility_id: str = "office", days: int = 30) -> dict:
    """Identify peak demand hours for a facility."""
    df = _get_data(days)
    demand = df[(df["facility_id"] == facility_id) & (df["domain"] == "demand")].copy()
    demand["hour"] = pd.to_datetime(demand["ts"]).dt.hour
    hourly = demand.groupby("hour")["value"].mean()
    top_5 = hourly.nlargest(5)
    return {
        "peak_hours": {int(h): round(float(v), 2) for h, v in top_5.items()},
        "off_peak_avg": round(float(hourly.nsmallest(5).mean()), 2),
        "peak_avg": round(float(top_5.mean()), 2),
        "peak_to_offpeak_ratio": round(float(top_5.mean() / (hourly.nsmallest(5).mean() + 1e-6)), 2),
    }


# ── ML model tools ──────────────────────────────────────────

def run_anomaly_detection(facility_id: str = "office", days: int = 30) -> dict:
    """Run PyOD anomaly detection on a facility's demand data."""
    from ml.anomaly import AnomalyDetector
    series = _get_series(facility_id, days)
    detector = AnomalyDetector()
    detector.fit(series)
    flags = detector.predict(series)
    scores = detector.score(series)
    anomaly_indices = flags[flags].index
    top_anomalies = []
    for idx in anomaly_indices[:5]:
        top_anomalies.append({
            "timestamp": str(idx),
            "value_kw": round(float(series.loc[idx]), 2),
            "score": round(float(scores.loc[idx]), 4),
        })
    return {
        "facility": facility_id,
        "total_readings": len(series),
        "anomalies_detected": int(flags.sum()),
        "anomaly_rate": round(float(flags.mean() * 100), 2),
        "top_anomalies": top_anomalies,
    }


def run_forecast(facility_id: str = "office", horizon_hours: int = 24) -> dict:
    """Run demand forecast for a facility."""
    from ml.forecasting import ForecastEngine
    series = _get_series(facility_id, 30)
    engine = ForecastEngine()
    forecast = engine.forecast(facility_id, series, horizon_hours=horizon_hours)
    return {
        "facility": facility_id,
        "model_used": forecast["model"].iloc[0],
        "horizon_hours": horizon_hours,
        "peak_predicted_kw": round(float(forecast["predicted_kw"].max()), 2),
        "avg_predicted_kw": round(float(forecast["predicted_kw"].mean()), 2),
        "min_predicted_kw": round(float(forecast["predicted_kw"].min()), 2),
        "forecast_points": len(forecast),
    }


def run_cost_analysis(facility_id: str = "office", days: int = 30) -> dict:
    """Run cost analysis for a facility."""
    from ml.cost_engine import monthly_cost_summary, peak_demand_charge
    df = _get_data(days)
    fdf = df[df["facility_id"] == facility_id]
    cost = fdf[fdf["domain"] == "cost"]
    monthly = monthly_cost_summary(fdf)
    peak = peak_demand_charge(fdf)
    return {
        "facility": facility_id,
        "total_cost_inr": round(float(cost["value"].sum()), 2),
        "avg_cost_per_interval": round(float(cost["value"].mean()), 4),
        "peak_interval_cost": round(float(cost["value"].max()), 4),
        "monthly_summary": monthly.to_dict(orient="records"),
        "peak_demand_charges": peak.to_dict(orient="records"),
    }


def run_peak_optimization(facility_id: str = "office",
                           threshold_kw: float = 150.0) -> dict:
    """Run peak load optimization analysis."""
    from ml.peak_optimizer import PeakOptimizer, ControllableLoad
    optimizer = PeakOptimizer(peak_threshold_kw=threshold_kw)
    training_data = optimizer.generate_synthetic_training_data()
    optimizer.fit(training_data)
    loads = [
        ControllableLoad("HVAC-Zone-A", "hvac", facility_id, 45.0, "high", 0.3, 5.0),
        ControllableLoad("HVAC-Zone-B", "hvac", facility_id, 38.0, "high", 0.4, 5.0),
        ControllableLoad("Lighting-Ext", "lighting", facility_id, 12.0, "high", 0.1, 1.0),
        ControllableLoad("Lighting-Int", "lighting", facility_id, 18.0, "medium", 0.5, 2.0),
        ControllableLoad("Server-Rack-1", "main_meter", facility_id, 55.0, "low", 0.9, 30.0),
        ControllableLoad("EV-Charger", "sub_meter", facility_id, 22.0, "high", 0.2, 1.0),
    ]
    current_demand = sum(l.current_kw for l in loads)
    target_reduction = max(0, current_demand - threshold_kw * 0.85)
    is_peak = optimizer.should_activate(current_demand)
    recs = optimizer.rank_loads(loads, current_demand, target_reduction) if is_peak else []
    return {
        "facility": facility_id,
        "current_demand_kw": current_demand,
        "threshold_kw": threshold_kw,
        "peak_warning": is_peak,
        "recommendations": [
            {"rank": r.rank, "load": r.load_id, "action": r.action,
             "kw_saved": r.estimated_kw_saved, "score": r.shed_score}
            for r in recs
        ],
        "total_saveable_kw": sum(r.estimated_kw_saved for r in recs),
    }


def run_drift_check(days: int = 14) -> dict:
    """Check for data/model drift."""
    from ml.drift_monitor import DriftMonitor
    df = _get_data(days)
    monitor = DriftMonitor()
    demand = df[df["domain"] == "demand"]
    if demand.empty:
        return {"drift_detected": False, "reason": "no demand data"}
    cutoff = demand["ts"].max() - pd.Timedelta(days=monitor.reference_window_days)
    ref = demand[demand["ts"] < cutoff]["value"].to_frame("demand_kw")
    cur = demand[demand["ts"] >= cutoff]["value"].to_frame("demand_kw")
    if ref.empty or cur.empty:
        return {"drift_detected": False, "reason": "insufficient data for split"}
    return monitor.check_data_drift(ref, cur, ["demand_kw"])


def run_optimization_opportunity(days: int = 45) -> list[dict]:
    """Run load-shape clustering to find optimization opportunities."""
    from ml.optimization_clustering import LoadShapeClusterer, build_optimization_narrative_context
    df = _get_data(days)
    clusterer = LoadShapeClusterer(n_clusters=4)
    clusterer.fit(df)
    report = clusterer.opportunity_report(df)
    return [
        {
            "facility": o.facility_id,
            "load_factor": o.facility_load_factor,
            "best_load_factor": o.best_cluster_load_factor,
            "gap": o.load_factor_gap,
            "peak_reduction_kw": o.estimated_peak_reduction_kw,
            "monthly_savings_inr": o.estimated_monthly_demand_charge_savings_inr,
            "narrative_context": build_optimization_narrative_context(o),
        }
        for o in report
    ]


def send_alert(facility_id: str, event_type: str, message: str) -> dict:
    """Send an alert through the trigger system."""
    from triggers.handler import TriggerHandler, EnergyEvent
    handler = TriggerHandler()
    event = EnergyEvent(
        event_type=event_type,
        facility_id=facility_id,
        device_id="agent-system",
        timestamp=datetime.now(timezone.utc),
        observed_value=0.0,
        expected_value=0.0,
        anomaly_score=0.0,
        narrative=message,
    )
    sent = handler.fire(event)
    return {"sent": sent, "facility": facility_id, "type": event_type}


# ── Tool registry ────────────────────────────────────────────

def get_all_tools() -> list[AgentTool]:
    """Return all available agent tools."""
    return [
        AgentTool(
            name="query_facility_stats",
            description="Get energy statistics (consumption, demand, cost) for a facility",
            parameters={"facility_id": "str (office/warehouse/datacentre)", "days": "int (default 30)"},
            func=query_facility_stats,
        ),
        AgentTool(
            name="query_all_facilities",
            description="Compare stats across all three facilities",
            parameters={"days": "int (default 30)"},
            func=query_all_facilities,
        ),
        AgentTool(
            name="query_peak_hours",
            description="Find peak demand hours and peak-to-offpeak ratio",
            parameters={"facility_id": "str", "days": "int (default 30)"},
            func=query_peak_hours,
        ),
        AgentTool(
            name="run_anomaly_detection",
            description="Run PyOD anomaly detection and get flagged anomalies with scores",
            parameters={"facility_id": "str", "days": "int (default 30)"},
            func=run_anomaly_detection,
        ),
        AgentTool(
            name="run_forecast",
            description="Run Chronos demand forecast for a facility",
            parameters={"facility_id": "str", "horizon_hours": "int (default 24)"},
            func=run_forecast,
        ),
        AgentTool(
            name="run_cost_analysis",
            description="Analyze energy costs including monthly summary and demand charges",
            parameters={"facility_id": "str", "days": "int (default 30)"},
            func=run_cost_analysis,
        ),
        AgentTool(
            name="run_peak_optimization",
            description="Get load-shed recommendations when demand exceeds threshold",
            parameters={"facility_id": "str", "threshold_kw": "float (default 150.0)"},
            func=run_peak_optimization,
        ),
        AgentTool(
            name="run_drift_check",
            description="Check for data drift or model degradation",
            parameters={"days": "int (default 14)"},
            func=run_drift_check,
        ),
        AgentTool(
            name="run_optimization_opportunity",
            description="Find energy optimization opportunities via load-shape clustering",
            parameters={"days": "int (default 45)"},
            func=run_optimization_opportunity,
        ),
        AgentTool(
            name="send_alert",
            description="Send an alert to the operations team",
            parameters={"facility_id": "str", "event_type": "str (anomaly/peak_warning/optimization)", "message": "str"},
            func=send_alert,
        ),
    ]
