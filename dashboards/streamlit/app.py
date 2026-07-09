"""WattWise AI — Streamlit demo dashboard.

Public demo URL (deployed to Streamlit Community Cloud).
Shows live simulated energy data + AI insights.
Run locally: streamlit run dashboards/streamlit/app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta, timezone

from ml.data_generator import generate_historical, get_facility_demand_series
from ml.anomaly import AnomalyDetector
from ml.forecasting import ForecastEngine

st.set_page_config(
    page_title="WattWise AI — Smart Energy Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Header ----
st.title("⚡ WattWise AI")
st.caption("Smart Energy Management Platform · IMPACT pSiddhi 3.0 · S4-I-14")

# ---- Sidebar ----
st.sidebar.header("Controls")
facility = st.sidebar.selectbox("Facility", ["office", "warehouse", "datacentre"])
view = st.sidebar.radio(
    "Dashboard View",
    ["Real-Time Consumption", "Demand Pattern Analysis",
     "AI Anomaly Detection", "Demand Forecast"]
)
days_back = st.sidebar.slider("History (days)", 1, 90, 7)

# ---- Load data (cached) ----
@st.cache_data(ttl=60)
def load_data(days: int) -> pd.DataFrame:
    return generate_historical(days=days, interval_minutes=15)


df = load_data(days_back)
facility_df = df[df["facility_id"] == facility].copy()

# ============================================================
# VIEW 1 — Real-Time Consumption
# ============================================================
if view == "Real-Time Consumption":
    st.subheader("View 1 — Real-Time Consumption (kWh)")

    cons = facility_df[facility_df["domain"] == "consumption"].copy()
    cons_pivot = cons.groupby(["ts", "device_class"])["value"].sum().unstack(fill_value=0)

    fig = px.area(
        cons_pivot.reset_index(),
        x="ts",
        y=cons_pivot.columns.tolist(),
        title=f"{facility.title()} — Energy Consumption by Device Class",
        labels={"value": "kWh", "ts": "Time"},
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_layout(height=450, legend_title="Device Class")
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    total_kwh = cons["value"].sum()
    peak_kwh = cons.groupby("ts")["value"].sum().max()
    col1.metric("Total Consumption", f"{total_kwh:,.1f} kWh")
    col2.metric("Peak Hour", f"{peak_kwh:,.2f} kWh")
    col3.metric("Avg per 15-min", f"{cons.groupby('ts')['value'].sum().mean():.3f} kWh")

# ============================================================
# VIEW 2 — Demand Pattern Analysis
# ============================================================
elif view == "Demand Pattern Analysis":
    st.subheader("View 2 — Demand Pattern Analysis (kW)")

    demand = facility_df[facility_df["domain"] == "demand"]
    main_demand = demand[demand["device_class"] == "main_meter"].copy()
    main_demand = main_demand.set_index("ts")["value"].sort_index()

    threshold_kw = st.sidebar.number_input(
        "Peak Threshold (kW)", min_value=10.0, max_value=500.0,
        value=float(main_demand.quantile(0.90)), step=5.0
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=main_demand.index, y=main_demand.values,
        mode="lines", name="Demand (kW)",
        line=dict(color="#0ea5e9", width=1.5)
    ))
    fig.add_hline(
        y=threshold_kw, line_dash="dash", line_color="red",
        annotation_text=f"Peak threshold: {threshold_kw:.0f} kW"
    )
    fig.update_layout(
        title=f"{facility.title()} — 15-min Rolling Demand",
        xaxis_title="Time", yaxis_title="kW", height=450
    )
    st.plotly_chart(fig, use_container_width=True)

    exceedances = (main_demand > threshold_kw).sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("Peak Demand", f"{main_demand.max():.1f} kW")
    col2.metric("Avg Demand", f"{main_demand.mean():.1f} kW")
    col3.metric("Threshold Exceedances", exceedances, delta_color="inverse")

# ============================================================
# VIEW 3 — AI Anomaly Detection
# ============================================================
elif view == "AI Anomaly Detection":
    st.subheader("View 3 — AI Anomaly Detection (PyOD Ensemble)")

    demand = facility_df[
        (facility_df["domain"] == "demand") &
        (facility_df["device_class"] == "main_meter")
    ].set_index("ts")["value"].sort_index()

    with st.spinner("Running PyOD anomaly detection..."):
        detector = AnomalyDetector(contamination=0.02)
        detector.fit(demand)
        flags = detector.predict(demand)
        scores = detector.score(demand)

    anomaly_df = pd.DataFrame({
        "ts": flags.index,
        "demand_kw": demand[flags.index],
        "is_anomaly": flags.values,
        "score": scores.values,
    })

    fig = go.Figure()
    normal = anomaly_df[~anomaly_df["is_anomaly"]]
    anomalies = anomaly_df[anomaly_df["is_anomaly"]]

    fig.add_trace(go.Scatter(
        x=normal["ts"], y=normal["demand_kw"],
        mode="lines", name="Normal", line=dict(color="#10b981")
    ))
    fig.add_trace(go.Scatter(
        x=anomalies["ts"], y=anomalies["demand_kw"],
        mode="markers", name="Anomaly",
        marker=dict(color="red", size=8, symbol="x")
    ))
    fig.update_layout(
        title=f"{facility.title()} — Anomaly Detection (PyOD: IF + COPOD + ECOD)",
        xaxis_title="Time", yaxis_title="kW", height=450
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    col1.metric("Anomalies Detected", int(flags.sum()))
    col2.metric("Anomaly Rate", f"{flags.mean()*100:.1f}%")

    if not anomalies.empty:
        st.warning(f"⚠️ {len(anomalies)} anomalous demand readings detected in {facility}")
        st.dataframe(anomalies.sort_values("score", ascending=False).head(10))

# ============================================================
# VIEW 4 — Demand Forecast
# ============================================================
elif view == "Demand Forecast":
    st.subheader("View 4 — AI Demand Forecast (Chronos Foundation Model)")

    demand = facility_df[
        (facility_df["domain"] == "demand") &
        (facility_df["device_class"] == "main_meter")
    ].set_index("ts")["value"].sort_index()

    horizon = st.sidebar.slider("Forecast horizon (hours)", 6, 48, 24)

    with st.spinner("Running Chronos forecast..."):
        engine = ForecastEngine()
        forecast_df = engine.forecast(facility, demand, horizon_hours=horizon)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=demand.index[-96:], y=demand.values[-96:],
        mode="lines", name="Actual (kW)", line=dict(color="#0ea5e9")
    ))
    fig.add_trace(go.Scatter(
        x=forecast_df["forecast_ts"], y=forecast_df["predicted_kw"],
        mode="lines", name="Forecast (kW)",
        line=dict(color="#a855f7", dash="dash", width=2)
    ))
    fig.add_trace(go.Scatter(
        x=list(forecast_df["forecast_ts"]) + list(forecast_df["forecast_ts"][::-1]),
        y=list(forecast_df["upper_bound"]) + list(forecast_df["lower_bound"][::-1]),
        fill="toself", fillcolor="rgba(168,85,247,0.1)",
        line=dict(color="rgba(0,0,0,0)"), name="80% CI"
    ))
    fig.update_layout(
        title=f"{facility.title()} — {horizon}h Demand Forecast",
        xaxis_title="Time", yaxis_title="kW", height=450
    )
    st.plotly_chart(fig, use_container_width=True)

    model_used = forecast_df["model"].iloc[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Model", model_used)
    col2.metric("Peak Forecast", f"{forecast_df['predicted_kw'].max():.1f} kW")
    col3.metric("Avg Forecast", f"{forecast_df['predicted_kw'].mean():.1f} kW")

    st.info(f"Forecast generated using **{model_used}** — "
            f"{'zero-shot foundation model (no training required)' if model_used == 'chronos' else 'statistical model'}")

# ---- Footer ----
st.divider()
st.caption("WattWise AI · IMPACT pSiddhi 3.0 · S4-I-14 · "
           "Semester 4 Integration Mastery · Azure-deployed")
