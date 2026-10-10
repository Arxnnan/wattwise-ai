"""Unit tests for ViewRecommender.

Zero real LLM calls — the BriefingAgent dependency is mocked everywhere.
Each test completes well under 500ms.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ml.agents.briefing_agent import ActionRecommendation, BriefingAgent
from ml.analytics.view_recommender import (
    VIEW_TO_CATEGORY,
    ViewRecommendation,
    ViewRecommender,
    _format_inr,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _rec(
    *,
    category: str = "optimization",
    impact: float = 10_000.0,
    confidence: float = 0.8,
    agent_name: str = "OptimizerAgent",
    title: str = "Shed non-critical load",
    action_type: str = "shed_load",
    facility_id: str = "FAC-1",
    device_id: str = "HVAC-01",
) -> ActionRecommendation:
    return ActionRecommendation(
        id=f"rec-{category}-{int(impact)}",
        created_at=datetime.now(timezone.utc),
        facility_id=facility_id,
        category=category,  # type: ignore[arg-type]
        agent_name=agent_name,
        title=title,
        rationale="because telemetry says so",
        impact_inr_month=impact,
        confidence=confidence,
        action_type=action_type,  # type: ignore[arg-type]
        one_click_payload={"device_id": device_id},
        counterfactual="without this action the issue persists",
    )


@pytest.fixture
def mock_briefing():
    """A MagicMock constrained to the BriefingAgent surface."""
    agent = MagicMock(spec=BriefingAgent)
    agent.generate.return_value = [
        _rec(category="anomaly",      impact=25_000, confidence=0.9),
        _rec(category="cost",         impact=22_500, confidence=0.8),
        _rec(category="optimization", impact=18_000, confidence=0.7),
        _rec(category="forecast",     impact=12_000, confidence=0.6),
    ]
    return agent


# ---------------------------------------------------------------------------
# recommend() — chat view returns None
# ---------------------------------------------------------------------------


def test_recommend_returns_none_for_chat_view(mock_briefing):
    rec = ViewRecommender(mock_briefing).recommend("AI Chat Agent", "FAC-1")
    assert rec is None
    # The chat view short-circuits before calling the agent.
    mock_briefing.generate.assert_not_called()


def test_recommend_returns_none_for_unknown_view(mock_briefing):
    rec = ViewRecommender(mock_briefing).recommend("Nonexistent View", "FAC-1")
    assert rec is None
    mock_briefing.generate.assert_not_called()


# ---------------------------------------------------------------------------
# recommend() — top-category per view
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "view, expected_category",
    [
        ("Real-Time Consumption",    "anomaly"),
        ("Demand Pattern Analysis",  "optimization"),
        ("Cost Analysis",            "cost"),
        ("AI Optimization",          "anomaly"),
        ("Cross-Facility Benchmark", "optimization"),
    ],
)
def test_recommend_returns_top_category_rec(mock_briefing, view, expected_category):
    recommender = ViewRecommender(mock_briefing)
    rec = recommender.recommend(view, "FAC-1")
    assert rec is not None
    assert isinstance(rec, ViewRecommendation)
    assert rec.view == view
    assert rec.category == expected_category
    assert rec.facility_id == "FAC-1"
    # business framing fields are always populated
    assert rec.business_value
    assert rec.why_this_matters


def test_recommend_full_sweep_picks_first_priority(mock_briefing):
    rec = ViewRecommender(mock_briefing).recommend("Full Agent Sweep", "FAC-1")
    assert rec is not None
    # VIEW_TO_CATEGORY['Full Agent Sweep'] starts with 'anomaly'.
    assert rec.category == "anomaly"


# ---------------------------------------------------------------------------
# recommend() — empty briefing
# ---------------------------------------------------------------------------


def test_recommend_none_when_briefing_empty():
    agent = MagicMock(spec=BriefingAgent)
    agent.generate.return_value = []
    recommender = ViewRecommender(agent)
    assert recommender.recommend("Cost Analysis", "FAC-1") is None


def test_recommend_none_when_no_matching_category():
    agent = MagicMock(spec=BriefingAgent)
    # Only forecast rec, but "Cost Analysis" only cares about cost/optimization.
    agent.generate.return_value = [_rec(category="forecast", impact=1000)]
    recommender = ViewRecommender(agent)
    assert recommender.recommend("Cost Analysis", "FAC-1") is None


def test_recommend_handles_none_generate_result():
    agent = MagicMock(spec=BriefingAgent)
    agent.generate.return_value = None  # defensive: real impl returns []
    recommender = ViewRecommender(agent)
    assert recommender.recommend("Real-Time Consumption", "FAC-1") is None


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_second_call_is_cached(mock_briefing):
    recommender = ViewRecommender(mock_briefing)
    first = recommender.recommend("Cost Analysis", "FAC-1")
    second = recommender.recommend("Cost Analysis", "FAC-1")
    assert first is second
    assert mock_briefing.generate.call_count == 1


def test_cache_distinguishes_views_and_facilities(mock_briefing):
    recommender = ViewRecommender(mock_briefing)
    recommender.recommend("Cost Analysis", "FAC-1")
    recommender.recommend("Cost Analysis", "FAC-2")
    recommender.recommend("Real-Time Consumption", "FAC-1")
    assert mock_briefing.generate.call_count == 3


def test_force_refresh_bypasses_cache(mock_briefing):
    recommender = ViewRecommender(mock_briefing)
    recommender.recommend("Cost Analysis", "FAC-1")
    recommender.recommend("Cost Analysis", "FAC-1", force_refresh=True)
    assert mock_briefing.generate.call_count == 2


def test_clear_cache_resets_state(mock_briefing):
    recommender = ViewRecommender(mock_briefing)
    recommender.recommend("Cost Analysis", "FAC-1")
    recommender.clear_cache()
    recommender.recommend("Cost Analysis", "FAC-1")
    assert mock_briefing.generate.call_count == 2


def test_none_result_is_also_cached():
    agent = MagicMock(spec=BriefingAgent)
    agent.generate.return_value = []
    recommender = ViewRecommender(agent)
    assert recommender.recommend("Cost Analysis", "FAC-1") is None
    assert recommender.recommend("Cost Analysis", "FAC-1") is None
    assert agent.generate.call_count == 1


# ---------------------------------------------------------------------------
# _filter_by_category
# ---------------------------------------------------------------------------


def test_filter_by_category_keeps_only_matching():
    recommender = ViewRecommender(MagicMock(spec=BriefingAgent))
    recs = [
        _rec(category="anomaly"),
        _rec(category="cost"),
        _rec(category="optimization"),
        _rec(category="forecast"),
    ]
    kept = recommender._filter_by_category(recs, ["cost", "forecast"])
    assert {r.category for r in kept} == {"cost", "forecast"}
    assert len(kept) == 2


def test_filter_by_category_empty_input():
    recommender = ViewRecommender(MagicMock(spec=BriefingAgent))
    assert recommender._filter_by_category([], ["cost"]) == []


def test_filter_by_category_no_match():
    recommender = ViewRecommender(MagicMock(spec=BriefingAgent))
    recs = [_rec(category="anomaly")]
    assert recommender._filter_by_category(recs, ["cost"]) == []


# ---------------------------------------------------------------------------
# _format_business_value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category, impact, substring",
    [
        ("cost",         22_500, "/mo saved"),
        ("anomaly",     300_000, "compressor failure risk"),
        ("optimization", 15_000, "peak-shed opportunity"),
        ("forecast",     40_000, "Peak charge avoidance"),
        ("mystery",       5_000, "impact"),
    ],
)
def test_format_business_value_per_category(category, impact, substring):
    r = ViewRecommender(MagicMock(spec=BriefingAgent))
    out = r._format_business_value(impact, category)
    assert substring in out
    assert "Rs" in out


def test_format_inr_lakh_and_thousands():
    assert "L" in _format_inr(3_00_000)       # lakh formatting
    assert "," in _format_inr(22_500)         # thousands separator
    assert _format_inr(42).endswith("42")     # small values preserved


# ---------------------------------------------------------------------------
# _why_this_matters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "view, needle",
    [
        ("Real-Time Consumption",    "Live telemetry"),
        ("Demand Pattern Analysis",  "Demand patterns"),
        ("Cost Analysis",            "Tariff exposure"),
        ("AI Optimization",          "Optimization sweep"),
        ("Cross-Facility Benchmark", "Peer facilities"),
        ("Full Agent Sweep",         "Top-ranked"),
    ],
)
def test_why_this_matters_is_view_specific(view, needle):
    r = ViewRecommender(MagicMock(spec=BriefingAgent))
    out = r._why_this_matters(view, "cost", 12_000)
    assert needle in out


def test_why_this_matters_unknown_view_fallback():
    r = ViewRecommender(MagicMock(spec=BriefingAgent))
    out = r._why_this_matters("Something Else", "cost", 1_000)
    assert "Impact" in out and "cost" in out


# ---------------------------------------------------------------------------
# VIEW_TO_CATEGORY integrity — no typos, categories are valid
# ---------------------------------------------------------------------------


VALID_CATEGORIES = {"anomaly", "cost", "optimization", "forecast"}
EXPECTED_VIEWS = {
    "Real-Time Consumption",
    "Demand Pattern Analysis",
    "Cost Analysis",
    "AI Optimization",
    "Cross-Facility Benchmark",
    "Full Agent Sweep",
    "AI Chat Agent",
}


def test_view_to_category_has_all_expected_views():
    assert set(VIEW_TO_CATEGORY.keys()) == EXPECTED_VIEWS


@pytest.mark.parametrize("view", sorted(EXPECTED_VIEWS))
def test_view_to_category_values_are_valid(view):
    cats = VIEW_TO_CATEGORY[view]
    assert isinstance(cats, list)
    for c in cats:
        assert c in VALID_CATEGORIES, f"{view!r} has invalid category {c!r}"


def test_chat_view_has_no_categories():
    assert VIEW_TO_CATEGORY["AI Chat Agent"] == []


# ---------------------------------------------------------------------------
# ViewRecommendation dataclass round-trip
# ---------------------------------------------------------------------------


def test_view_recommendation_round_trip():
    v = ViewRecommendation(
        id="r-1",
        view="Cost Analysis",
        facility_id="FAC-9",
        title="Shift chiller schedule",
        rationale="peak tariff window overlaps chiller runtime",
        impact_inr_month=22_500.0,
        confidence=0.82,
        category="cost",
        agent_name="CostAgent",
        action_type="shift_schedule",
        business_value="Rs 22,500/mo saved",
        why_this_matters="Tariff exposure can be reduced.",
        one_click_payload={"device_id": "CHILLER-02"},
        counterfactual="without shift, Rs 22,500/mo lost",
    )
    assert v.id == "r-1"
    assert v.view == "Cost Analysis"
    assert v.facility_id == "FAC-9"
    assert v.title == "Shift chiller schedule"
    assert v.category == "cost"
    assert v.agent_name == "CostAgent"
    assert v.action_type == "shift_schedule"
    assert v.impact_inr_month == pytest.approx(22_500.0)
    assert v.confidence == pytest.approx(0.82)
    assert v.business_value.endswith("saved")
    assert "Tariff" in v.why_this_matters
    assert v.one_click_payload == {"device_id": "CHILLER-02"}
    assert v.counterfactual.startswith("without shift")


def test_view_recommendation_default_factories():
    v = ViewRecommendation(
        id="r-2",
        view="AI Optimization",
        facility_id="FAC-1",
        title="t",
        rationale="r",
        impact_inr_month=0.0,
        confidence=0.0,
        category="anomaly",
        agent_name="A",
        action_type="send_alert",
        business_value="bv",
        why_this_matters="w",
    )
    assert v.one_click_payload == {}
    assert v.counterfactual == ""


# ---------------------------------------------------------------------------
# Enrichment carries fields across
# ---------------------------------------------------------------------------


def test_enrichment_populates_all_fields(mock_briefing):
    recommender = ViewRecommender(mock_briefing)
    rec = recommender.recommend("Real-Time Consumption", "FAC-1")
    assert rec is not None
    # id came from the ActionRecommendation
    assert rec.id.startswith("rec-anomaly")
    assert rec.agent_name == "OptimizerAgent" or rec.agent_name  # non-empty
    assert rec.action_type  # non-empty
    assert rec.one_click_payload.get("device_id") == "HVAC-01"
    assert "without" in rec.counterfactual


def test_enrichment_handles_missing_payload():
    """A rec whose one_click_payload is None/missing should not crash."""
    agent = MagicMock(spec=BriefingAgent)
    rec = _rec(category="cost")
    rec.one_click_payload = None  # type: ignore[assignment]
    agent.generate.return_value = [rec]
    recommender = ViewRecommender(agent)
    out = recommender.recommend("Cost Analysis", "FAC-1")
    assert out is not None
    assert out.one_click_payload == {}


# ---------------------------------------------------------------------------
# Lazy agent loading
# ---------------------------------------------------------------------------


def test_lazy_agent_load_imports_briefing_agent():
    """When no agent is supplied, _get_agent lazy-imports BriefingAgent."""
    with patch("ml.agents.briefing_agent.BriefingAgent") as cls:
        cls.return_value = MagicMock(spec=BriefingAgent)
        cls.return_value.generate.return_value = []
        recommender = ViewRecommender()  # no agent passed
        recommender.recommend("Cost Analysis", "FAC-1")
        cls.assert_called_once()


def test_lazy_agent_cached_after_first_use():
    with patch("ml.agents.briefing_agent.BriefingAgent") as cls:
        inst = MagicMock(spec=BriefingAgent)
        inst.generate.return_value = []
        cls.return_value = inst
        recommender = ViewRecommender()
        recommender._get_agent()
        recommender._get_agent()
        cls.assert_called_once()  # built exactly once
