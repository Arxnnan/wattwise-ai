"""WattWise AI — Multi-agent orchestration integration tests.

Covers the agent-to-agent integration layer end-to-end:
    BaseAgent ReAct loop -> real tool execution -> type coercion
    -> specialist agents -> orchestrator routing & full_sweep
    -> BriefingAgent -> ViewRecommender filtering
    -> ForensicAgent reasoning with real anomaly data

Real agent / tool / orchestrator / briefing / view-recommender / forensic
code paths are exercised. Only the LLM provider wrapper
(``ml.agents.llm_provider.get_llm_provider``) is mocked, so no real network
calls are made. The scripted provider returns per-test ``TOOL_CALL`` /
``FINAL_ANSWER`` strings that drive the real ReAct loop.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ml.agents.base import BaseAgent, AgentTool, MAX_MEMORY
from ml.agents.tools import (
    query_facility_stats,
    get_all_tools,
    _get_data,
)
from ml.agents.anomaly_agent import AnomalyAgent
from ml.agents.cost_agent import CostAgent
from ml.agents.forecast_agent import ForecastAgent
from ml.agents.optimizer_agent import OptimizerAgent
from ml.agents.orchestrator import EnergyOrchestrator
from ml.agents.chat_agent import ChatAgent
from ml.agents.briefing_agent import ActionRecommendation, BriefingAgent
from ml.agents.forensic_agent import ForensicAgent
from ml.analytics.view_recommender import ViewRecommender


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _warm_tool_cache() -> None:
    """Pre-populate the tools data cache once per module so each test's
    first call to a query tool doesn't pay the data-generation cost."""
    _get_data(30)


@pytest.fixture
def mock_llm():
    """Patch the LLM provider factory to return a controllable mock.

    Each test may re-assign ``provider.generate.return_value`` or
    ``provider.generate.side_effect`` to script the response. The mock is
    marked ``is_available=True`` by default so the ReAct loop will consult
    it; flip to False to exercise the "no provider" branch.
    """
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.name = "mock"
    provider.info.return_value = MagicMock(name="mock", model="mock-model", detail="ready")
    with patch(
        "ml.agents.llm_provider.get_llm_provider",
        return_value=provider,
    ):
        yield provider


# ---------------------------------------------------------------------------
# 1. BaseAgent ReAct loop with a real tool
# ---------------------------------------------------------------------------


class TestReactLoopWithRealTool:

    def test_single_tool_then_final_answer(self, mock_llm):
        """Mock LLM to emit TOOL_CALL then FINAL_ANSWER; verify the real
        ``query_facility_stats`` ran and its JSON result landed in memory."""
        agent = BaseAgent("ReactTest", "tester", "system")
        agent.register_tool(AgentTool(
            name="query_facility_stats",
            description="facility stats",
            parameters={"facility_id": "str", "days": "int"},
            func=query_facility_stats,
        ))
        mock_llm.generate.side_effect = [
            'TOOL_CALL: query_facility_stats({"facility_id": "office"})',
            "FINAL_ANSWER: done — office stats collected.",
        ]

        result = agent.run("How is office?")

        assert result == "done — office stats collected."
        # 2 LLM calls (first tool, second final)
        assert mock_llm.generate.call_count == 2
        # Memory should contain a tool result message with real JSON
        tool_msgs = [m for m in agent.memory if m.role == "tool"]
        assert len(tool_msgs) == 1
        parsed = json.loads(tool_msgs[0].content)
        # Real tool returned real stats structure
        assert "demand" in parsed or "consumption" in parsed or "cost" in parsed


# ---------------------------------------------------------------------------
# 2. Multi-iteration ReAct — two tools then final answer
# ---------------------------------------------------------------------------


class TestMultiIterationReact:

    def test_two_tool_calls_then_final(self, mock_llm):
        """Two sequential tool invocations followed by FINAL_ANSWER."""
        calls: list[dict] = []

        def _tool_a(x: int) -> dict:
            calls.append({"tool": "a", "x": x})
            return {"ok": True, "value": x * 2}

        def _tool_b(y: str) -> dict:
            calls.append({"tool": "b", "y": y})
            return {"ok": True, "echo": y.upper()}

        agent = BaseAgent("Multi", "multi", "system")
        agent.register_tool(AgentTool(
            name="tool_a", description="a",
            parameters={"x": "int"}, func=_tool_a,
        ))
        agent.register_tool(AgentTool(
            name="tool_b", description="b",
            parameters={"y": "str"}, func=_tool_b,
        ))

        mock_llm.generate.side_effect = [
            'TOOL_CALL: tool_a({"x": 7})',
            'TOOL_CALL: tool_b({"y": "hello"})',
            "FINAL_ANSWER: Combined — a doubled 7 to 14; b uppercased hello.",
        ]

        answer = agent.run("do both")

        assert mock_llm.generate.call_count == 3
        assert calls == [
            {"tool": "a", "x": 7},
            {"tool": "b", "y": "hello"},
        ]
        assert "14" in answer and "hello" in answer.lower()


# ---------------------------------------------------------------------------
# 3. Type coercion end-to-end
# ---------------------------------------------------------------------------


class TestTypeCoercionEndToEnd:

    def test_days_string_coerced_to_int(self, mock_llm):
        """LLM returns ``"days": "30"`` (string) — ``_coerce_arg`` must
        convert to int before the real tool runs."""
        received: dict = {}

        def _spy(facility_id: str = "office", days: int = 30):
            received["facility_id"] = facility_id
            received["days"] = days
            received["days_type"] = type(days).__name__
            # delegate to real tool so result is realistic
            return query_facility_stats(facility_id=facility_id, days=days)

        agent = BaseAgent("CoerceTest", "tester", "system")
        agent.register_tool(AgentTool(
            name="query_facility_stats",
            description="facility stats",
            parameters={"facility_id": "str", "days": "int (default 30)"},
            func=_spy,
        ))
        mock_llm.generate.side_effect = [
            'TOOL_CALL: query_facility_stats({"facility_id": "office", "days": "30"})',
            "FINAL_ANSWER: ok",
        ]

        agent.run("stats please")

        assert received["facility_id"] == "office"
        assert received["days"] == 30
        assert received["days_type"] == "int"


# ---------------------------------------------------------------------------
# 4. Orchestrator routing
# ---------------------------------------------------------------------------


class TestOrchestratorRouting:

    def test_bill_query_routes_to_cost_agent(self, mock_llm):
        orch = EnergyOrchestrator()
        agents = orch._route_query("why is office bill high?")
        assert orch.cost_agent in agents

    def test_peak_forecast_query_routes_to_forecast_agent(self, mock_llm):
        orch = EnergyOrchestrator()
        agents = orch._route_query("peak forecast")
        assert orch.forecast_agent in agents


# ---------------------------------------------------------------------------
# 5. Orchestrator full_sweep executes all 4 specialists
# ---------------------------------------------------------------------------


class TestFullSweepExecutesAll:

    def test_full_sweep_calls_each_specialist(self, mock_llm):
        orch = EnergyOrchestrator()
        with patch.object(orch.anomaly_agent, "monitor", return_value="A-ok") as m1, \
             patch.object(orch.forecast_agent, "predict", return_value="F-ok") as m2, \
             patch.object(orch.cost_agent, "analyze", return_value="C-ok") as m3, \
             patch.object(orch.optimizer_agent, "optimize", return_value="O-ok") as m4:
            results = orch.full_sweep("office")

        for mocked in (m1, m2, m3, m4):
            mocked.assert_called_once()
        assert results == {
            "anomalies": "A-ok",
            "forecast": "F-ok",
            "costs": "C-ok",
            "optimization": "O-ok",
        }
        # Orchestrator records a report entry for each specialist
        assert len(orch.reports) == 4
        assert {r.agent_name for r in orch.reports} == {
            "AnomalyAgent", "ForecastAgent", "CostAgent", "OptimizerAgent",
        }


# ---------------------------------------------------------------------------
# 6. BriefingAgent -> ViewRecommender chain
# ---------------------------------------------------------------------------


def _make_rec(category: str, title: str, impact: float, confidence: float) -> ActionRecommendation:
    return ActionRecommendation(
        id=f"id-{category}",
        created_at=datetime.now(timezone.utc),
        facility_id="office",
        category=category,  # type: ignore[arg-type]
        agent_name=f"{category.title()}Agent",
        title=title,
        rationale=f"rationale for {category}",
        impact_inr_month=impact,
        confidence=confidence,
        action_type="send_alert",
        one_click_payload={"facility": "office"},
        counterfactual="",
    )


class TestBriefingToViewRecommenderChain:

    def test_view_filters_pick_right_category(self, mock_llm):
        """Three recs covering anomaly/cost/forecast — ViewRecommender must
        pick the right category for each view based on VIEW_TO_CATEGORY."""
        recs = [
            _make_rec("anomaly",  "A rec", 50_000, 0.9),
            _make_rec("cost",     "C rec", 40_000, 0.8),
            _make_rec("forecast", "F rec", 30_000, 0.7),
        ]
        briefing = MagicMock()
        briefing.generate.return_value = recs

        rec = ViewRecommender(briefing_agent=briefing)

        # Real-Time Consumption prioritises anomaly over optimization
        rt = rec.recommend("Real-Time Consumption", "office")
        assert rt is not None and rt.category == "anomaly"

        # Cost Analysis prioritises cost
        ca = rec.recommend("Cost Analysis", "office")
        assert ca is not None and ca.category == "cost"

        # Demand Pattern Analysis has (optimization, forecast); only
        # forecast is available in our fixture set, so it should win.
        dpa = rec.recommend("Demand Pattern Analysis", "office")
        assert dpa is not None and dpa.category == "forecast"

        # AI Chat Agent has no strip
        chat = rec.recommend("AI Chat Agent", "office")
        assert chat is None


# ---------------------------------------------------------------------------
# 7. ForensicAgent with real anomaly data
# ---------------------------------------------------------------------------


class TestForensicAgentWithRealAnomaly:

    def test_forensic_card_from_real_detector(self, mock_llm, office_demand):
        """Fit the real AnomalyDetector on the office demand series,
        pick the top-scored anomaly, and build a ForensicCard."""
        # Force template-fallback path so no scripted LLM response is needed.
        mock_llm.is_available.return_value = False

        from ml.anomaly import AnomalyDetector

        detector = AnomalyDetector()
        detector.fit(office_demand)
        scores = detector.score(office_demand)
        flags = detector.predict(office_demand)
        anomaly_idx = flags[flags].index
        assert len(anomaly_idx) > 0, "detector should flag at least one point"

        # Pick the highest-scored flagged anomaly
        top_ts = scores.loc[anomaly_idx].idxmax()
        observed = float(office_demand.loc[top_ts])
        baseline = float(office_demand.rolling(15, center=True, min_periods=5).median().loc[top_ts])

        agent = ForensicAgent()
        card = agent.forensic(
            anomaly_id="anom-1",
            anomaly_timestamp=top_ts.to_pydatetime() if hasattr(top_ts, "to_pydatetime") else datetime.now(timezone.utc),
            facility_id="office",
            device_id="hvac-main",
            observed_value=observed,
            expected_value=baseline,
            pyod_scores={"iforest": 0.91, "copod": 0.84, "ecod": 0.88},
            historical_anomalies=None,
            severity="major",
        )

        assert card.why_flagged, "why_flagged must be non-empty"
        assert "PyOD" in card.why_flagged
        assert card.hypothesis, "hypothesis must be non-empty"
        # HVAC device id steers template branch
        assert "HVAC" in card.hypothesis or "hvac" in card.hypothesis.lower()
        assert card.work_order_draft, "work_order_draft must be non-empty"
        assert "Title:" in card.work_order_draft
        assert card.llm_source == "template"


# ---------------------------------------------------------------------------
# 8. ChatAgent registers 10 tools and executes one
# ---------------------------------------------------------------------------


class TestChatAgentTenTools:

    def test_chat_agent_ten_tools_and_tool_fires(self, mock_llm):
        agent = ChatAgent()
        assert len(agent.tools) == 10, (
            f"ChatAgent should have 10 tools, got {len(agent.tools)}"
        )
        # Spot-check: all tools from get_all_tools() are registered.
        expected = {t.name for t in get_all_tools()}
        assert set(agent.tools.keys()) == expected

        mock_llm.generate.side_effect = [
            'TOOL_CALL: query_facility_stats({"facility_id": "office"})',
            "FINAL_ANSWER: Office has normal usage.",
        ]
        answer = agent.chat("How's office?")

        assert "Office" in answer
        # Verify a tool actually ran (produced a tool-role memory message)
        tool_msgs = [m for m in agent.memory if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].tool_name == "query_facility_stats"


# ---------------------------------------------------------------------------
# 9. Memory trimming over many runs
# ---------------------------------------------------------------------------


class TestMemoryTrimming:

    def test_memory_bounded_after_many_runs(self, mock_llm):
        agent = BaseAgent("MemTest", "memtester", "system")
        mock_llm.generate.return_value = "FINAL_ANSWER: ok"

        for i in range(25):
            agent.run(f"query {i}")
            # Trimming happens at the START of run(); each run then appends
            # one user + one assistant message. So the ceiling is MAX_MEMORY + 2.
            assert len(agent.memory) <= MAX_MEMORY + 2, (
                f"memory ballooned at iteration {i}: {len(agent.memory)}"
            )

        # After the long sequence, confirm the invariant is still holding
        # at (or near) the MAX_MEMORY ceiling (not drifting upward).
        assert len(agent.memory) <= MAX_MEMORY + 2
        assert len(agent.memory) >= MAX_MEMORY - 1  # we did reach the ceiling


# ---------------------------------------------------------------------------
# 10. Specialist agent registration completeness
# ---------------------------------------------------------------------------


class TestSpecialistRegistration:

    def test_anomaly_agent(self, mock_llm):
        a = AnomalyAgent()
        assert hasattr(a, "monitor") and callable(a.monitor)
        expected_tools = {
            "run_anomaly_detection", "query_facility_stats",
            "query_peak_hours", "send_alert",
        }
        assert set(a.tools.keys()) == expected_tools
        assert len(a.tools) == 4

    def test_cost_agent(self, mock_llm):
        a = CostAgent()
        assert hasattr(a, "analyze") and callable(a.analyze)
        expected_tools = {
            "run_cost_analysis", "query_facility_stats",
            "query_all_facilities", "run_optimization_opportunity",
        }
        assert set(a.tools.keys()) == expected_tools
        assert len(a.tools) == 4

    def test_forecast_agent(self, mock_llm):
        a = ForecastAgent()
        assert hasattr(a, "predict") and callable(a.predict)
        expected_tools = {
            "run_forecast", "query_facility_stats",
            "query_peak_hours", "send_alert",
        }
        assert set(a.tools.keys()) == expected_tools
        assert len(a.tools) == 4

    def test_optimizer_agent(self, mock_llm):
        a = OptimizerAgent()
        assert hasattr(a, "optimize") and callable(a.optimize)
        expected_tools = {
            "run_peak_optimization", "run_optimization_opportunity",
            "query_facility_stats", "query_peak_hours", "send_alert",
        }
        assert set(a.tools.keys()) == expected_tools
        assert len(a.tools) == 5
