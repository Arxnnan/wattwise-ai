"""Tests for the multi-agent system."""
import json
import pytest
from unittest.mock import patch, MagicMock

from ml.agents.base import BaseAgent, AgentTool, AgentMessage, MAX_MEMORY
from ml.agents.tools import (
    query_facility_stats, query_all_facilities, query_peak_hours,
    run_anomaly_detection, run_cost_analysis, run_peak_optimization,
    run_optimization_opportunity, run_drift_check, get_all_tools,
)
from ml.agents.anomaly_agent import AnomalyAgent
from ml.agents.forecast_agent import ForecastAgent
from ml.agents.cost_agent import CostAgent
from ml.agents.optimizer_agent import OptimizerAgent
from ml.agents.orchestrator import EnergyOrchestrator
from ml.agents.chat_agent import ChatAgent


class TestBaseAgent:

    def test_init(self):
        agent = BaseAgent("test", "tester", "You are a test agent.")
        assert agent.name == "test"
        assert agent.role == "tester"
        assert agent.tools == {}
        assert agent.memory == []

    def test_register_tool(self):
        agent = BaseAgent("test", "tester", "prompt")
        tool = AgentTool(
            name="dummy", description="A test tool",
            parameters={"x": "int"}, func=lambda x: x * 2,
        )
        agent.register_tool(tool)
        assert "dummy" in agent.tools

    def test_execute_tool_success(self):
        agent = BaseAgent("test", "tester", "prompt")
        agent.register_tool(AgentTool(
            name="add", description="Add two numbers",
            parameters={"a": "int", "b": "int"},
            func=lambda a, b: a + b,
        ))
        result = agent._execute_tool("add", {"a": 3, "b": 4})
        assert result == "7"

    def test_execute_tool_unknown(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent._execute_tool("nonexistent", {})
        assert "Unknown tool" in result

    def test_execute_tool_error(self):
        agent = BaseAgent("test", "tester", "prompt")
        agent.register_tool(AgentTool(
            name="fail", description="Always fails",
            parameters={}, func=lambda: 1 / 0,
        ))
        result = agent._execute_tool("fail", {})
        assert "Tool error" in result

    def test_parse_tool_call(self):
        agent = BaseAgent("test", "tester", "prompt")
        response = 'Let me check. TOOL_CALL: query_stats({"facility_id": "office"})'
        result = agent._parse_tool_call(response)
        assert result is not None
        assert result[0] == "query_stats"
        assert result[1] == {"facility_id": "office"}

    def test_parse_tool_call_none(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent._parse_tool_call("Just a normal response.")
        assert result is None

    def test_parse_final_answer(self):
        agent = BaseAgent("test", "tester", "prompt")
        response = "FINAL_ANSWER: The office has 5 anomalies."
        result = agent._parse_final_answer(response)
        assert result == "The office has 5 anomalies."

    def test_parse_final_answer_none(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent._parse_final_answer("No final answer here.")
        assert result is None

    def test_run_without_llm(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent.run("test query")
        assert "LLM unavailable" in result or "rule-based" in result.lower() or len(result) > 0

    def test_type_coercion_int(self):
        agent = BaseAgent("test", "tester", "prompt")
        assert agent._coerce_arg("30", "int") == 30
        assert agent._coerce_arg(30, "int") == 30
        assert agent._coerce_arg("abc", "int") == "abc"

    def test_type_coercion_float(self):
        agent = BaseAgent("test", "tester", "prompt")
        assert agent._coerce_arg("150.0", "float") == 150.0
        assert agent._coerce_arg(150.0, "float") == 150.0
        assert agent._coerce_arg("abc", "float") == "abc"

    def test_execute_tool_coerces_string_to_int(self):
        agent = BaseAgent("test", "tester", "prompt")
        agent.register_tool(AgentTool(
            name="double", description="Double a number",
            parameters={"n": "int"}, func=lambda n: n * 2,
        ))
        result = agent._execute_tool("double", {"n": "5"})
        assert result == "10"

    def test_execute_tool_coerces_string_to_float(self):
        agent = BaseAgent("test", "tester", "prompt")
        agent.register_tool(AgentTool(
            name="half", description="Halve",
            parameters={"n": "float"}, func=lambda n: n / 2,
        ))
        result = agent._execute_tool("half", {"n": "10.0"})
        assert result == "5.0"

    def test_memory_is_trimmed(self):
        agent = BaseAgent("test", "tester", "prompt")
        for i in range(MAX_MEMORY + 10):
            agent.memory.append(AgentMessage(role="user", content=f"msg {i}"))
        agent.run("new query")
        assert len(agent.memory) <= MAX_MEMORY + 3  # run adds a few messages

    def test_tool_call_checked_before_final_answer(self):
        agent = BaseAgent("test", "tester", "prompt")
        response = "TOOL_CALL: func({\"x\": 1})\nFINAL_ANSWER: done"
        tool = agent._parse_tool_call(response)
        assert tool is not None
        assert tool[0] == "func"

    def test_parse_tool_call_multikey_json(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent._parse_tool_call(
            'TOOL_CALL: query_facility_stats({"facility_id": "office", "days": 30})'
        )
        assert result == ("query_facility_stats", {"facility_id": "office", "days": 30})

    def test_parse_tool_call_nested_json(self):
        agent = BaseAgent("test", "tester", "prompt")
        result = agent._parse_tool_call(
            'TOOL_CALL: func({"key": {"nested": "val"}})'
        )
        assert result == ("func", {"key": {"nested": "val"}})


class TestAgentTools:

    def test_query_facility_stats(self):
        result = query_facility_stats("office", days=7)
        assert "consumption" in result
        assert "demand" in result
        assert "cost" in result
        assert result["consumption"]["unit"] == "kWh"
        assert result["demand"]["unit"] == "kW"
        assert result["cost"]["unit"] == "INR"

    def test_query_all_facilities(self):
        result = query_all_facilities(days=7)
        assert "office" in result
        assert "warehouse" in result
        assert "datacentre" in result

    def test_query_peak_hours(self):
        result = query_peak_hours("office", days=7)
        assert "peak_hours" in result
        assert "peak_to_offpeak_ratio" in result
        assert len(result["peak_hours"]) <= 5

    def test_run_anomaly_detection(self):
        result = run_anomaly_detection("office", days=7)
        assert result["facility"] == "office"
        assert "anomalies_detected" in result
        assert "anomaly_rate" in result
        assert isinstance(result["top_anomalies"], list)

    def test_run_cost_analysis(self):
        result = run_cost_analysis("office", days=7)
        assert result["facility"] == "office"
        assert result["total_cost_inr"] > 0

    def test_run_peak_optimization(self):
        result = run_peak_optimization("office", threshold_kw=150.0)
        assert result["facility"] == "office"
        assert "peak_warning" in result
        assert isinstance(result["recommendations"], list)

    def test_run_optimization_opportunity(self):
        result = run_optimization_opportunity(days=14)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "facility" in result[0]
        assert "load_factor" in result[0]

    def test_get_all_tools_returns_complete_list(self):
        tools = get_all_tools()
        assert len(tools) >= 8
        names = {t.name for t in tools}
        assert "query_facility_stats" in names
        assert "run_anomaly_detection" in names
        assert "run_forecast" in names
        assert "run_cost_analysis" in names

    def test_run_drift_check_returns_dict_no_file_write(self, tmp_path, monkeypatch):
        import os
        import ml.agents.tools as tools_mod
        tools_mod._data_cache.clear()
        monkeypatch.chdir(tmp_path)
        result = run_drift_check(days=14)
        assert isinstance(result, dict)
        # Should not have written any JSON drift report to cwd
        assert not list(tmp_path.rglob("drift_reports/*.json"))

    def test_data_cache_reuses_same_dataframe(self):
        import ml.agents.tools as tools_mod
        tools_mod._data_cache.clear()
        df1 = tools_mod._get_data(7)
        df2 = tools_mod._get_data(7)
        assert df1 is df2  # same object = cache hit
        df3 = tools_mod._get_data(14)
        assert df3 is not df1  # different days = new entry


class TestSpecialistAgents:

    def test_anomaly_agent_init(self):
        agent = AnomalyAgent()
        assert agent.name == "AnomalyAgent"
        assert "run_anomaly_detection" in agent.tools

    def test_forecast_agent_init(self):
        agent = ForecastAgent()
        assert agent.name == "ForecastAgent"
        assert "run_forecast" in agent.tools

    def test_cost_agent_init(self):
        agent = CostAgent()
        assert agent.name == "CostAgent"
        assert "run_cost_analysis" in agent.tools

    def test_optimizer_agent_init(self):
        agent = OptimizerAgent()
        assert agent.name == "OptimizerAgent"
        assert "run_peak_optimization" in agent.tools


class TestOrchestrator:

    def test_init_creates_all_agents(self):
        orch = EnergyOrchestrator()
        assert orch.anomaly_agent is not None
        assert orch.forecast_agent is not None
        assert orch.cost_agent is not None
        assert orch.optimizer_agent is not None

    def test_route_anomaly_query(self):
        orch = EnergyOrchestrator()
        agents = orch._route_query("Are there any anomalies?")
        assert any(a.name == "AnomalyAgent" for a in agents)

    def test_route_forecast_query(self):
        orch = EnergyOrchestrator()
        agents = orch._route_query("What will demand be tomorrow?")
        assert any(a.name == "ForecastAgent" for a in agents)

    def test_route_cost_query(self):
        orch = EnergyOrchestrator()
        agents = orch._route_query("How much is the bill?")
        assert any(a.name == "CostAgent" for a in agents)

    def test_route_optimizer_query(self):
        orch = EnergyOrchestrator()
        agents = orch._route_query("How can we reduce peak load?")
        assert any(a.name == "OptimizerAgent" for a in agents)

    def test_route_generic_query_uses_all(self):
        orch = EnergyOrchestrator()
        agents = orch._route_query("Give me a status report")
        assert len(agents) == 4

    def test_report_history(self):
        orch = EnergyOrchestrator()
        history = orch.get_report_history()
        assert isinstance(history, list)


class TestChatAgent:

    def test_init(self):
        agent = ChatAgent()
        assert agent.name == "WattWise Assistant"
        assert len(agent.tools) >= 8
