"""WattWise AI — Streamlit Dashboard (Phase 2 — 5 views).

Public demo URL (Streamlit Community Cloud).
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
from datetime import datetime, timezone

st.set_page_config(
    page_title="WattWise AI — Smart Energy Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Header ----
st.title("⚡ WattWise AI")
st.caption("Smart Energy Management Platform · IMPACT pSiddhi 3.0 · S4-I-14 · Semester 4 Integration Mastery")

# ---- Sidebar ----
st.sidebar.header("Controls")
facility = st.sidebar.selectbox("Facility", ["office", "warehouse", "datacentre"])
view = st.sidebar.radio(
    "Dashboard View",
    [
        "View 1 — Real-Time Consumption",
        "View 2 — Demand Pattern Analysis",
        "View 3 — Cost Analysis",
        "View 4 — AI Optimization Intelligence",
        "View 5 — Cross-Facility Benchmarking",
    ]
)
days_back = st.sidebar.slider("History (days)", 1, 90, 30)

# ---- Load data ----
@st.cache_data(ttl=60)
def load_data(days: int) -> pd.DataFrame:
    from ml.data_generator import generate_with_cost
    return generate_with_cost(days=days, interval_minutes=15)

@st.cache_data(ttl=300)
def get_anomalies(facility_id: str, days: int):
    from ml.data_generator import generate_with_cost, get_facility_demand_series
    from ml.anomaly import AnomalyDetector
    df = generate_with_cost(days=days)
    series = get_facility_demand_series(df, facility_id)
    detector = AnomalyDetector(contamination=0.02)
    detector.fit(series)
    flags = detector.predict(series)
    scores = detector.score(series)
    return series, flags, scores

@st.cache_data(ttl=300)
def get_forecast(facility_id: str, days: int, horizon: int = 24):
    from ml.data_generator import generate_with_cost, get_facility_demand_series
    from ml.forecasting import ForecastEngine
    df = generate_with_cost(days=days)
    series = get_facility_demand_series(df, facility_id)
    engine = ForecastEngine()
    return series, engine.forecast(facility_id, series, horizon_hours=horizon)

df = load_data(days_back)
facility_df = df[df["facility_id"] == facility].copy()

# ============================================================
# VIEW 1 — Real-Time Consumption
# ============================================================
if "View 1" in view:
    st.subheader("View 1 — Real-Time Consumption (kWh)")
    cons = facility_df[facility_df["domain"] == "consumption"].copy()
    cons_pivot = cons.groupby(["ts", "device_class"])["value"].sum().unstack(fill_value=0)
    fig = px.area(
        cons_pivot.reset_index(), x="ts",
        y=cons_pivot.columns.tolist(),
        title=f"{facility.title()} — Energy Consumption by Device Class",
        labels={"value": "kWh", "ts": "Time"},
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_layout(height=450, legend_title="Device Class")
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)
    total = cons["value"].sum()
    peak = cons.groupby("ts")["value"].sum().max()
    avg = cons.groupby("ts")["value"].sum().mean()
    col1.metric("Total Consumption", f"{total:,.1f} kWh")
    col2.metric("Peak Interval", f"{peak:.3f} kWh")
    col3.metric("Avg per 15-min", f"{avg:.3f} kWh")
    col4.metric("Facility", facility.title())

# ============================================================
# VIEW 2 — Demand Pattern Analysis
# ============================================================
elif "View 2" in view:
    st.subheader("View 2 — Demand Pattern Analysis (kW)")
    demand = facility_df[facility_df["domain"] == "demand"]
    main_demand = demand[demand["device_class"] == "main_meter"].set_index("ts")["value"].sort_index()

    threshold_kw = st.sidebar.number_input(
        "Peak Threshold (kW)", min_value=10.0, max_value=500.0,
        value=float(main_demand.quantile(0.90)), step=5.0
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=main_demand.index, y=main_demand.values,
                             mode="lines", name="Demand (kW)",
                             line=dict(color="#0ea5e9", width=1.5)))
    fig.add_hline(y=threshold_kw, line_dash="dash", line_color="red",
                  annotation_text=f"Peak threshold: {threshold_kw:.0f} kW")
    fig.update_layout(title=f"{facility.title()} — 15-min Rolling Demand",
                      height=450, xaxis_title="Time", yaxis_title="kW")
    st.plotly_chart(fig, use_container_width=True)

    exceedances = (main_demand > threshold_kw).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Peak Demand", f"{main_demand.max():.1f} kW")
    c2.metric("Avg Demand", f"{main_demand.mean():.1f} kW")
    c3.metric("Threshold Exceedances", int(exceedances), delta_color="inverse")

# ============================================================
# VIEW 3 — Cost Analysis (NEW — Phase 2)
# ============================================================
elif "View 3" in view:
    st.subheader("View 3 — Cost Analysis (INR)")
    from ml.cost_engine import monthly_cost_summary, peak_demand_charge, TouRateConfig

    cost_df = facility_df[facility_df["domain"] == "cost"]

    # Monthly cost trend
    cost_ts = cost_df.groupby("ts")["value"].sum().reset_index()
    cost_ts["ts"] = pd.to_datetime(cost_ts["ts"])
    cost_ts["month"] = cost_ts["ts"].dt.to_period("M").astype(str)

    fig = px.area(cost_ts, x="ts", y="value",
                  title=f"{facility.title()} — Energy Cost Over Time (INR)",
                  labels={"value": "INR", "ts": "Time"},
                  color_discrete_sequence=["#10b981"])
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Monthly summary
    st.subheader("Monthly Cost Summary")
    monthly = monthly_cost_summary(df[df["facility_id"] == facility])
    monthly["month"] = monthly["month"].astype(str)
    st.dataframe(monthly.rename(columns={
        "facility_id": "Facility", "month": "Month",
        "total_cost_inr": "Total Cost (INR)"
    }), use_container_width=True)

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Cost", f"₹{cost_df['value'].sum():,.2f}")
    c2.metric("Avg per 15-min", f"₹{cost_df.groupby('ts')['value'].sum().mean():.3f}")
    c3.metric("Peak Hour Cost", f"₹{cost_df.groupby('ts')['value'].sum().max():.3f}")
    cfg = TouRateConfig()
    c4.metric("Peak Rate", f"₹{cfg.peak_rate_per_kwh}/kWh")

# ============================================================
# VIEW 4 — AI Optimization Intelligence (Phase 2)
# ============================================================
elif "View 4" in view:
    st.subheader("View 4 — AI Optimization Intelligence")

    tab1, tab2, tab3 = st.tabs(["Anomaly Detection", "Demand Forecast", "Peak Shaving"])

    # --- Anomaly tab ---
    with tab1:
        st.markdown("**PyOD 3-Algorithm Ensemble (IsolationForest + COPOD + ECOD)**")
        with st.spinner("Running anomaly detection..."):
            series, flags, scores = get_anomalies(facility, days_back)

        anomaly_df = pd.DataFrame({
            "ts": flags.index, "demand_kw": series[flags.index],
            "is_anomaly": flags.values, "score": scores.values,
        })
        normal = anomaly_df[~anomaly_df["is_anomaly"]]
        anomalies = anomaly_df[anomaly_df["is_anomaly"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=normal["ts"], y=normal["demand_kw"],
                                 mode="lines", name="Normal", line=dict(color="#10b981")))
        fig.add_trace(go.Scatter(x=anomalies["ts"], y=anomalies["demand_kw"],
                                 mode="markers", name="Anomaly",
                                 marker=dict(color="red", size=8, symbol="x")))
        fig.update_layout(title="Consumption Anomaly Detection", height=400)
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        c1.metric("Anomalies Detected", int(flags.sum()))
        c2.metric("Anomaly Rate", f"{flags.mean()*100:.1f}%")

        if not anomalies.empty:
            st.warning(f"⚠️ {len(anomalies)} anomalous readings detected")
            # Generate narrative
            from ml.narrative import NarrativeEngine, NarrativeRequest
            top = anomalies.nlargest(1, "score").iloc[0]
            engine = NarrativeEngine()
            narrative = engine.generate(NarrativeRequest(
                narrative_type="anomaly",
                facility_id=facility,
                device_id="main_meter",
                observed_value=float(top["demand_kw"]),
                expected_value=float(series.mean()),
                anomaly_score=float(top["score"]),
            ))
            st.info(f"**AI Narrative:** {narrative}")

    # --- Forecast tab ---
    with tab2:
        st.markdown("**Chronos Foundation Model + Seasonal Naive Fallback**")
        horizon = st.slider("Forecast horizon (hours)", 6, 48, 24)
        with st.spinner("Running forecast..."):
            demand_series, forecast_df = get_forecast(facility, days_back, horizon)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=demand_series.index[-96:], y=demand_series.values[-96:],
                                 mode="lines", name="Actual (kW)", line=dict(color="#0ea5e9")))
        fig.add_trace(go.Scatter(x=forecast_df["forecast_ts"], y=forecast_df["predicted_kw"],
                                 mode="lines", name="Forecast (kW)",
                                 line=dict(color="#a855f7", dash="dash", width=2)))
        fig.add_trace(go.Scatter(
            x=list(forecast_df["forecast_ts"]) + list(forecast_df["forecast_ts"][::-1]),
            y=list(forecast_df["upper_bound"]) + list(forecast_df["lower_bound"][::-1]),
            fill="toself", fillcolor="rgba(168,85,247,0.1)",
            line=dict(color="rgba(0,0,0,0)"), name="80% CI"
        ))
        fig.update_layout(title=f"{horizon}h Demand Forecast", height=400)
        st.plotly_chart(fig, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Model", forecast_df["model"].iloc[0])
        c2.metric("Peak Forecast", f"{forecast_df['predicted_kw'].max():.1f} kW")
        c3.metric("Avg Forecast", f"{forecast_df['predicted_kw'].mean():.1f} kW")

    # --- Peak Shaving tab ---
    with tab3:
        st.markdown("**XGBoost Load-Ranking Optimizer**")
        from ml.peak_optimizer import PeakOptimizer, ControllableLoad

        threshold = st.slider("Peak threshold (kW)", 50, 300, 150)
        optimizer = PeakOptimizer(peak_threshold_kw=threshold)
        training_data = optimizer.generate_synthetic_training_data()
        optimizer.fit(training_data)

        # Simulate current loads
        loads = [
            ControllableLoad("HVAC-Zone-A", "hvac", facility, 45.0, "high", 0.3, 5.0),
            ControllableLoad("HVAC-Zone-B", "hvac", facility, 38.0, "high", 0.4, 5.0),
            ControllableLoad("Lighting-Ext", "lighting", facility, 12.0, "high", 0.1, 1.0),
            ControllableLoad("Lighting-Int", "lighting", facility, 18.0, "medium", 0.5, 2.0),
            ControllableLoad("Server-Rack-1", "main_meter", facility, 55.0, "low", 0.9, 30.0),
            ControllableLoad("EV-Charger", "sub_meter", facility, 22.0, "high", 0.2, 1.0),
        ]
        current_demand = sum(l.current_kw for l in loads)
        target_reduction = max(0, current_demand - threshold * 0.85)

        if optimizer.should_activate(current_demand):
            st.error(f"⚡ PEAK WARNING: Current demand {current_demand:.0f} kW "
                     f"exceeds {threshold*0.9:.0f} kW warning threshold")
            recs = optimizer.rank_loads(loads, current_demand, target_reduction)
            rec_df = pd.DataFrame([{
                "Rank": r.rank, "Load": r.load_id,
                "Device": r.device_class, "kW": r.current_kw,
                "Action": r.action, "kW Saved": r.estimated_kw_saved,
                "Score": r.shed_score
            } for r in recs])
            st.dataframe(rec_df, use_container_width=True)
            st.success(f"Estimated reduction: {sum(r.estimated_kw_saved for r in recs):.1f} kW")
        else:
            st.success(f"✅ Demand normal: {current_demand:.0f} kW "
                       f"(threshold: {threshold} kW)")

# ============================================================
# VIEW 5 — Cross-Facility Benchmarking (BONUS — exceeds RFP)
# ============================================================
elif "View 5" in view:
    st.subheader("View 5 — Cross-Facility Benchmarking")

    # Facility areas (sq ft) for normalization
    facility_areas = {"office": 5000, "warehouse": 15000, "datacentre": 3000}

    # Aggregate consumption per facility
    all_cons = df[df["domain"] == "consumption"].groupby(
        ["facility_id", "device_class"])["value"].sum().reset_index()
    all_demand = df[df["domain"] == "demand"].groupby(
        "facility_id")["value"].agg(["mean", "max"]).reset_index()
    all_cost = df[df["domain"] == "cost"].groupby(
        "facility_id")["value"].sum().reset_index()

    # Normalized energy intensity (kWh per sq ft)
    summary = all_cons.groupby("facility_id")["value"].sum().reset_index()
    summary["area_sqft"] = summary["facility_id"].map(facility_areas)
    summary["kwh_per_sqft"] = (summary["value"] / summary["area_sqft"]).round(3)
    summary = summary.merge(all_cost.rename(columns={"value": "total_cost_inr"}),
                            on="facility_id")
    summary = summary.merge(all_demand.rename(
        columns={"mean": "avg_demand_kw", "max": "peak_demand_kw"}),
        on="facility_id")
    summary["cost_per_sqft"] = (summary["total_cost_inr"] / summary["area_sqft"]).round(2)

    # Chart — energy intensity
    fig1 = px.bar(summary, x="facility_id", y="kwh_per_sqft",
                  color="facility_id", title="Energy Intensity (kWh per sq ft)",
                  color_discrete_sequence=["#0ea5e9", "#10b981", "#a855f7"],
                  labels={"kwh_per_sqft": "kWh/sq ft", "facility_id": "Facility"})
    fig1.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig1, use_container_width=True)

    # Chart — cost breakdown
    fig2 = px.bar(summary, x="facility_id", y="cost_per_sqft",
                  color="facility_id", title="Cost Intensity (INR per sq ft)",
                  color_discrete_sequence=["#f59e0b", "#ef4444", "#6366f1"],
                  labels={"cost_per_sqft": "INR/sq ft", "facility_id": "Facility"})
    fig2.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

    # Summary table
    st.subheader("Benchmarking Summary")
    display = summary.rename(columns={
        "facility_id": "Facility", "value": "Total kWh",
        "area_sqft": "Area (sq ft)", "kwh_per_sqft": "kWh/sq ft",
        "total_cost_inr": "Total Cost (INR)",
        "avg_demand_kw": "Avg Demand (kW)", "peak_demand_kw": "Peak Demand (kW)",
        "cost_per_sqft": "INR/sq ft"
    })
    st.dataframe(display.round(2), use_container_width=True)

    best = summary.loc[summary["kwh_per_sqft"].idxmin(), "facility_id"]
    st.info(f"**Most energy-efficient facility:** {best.title()} "
            f"({summary.loc[summary['facility_id']==best, 'kwh_per_sqft'].values[0]:.3f} kWh/sq ft)")

# ---- Footer ----
st.divider()
col1, col2, col3 = st.columns(3)
col1.caption("WattWise AI · IMPACT pSiddhi 3.0 · S4-I-14")
col2.caption("Semester 4 Integration Mastery · Azure-deployed")
col3.caption(f"Data: {days_back} days · Facility: {facility.title()}")
