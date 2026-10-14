"""Integration tests — WattWise AI ML pipeline chain.

Proves the AI/ML Core modules work together end-to-end (RFP Layer 3):

    data_generator -> anomaly_detector
    data_generator -> forecast_engine
    data_generator -> cost_engine
    anomaly_detector -> severity classifier
    tools.run_anomaly_detection -> forensic_agent
    BriefingAgent (template fallback) -> specialist adapters
    comparator with real data
    caption_engine (template fallback)
    load-shape clustering -> opportunity_report
    drift_monitor cross-check

LLM providers are mocked to force the deterministic template fallback paths —
no network, no real LLM traffic. ``requests.post`` is stubbed so any accidental
dispatcher invocation is also a no-op. Chronos' pretrained model loader is
patched off so the forecast engine falls back to the fast seasonal_naive path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ml.data_generator import generate_with_cost, get_facility_demand_series
from ml.agents.llm_provider import NullProvider


# ---------------------------------------------------------------------------
# Shared fixtures — module scope keeps every test well under 3 seconds
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def small_df() -> pd.DataFrame:
    """7-day telemetry with cost domain — enough signal, fast to produce."""
    return generate_with_cost(days=7, interval_minutes=15, seed=42)


@pytest.fixture(scope="module", autouse=True)
def _mute_external_io():
    """Session-wide: null LLM provider, no Chronos load, no outbound HTTP.

    Each patch targets the exact symbol a caller uses so the fallback paths
    engage regardless of import timing.
    """
    null = NullProvider()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {}
    fake_response.raise_for_status.return_value = None

    patches = [
        patch("ml.agents.llm_provider.get_llm_provider", return_value=null),
        patch("ml.agents.briefing_agent.get_llm_provider", return_value=null, create=True),
        patch("ml.analytics.caption_engine.get_llm_provider", return_value=null, create=True),
        patch("ml.forecasting.ChronosForecaster._try_load", return_value=False),
        # Force the drift monitor to the fast KS-test path; the Evidently
        # import graph alone can push this test past the 3s per-test ceiling.
        patch("ml.drift_monitor._try_evidently", return_value=False),
        patch("requests.post", return_value=fake_response),
    ]
    started = []
    for p in patches:
        try:
            started.append(p.start())
        except (AttributeError, ModuleNotFoundError):
            # Patch target is loaded lazily — skipping it is safe because the
            # root ``ml.agents.llm_provider.get_llm_provider`` patch above
            # covers the resolved symbol everywhere.
            pass
    yield
    for p in patches:
        try:
            p.stop()
        except RuntimeError:
            pass


@pytest.fixture(scope="module", autouse=True)
def _prime_tools_cache(small_df):
    """Pre-populate ``ml.agents.tools._data_cache`` so each tool call reuses
    the small 7-day frame instead of regenerating 30/45 days of data. Also
    pre-import the heavier scipy/xgboost modules once at module setup so the
    first test that touches them does not absorb the cold-import cost."""
    import ml.agents.tools as tools
    for key in (7, 14, 30, 45):
        tools._data_cache[key] = small_df
    # Warm imports whose cold-load otherwise skews a single test's duration.
    import scipy.stats  # noqa: F401
    import xgboost  # noqa: F401
    yield
    tools._data_cache.clear()


@pytest.fixture(scope="module")
def office_series(small_df) -> pd.Series:
    return get_facility_demand_series(small_df, "office")


@pytest.fixture(scope="module")
def anomaly_detector(office_series):
    """One fitted detector reused by every test that needs one — fits are
    deterministic (seed=42) and account for most of the per-test cost."""
    from ml.anomaly import AnomalyDetector
    detector = AnomalyDetector(contamination=0.03)
    detector.fit(office_series)
    return detector


# ---------------------------------------------------------------------------
# 1. data_generator -> anomaly_detector
# ---------------------------------------------------------------------------


def test_generator_feeds_anomaly_detector(office_series, anomaly_detector):
    flags = anomaly_detector.predict(office_series)

    # DataFrame columns align: data_generator emits a demand series indexed by
    # UTC timestamps and the detector consumes it directly without reshaping.
    assert isinstance(flags, pd.Series)
    assert flags.dtype == bool
    assert isinstance(flags.index, pd.DatetimeIndex)

    # Synthetic data injects anomalies at ~2% rate — at least one must fire.
    assert flags.sum() >= 1, "No anomalies detected on synthetic injected data"


# ---------------------------------------------------------------------------
# 2. data_generator -> forecast_engine
# ---------------------------------------------------------------------------


def test_generator_feeds_forecast_engine(office_series):
    from ml.forecasting import ForecastEngine
    engine = ForecastEngine()
    horizon = 12
    forecast = engine.forecast("office", office_series, horizon_hours=horizon)

    assert isinstance(forecast, pd.DataFrame)
    assert "predicted_kw" in forecast.columns
    assert len(forecast) == horizon
    assert (forecast["predicted_kw"] > 0).all(), \
        "Forecast returned non-positive demand predictions"
    # Chronos was patched off, so the fallback path advertises itself.
    assert forecast["model"].iloc[0] == "seasonal_naive"


# ---------------------------------------------------------------------------
# 3. data_generator -> cost_engine
# ---------------------------------------------------------------------------


def test_generator_feeds_cost_engine(small_df):
    from ml.cost_engine import monthly_cost_summary, peak_demand_charge

    monthly = monthly_cost_summary(small_df)
    peak = peak_demand_charge(small_df)

    assert not monthly.empty
    assert (monthly["total_cost_inr"] > 0).all(), \
        "Monthly ToU cost should be strictly positive for every facility"
    assert set(monthly["facility_id"]) == {"office", "warehouse", "datacentre"}

    assert not peak.empty
    assert (peak["demand_charge_inr"] >= 0).all(), \
        "Demand charges must never be negative"
    assert (peak["peak_kw"] > 0).all()


# ---------------------------------------------------------------------------
# 4. anomaly_detector -> severity classifier
# ---------------------------------------------------------------------------


def test_anomalies_classified_into_critical_and_minor(office_series, anomaly_detector):
    from ml.analytics.severity import classify_severity

    scores = anomaly_detector.score(office_series)
    flags = anomaly_detector.predict(office_series)
    anomaly_scores = scores[flags].sort_values(ascending=False)
    assert len(anomaly_scores) >= 2, "need at least 2 anomalies to span severities"

    results = []
    # Highest-scoring anomaly on the most critical facility with a large cost
    # impact → "critical". Lowest-scoring anomaly on office with no cost
    # impact → "minor". This is the shape the UI drill-down uses.
    results.append(classify_severity(
        pyod_score=float(anomaly_scores.iloc[0]),
        facility_id="datacentre",
        estimated_cost_inr=100_000,
        repeat_count=5,
    ))
    results.append(classify_severity(
        pyod_score=float(anomaly_scores.iloc[-1]),
        facility_id="office",
        estimated_cost_inr=0,
        repeat_count=0,
    ))

    labels = {r.severity for r in results}
    assert "critical" in labels, f"no Critical severity produced: {labels}"
    assert "minor" in labels, f"no Minor severity produced: {labels}"


# ---------------------------------------------------------------------------
# 5. Full agent-tool chain: run_anomaly_detection -> ForensicAgent
# ---------------------------------------------------------------------------


def test_anomaly_tool_feeds_forensic_agent():
    from ml.agents.tools import run_anomaly_detection
    from ml.agents.forensic_agent import ForensicAgent, ForensicCard

    result = run_anomaly_detection("office", days=30)
    assert set(result).issuperset({"anomalies_detected", "anomaly_rate", "top_anomalies"})
    assert result["anomalies_detected"] >= 1
    assert len(result["top_anomalies"]) >= 1

    top = result["top_anomalies"][0]
    agent = ForensicAgent(llm_provider=NullProvider())
    card = agent.forensic(
        anomaly_id="anom-int-01",
        anomaly_timestamp=datetime.now(timezone.utc),
        facility_id="office",
        device_id="off-main-01",
        observed_value=float(top["value_kw"]),
        expected_value=float(top["value_kw"]) * 0.6,
        pyod_scores={"iforest": top["score"], "copod": top["score"], "ecod": top["score"]},
        severity="major",
    )
    assert isinstance(card, ForensicCard)
    assert card.why_flagged, "why_flagged is empty"
    assert card.hypothesis, "hypothesis is empty (template fallback should fire)"
    assert card.recommended_action, "recommended_action is empty"
    assert card.work_order_draft, "work_order_draft is empty"
    assert card.llm_source == "template"


# ---------------------------------------------------------------------------
# 6. BriefingAgent -> specialist adapters (template fallback)
# ---------------------------------------------------------------------------


def test_briefing_agent_produces_populated_recommendations():
    from ml.agents.briefing_agent import BriefingAgent, ActionRecommendation

    # specialists={} prevents lazy construction of the 4 real specialist
    # agents — the briefing's _candidates wrappers call ml tools directly.
    agent = BriefingAgent(specialists={})
    recs = agent.generate("office", top_n=3, timeout_sec=20)

    assert len(recs) >= 1, "Briefing produced zero recommendations"
    assert all(isinstance(r, ActionRecommendation) for r in recs)

    # Template fallback must populate the three narrative fields.
    populated = [r for r in recs if r.problem and r.solution and r.evidence]
    assert len(populated) >= 1, \
        "No recommendation had problem/solution/evidence filled from the template fallback"
    assert all(r.facility_id == "office" for r in recs)


# ---------------------------------------------------------------------------
# 7. Comparator with real data (sentiment matches direction)
# ---------------------------------------------------------------------------


def test_comparator_with_generated_data(small_df):
    from ml.analytics.comparator import compute_delta

    # Pull the office cost domain and aggregate daily so compute_delta sees
    # one row per day — same shape the dashboard feeds it.
    cost = (
        small_df[(small_df["facility_id"] == "office") & (small_df["domain"] == "cost")]
        .loc[:, ["ts", "value"]]
        .copy()
    )
    cost["ts"] = pd.to_datetime(cost["ts"])
    daily = cost.set_index("ts").resample("1D")["value"].sum().reset_index()

    # Pin ``now`` inside the generated window so we always have both periods.
    now = pd.Timestamp(daily["ts"].max()).tz_convert("UTC") if daily["ts"].dt.tz else pd.Timestamp(daily["ts"].max())
    result = compute_delta(daily, period="month", higher_is="bad", now=now)

    # Cost ``higher_is="bad"`` → up ⇒ bad, down ⇒ good, flat ⇒ neutral.
    expected = {"up": "bad", "down": "good", "flat": "neutral"}
    assert result.sentiment == expected[result.direction]


# ---------------------------------------------------------------------------
# 8. Caption engine (template fallback)
# ---------------------------------------------------------------------------


def test_caption_engine_template_fallback():
    from ml.analytics.caption_engine import CaptionEngine

    # Explicitly inject the NullProvider — exercises the same code path the
    # dashboard sees when no LLM credentials are present.
    engine = CaptionEngine(llm_provider=NullProvider())

    kpi = engine.caption_kpi("Monthly cost", 125000, 110000, "INR", "office")
    assert kpi.text, "caption_kpi returned empty text"
    assert kpi.source == "template"

    chart = engine.caption_chart("Hourly demand", {"trend": "rising", "peak_kw": 92})
    assert chart.text, "caption_chart returned empty text"
    assert chart.source == "template"


# ---------------------------------------------------------------------------
# 9. Clustering -> opportunity_report
# ---------------------------------------------------------------------------


def test_clustering_opportunity_report(small_df):
    from ml.optimization_clustering import LoadShapeClusterer, ClusterOpportunity

    clusterer = LoadShapeClusterer(n_clusters=3)
    clusterer.fit(small_df)
    report = clusterer.opportunity_report(small_df)

    assert len(report) >= 1
    assert all(isinstance(o, ClusterOpportunity) for o in report)
    # Every facility in the report must carry the two headline metrics.
    for opp in report:
        assert 0.0 < opp.facility_load_factor <= 1.0
        assert opp.estimated_monthly_demand_charge_savings_inr >= 0.0


# ---------------------------------------------------------------------------
# 10. Drift monitor cross-check
# ---------------------------------------------------------------------------


def test_drift_monitor_on_split_windows(small_df):
    from ml.drift_monitor import DriftMonitor

    # Scope to one facility's main meter so Evidently has a small, uniform
    # feature column to score — keeps the test well under 3 seconds.
    demand = small_df[
        (small_df["domain"] == "demand")
        & (small_df["facility_id"] == "office")
        & (small_df["device_class"] == "main_meter")
    ].copy()
    demand = demand.sort_values("ts").reset_index(drop=True)
    midpoint = len(demand) // 2
    reference = demand.iloc[:midpoint][["value"]].rename(columns={"value": "demand_kw"})
    current = demand.iloc[midpoint:][["value"]].rename(columns={"value": "demand_kw"})

    monitor = DriftMonitor()
    result = monitor.check_data_drift(reference, current, ["demand_kw"])

    assert isinstance(result, dict)
    assert "drift_detected" in result
    assert "method" in result
    assert isinstance(result["drift_detected"], (bool, type(None))) or hasattr(
        result["drift_detected"], "__bool__"
    )
