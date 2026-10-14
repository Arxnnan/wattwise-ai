"""Unit tests for the Morning Briefing agent.

Specialists are always mocked — no real LLM traffic, no network. Each test
is written to complete well under 2 seconds.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from ml.agents.briefing_agent import (
    ActionRecommendation,
    BriefingAgent,
    _as_confidence,
    _as_float,
    _build_recommendation,
    _parse_blocks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _text(device: str, impact: float, confidence: float = 0.8,
          title: str = "Do a thing", counterfactual: str = "") -> str:
    extra = f"counterfactual: {counterfactual}\n" if counterfactual else ""
    return (
        "RECOMMENDATION\n"
        f"device: {device}\n"
        f"title: {title}\n"
        f"impact: {impact}\n"
        f"confidence: {confidence}\n"
        f"rationale: because we said so\n"
        f"{extra}"
    )


@pytest.fixture
def mock_specialists():
    """Legacy-shape dict kept so TestSpecialistLoading can inject it.

    The `.monitor/.analyze/.optimize/.predict` returns are no longer consumed
    by `_X_candidates` — those methods now call `ml.agents.tools.*` directly —
    but keeping the shape avoids churning the lazy-loading tests.
    """
    anomaly = MagicMock()
    cost = MagicMock()
    optimizer = MagicMock()
    forecast = MagicMock()
    anomaly.monitor.return_value = _text("HVAC-01", 10000, 0.9, "Anomaly on HVAC-01")
    cost.analyze.return_value = _text("COST-02", 20000, 0.5, "Shift cost load")
    optimizer.optimize.return_value = _text("OPT-03", 15000, 0.6, "Shed peak load")
    forecast.predict.return_value = _text("FCST-04", 5000, 0.7, "Forecast warn")
    return {
        "anomaly": anomaly, "cost": cost,
        "optimizer": optimizer, "forecast": forecast,
    }


# Default tool-call payloads chosen so each specialist produces exactly one
# recommendation that passes its emit threshold. Impact numbers are tuned so
# the ranking order (impact*confidence desc) is: Cost > Optimizer > Anomaly > Forecast.
_ANOMALY_TOOL_OUT = {
    "anomalies_detected": 5,
    "anomaly_rate": 2.1,
    "top_anomalies": [
        {"value_kw": 95.0, "score": 0.95, "timestamp": "2026-10-10T13:00:00+00:00"},
    ],
}
_COST_TOOL_OUT = {"total_cost_inr": 85000}
_PEAK_HOURS_OUT = {"peak_to_offpeak_ratio": 2.3, "peak_avg": 110, "off_peak_avg": 48}
_FACILITY_STATS_OUT = {"demand": {"mean": 20.0}}
_PEAK_OPT_OUT = {
    "peak_warning": True,
    "current_demand_kw": 170.0,
    "total_saveable_kw": 25.0,
    "recommendations": [
        {"load": "HVAC-A"}, {"load": "HVAC-B"}, {"load": "EV-charger"},
    ],
}
_FORECAST_OUT = {
    "peak_predicted_kw": 160.0,
    "avg_predicted_kw": 95.0,
    "model_used": "Chronos",
}


@pytest.fixture
def mock_tools():
    """Patch the tool functions each `_X_candidates` method calls.

    Also force `_llm_narrative` to None so the template branch fires without
    spending time initialising an LLM provider — keeps each test well under 1s.
    """
    with patch("ml.agents.tools.run_anomaly_detection", return_value=_ANOMALY_TOOL_OUT) as anom, \
         patch("ml.agents.tools.run_cost_analysis", return_value=_COST_TOOL_OUT) as cost, \
         patch("ml.agents.tools.query_peak_hours", return_value=_PEAK_HOURS_OUT) as peak_h, \
         patch("ml.agents.tools.query_facility_stats", return_value=_FACILITY_STATS_OUT) as fstats, \
         patch("ml.agents.tools.run_peak_optimization", return_value=_PEAK_OPT_OUT) as popt, \
         patch("ml.agents.tools.run_forecast", return_value=_FORECAST_OUT) as fcst, \
         patch("ml.agents.briefing_agent.BriefingAgent._llm_narrative", return_value=None):
        yield {
            "anomaly": anom, "cost": cost, "peak_hours": peak_h,
            "facility_stats": fstats, "optimizer": popt, "forecast": fcst,
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


class TestParsingHelpers:

    def test_as_float_defaults_on_none(self):
        assert _as_float(None, 7.0) == 7.0

    def test_as_float_strips_currency(self):
        assert _as_float("₹1,234", 0.0) == 1234.0

    def test_as_float_empty_after_cleanup(self):
        assert _as_float("abc", 2.5) == 2.5

    def test_as_float_value_error(self):
        # "." survives the regex but float(".") raises → default is returned.
        assert _as_float(".", 9.0) == 9.0

    def test_as_confidence_default_on_none(self):
        assert _as_confidence(None) == 0.5

    def test_as_confidence_rescales_pct(self):
        assert _as_confidence("95") == 0.95

    def test_as_confidence_clamps_high(self):
        # 150 / 100 = 1.5 → clamped to 1.0
        assert _as_confidence("150") == 1.0

    def test_as_confidence_clamps_low(self):
        assert _as_confidence("-0.3") == 0.0

    def test_parse_blocks_empty_returns_empty(self):
        assert _parse_blocks("") == []
        assert _parse_blocks("   \n ") == []

    def test_parse_blocks_single_block_no_marker(self):
        blocks = _parse_blocks("device: X\nimpact: 10\n")
        assert blocks == [{"device": "X", "impact": "10"}]

    def test_parse_blocks_multiple_markers(self):
        txt = (
            "preamble lines ignored\n"
            "RECOMMENDATION\n"
            "device: A\nimpact: 10\n"
            "RECOMMENDATION:\n"
            "device: B\nimpact: 20\n"
        )
        blocks = _parse_blocks(txt)
        assert len(blocks) == 2
        assert blocks[0]["device"] == "A"
        assert blocks[1]["device"] == "B"

    def test_parse_blocks_no_kv_in_block_skipped(self):
        # Marker present but body has no kv pairs → nothing extracted.
        assert _parse_blocks("RECOMMENDATION\n(no data)\n") == []

    def test_build_recommendation_with_device_and_window(self):
        block = {
            "device": "HVAC-7", "window": "10-12",
            "title": "Shed", "impact": "1000", "confidence": "0.5",
            "rationale": "r", "counterfactual": "cf",
        }
        rec = _build_recommendation(
            block=block, facility_id="plant", category="anomaly",
            agent_name="AnomalyAgent", default_title="x", default_action="send_alert",
        )
        assert rec.one_click_payload == {"device_id": "HVAC-7", "window": "10-12"}
        assert rec.counterfactual == "cf"
        assert rec.title == "Shed"

    def test_build_recommendation_without_device_uses_defaults(self):
        rec = _build_recommendation(
            block={}, facility_id="plant", category="cost",
            agent_name="CostAgent", default_title="fallback", default_action="shed_load",
        )
        assert rec.one_click_payload == {}
        assert rec.title == "fallback"
        assert rec.action_type == "shed_load"
        assert rec.confidence == 0.5


# ---------------------------------------------------------------------------
# BriefingAgent.generate — happy path and ranking
# ---------------------------------------------------------------------------


class TestGenerate:

    def test_all_specialists_return_sorted_top3(self, mock_tools):
        agent = BriefingAgent(specialists={})
        recs = agent.generate("plant", top_n=3)
        assert len(recs) == 3
        # With the default tool payloads above, the computed scores are:
        #   Cost       85_800 * 0.78  ≈ 66_924
        #   Optimizer   3_750 * 0.85  ≈  3_187
        #   Forecast    1_500 * 0.82  ≈  1_230
        #   Anomaly     5_000 * 0.88  ≈  4_400
        # So Cost should rank first.
        assert recs[0].agent_name == "CostAgent"
        for r in recs:
            assert r.facility_id == "plant"
            assert r.category in {"cost", "anomaly", "optimization", "forecast"}

    def test_top_n_one(self, mock_tools):
        agent = BriefingAgent(specialists={})
        recs = agent.generate("plant", top_n=1)
        assert len(recs) == 1

    def test_top_n_larger_than_available(self, mock_tools):
        agent = BriefingAgent(specialists={})
        recs = agent.generate("plant", top_n=10)
        # Four specialists → at most 4 recommendations.
        assert len(recs) == 4

    def test_counterfactual_populated_when_provided(self, mock_tools):
        agent = BriefingAgent(specialists={})
        recs = agent.generate("plant", top_n=4)
        # Every candidate path sets a non-empty counterfactual string.
        assert all(r.counterfactual for r in recs)

    def test_ids_are_unique_across_calls(self, mock_tools):
        agent = BriefingAgent(specialists={})
        ids = set()
        for _ in range(3):
            for r in agent.generate("plant", top_n=4):
                ids.add(r.id)
        # 3 calls × 4 recs each = 12 unique UUIDs expected.
        assert len(ids) == 12


# ---------------------------------------------------------------------------
# BriefingAgent.generate — failure modes
# ---------------------------------------------------------------------------


class TestGenerateFailureModes:

    def test_specialist_timeout_other_three_still_returned(self, mock_tools):
        def slow(*_a, **_kw):
            time.sleep(1.5)
            return _FORECAST_OUT

        mock_tools["forecast"].side_effect = slow
        agent = BriefingAgent(specialists={})
        start = time.time()
        recs = agent.generate("plant", top_n=10, timeout_sec=1)
        elapsed = time.time() - start
        # The slow forecast specialist is dropped; the other 3 remain.
        assert len(recs) == 3
        agent_names = {r.agent_name for r in recs}
        assert "ForecastAgent" not in agent_names
        # Timeout honored — should finish close to timeout, not after the 1.5s sleep.
        assert elapsed < 1.4

    def test_all_specialists_fail_returns_empty(self, mock_tools, caplog):
        # Blow up every tool call → every _X_candidates branch swallows & returns [].
        for key in ("anomaly", "cost", "peak_hours", "facility_stats", "optimizer", "forecast"):
            mock_tools[key].side_effect = RuntimeError("boom")
        agent = BriefingAgent(specialists={})
        with caplog.at_level("WARNING"):
            recs = agent.generate("plant")
        assert recs == []
        assert any("no recommendations" in rec.message for rec in caplog.records)

    @pytest.mark.parametrize("tool_key,candidate_fn", [
        ("anomaly", "_anomaly_candidates"),
        ("cost", "_cost_candidates"),
        ("optimizer", "_optimizer_candidates"),
        ("forecast", "_forecast_candidates"),
    ])
    def test_each_candidate_wrapper_swallows_exception(
        self, mock_tools, tool_key, candidate_fn,
    ):
        mock_tools[tool_key].side_effect = RuntimeError("fail")
        agent = BriefingAgent(specialists={})
        # Should return [] rather than raise.
        assert getattr(agent, candidate_fn)("plant") == []


# ---------------------------------------------------------------------------
# Dedupe + rank
# ---------------------------------------------------------------------------


def _rec(impact, device=None, confidence=1.0, category="cost"):
    return ActionRecommendation(
        id="id-" + str(impact) + "-" + str(device),
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        facility_id="plant", category=category,
        agent_name="X", title="t", rationale="r",
        impact_inr_month=impact, confidence=confidence,
        action_type="send_alert",
        one_click_payload={"device_id": device} if device else {},
    )


class TestDedupeAndRank:

    def test_dedupe_keeps_highest_impact(self):
        agent = BriefingAgent(specialists={})
        a_small = _rec(100, device="HVAC-1")
        a_big = _rec(500, device="HVAC-1")
        b_only = _rec(300, device="HVAC-2")
        out = agent._dedupe_by_device([a_small, a_big, b_only])
        impacts_by_device = {r.one_click_payload["device_id"]: r.impact_inr_month for r in out}
        assert impacts_by_device == {"HVAC-1": 500, "HVAC-2": 300}

    def test_dedupe_passthrough_without_device(self):
        agent = BriefingAgent(specialists={})
        a = _rec(100)  # no device
        b = _rec(200)  # no device
        c = _rec(500, device="HVAC-1")
        out = agent._dedupe_by_device([a, b, c])
        # Two no-device recs pass through unchanged, plus the device winner.
        assert len(out) == 3

    def test_rank_descending_and_stable(self):
        agent = BriefingAgent(specialists={})
        # Equal scores (impact*confidence) → should preserve insertion order (stable).
        tied_1 = _rec(100, device="A", confidence=1.0)
        tied_2 = _rec(50, device="B", confidence=2.0)  # same score 100
        tied_3 = _rec(1000, device="C", confidence=1.0)
        ranked = agent._rank([tied_1, tied_2, tied_3])
        assert ranked[0] is tied_3  # 1000 > 100
        assert ranked[1] is tied_1
        assert ranked[2] is tied_2


# ---------------------------------------------------------------------------
# Lazy specialist loading / injection
# ---------------------------------------------------------------------------


class TestSpecialistLoading:

    def test_custom_specialists_injected(self, mock_specialists):
        agent = BriefingAgent(specialists=mock_specialists)
        assert agent._get_specialists() is mock_specialists

    def test_lazy_load_only_on_generate(self):
        # Instantiating with specialists=None must NOT import the real agents
        # or construct them; the lazy load happens inside _get_specialists.
        agent = BriefingAgent(specialists=None)
        assert agent._specialists is None

    def test_lazy_load_populates_dict(self):
        # Patch the four agent classes so no LLM is initialized.
        with patch("ml.agents.anomaly_agent.AnomalyAgent") as mA, \
             patch("ml.agents.cost_agent.CostAgent") as mC, \
             patch("ml.agents.optimizer_agent.OptimizerAgent") as mO, \
             patch("ml.agents.forecast_agent.ForecastAgent") as mF:
            mA.return_value = MagicMock()
            mC.return_value = MagicMock()
            mO.return_value = MagicMock()
            mF.return_value = MagicMock()
            agent = BriefingAgent(specialists=None)
            spec = agent._get_specialists()
            assert set(spec.keys()) == {"anomaly", "cost", "optimizer", "forecast"}
            # Idempotent — second call does not re-import.
            assert agent._get_specialists() is spec

    def test_generate_uses_lazy_loaded_specialists(self):
        with patch("ml.agents.anomaly_agent.AnomalyAgent") as mA, \
             patch("ml.agents.cost_agent.CostAgent") as mC, \
             patch("ml.agents.optimizer_agent.OptimizerAgent") as mO, \
             patch("ml.agents.forecast_agent.ForecastAgent") as mF:
            mA.return_value = MagicMock(
                monitor=MagicMock(return_value=_text("D1", 1000)))
            mC.return_value = MagicMock(
                analyze=MagicMock(return_value=_text("D2", 2000)))
            mO.return_value = MagicMock(
                optimize=MagicMock(return_value=_text("D3", 3000)))
            mF.return_value = MagicMock(
                predict=MagicMock(return_value=_text("D4", 500)))
            agent = BriefingAgent(specialists=None)
            recs = agent.generate("plant", top_n=2)
            assert len(recs) == 2
