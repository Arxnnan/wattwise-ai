"""Extra tests pushing ml.agents.* to 100% coverage.

All external I/O (HTTP, LLMs, cross-module calls) is mocked.
"""
from __future__ import annotations

import sys
import types
import logging
import pytest
from unittest.mock import patch, MagicMock

from ml.agents.base import (
    BaseAgent, AgentTool, AgentMessage, MAX_ITERATIONS, MAX_MEMORY,
)
from ml.agents import tools as tools_mod
from ml.agents.tools import (
    query_recent_readings, run_forecast, run_drift_check, send_alert,
    get_all_tools,
)
from ml.agents.anomaly_agent import AnomalyAgent
from ml.agents.forecast_agent import ForecastAgent
from ml.agents.cost_agent import CostAgent
from ml.agents.optimizer_agent import OptimizerAgent
from ml.agents.chat_agent import ChatAgent
from ml.agents.orchestrator import EnergyOrchestrator, AgentReport
from ml.agents import llm_provider as lp
from ml.agents.llm_provider import (
    GeminiProvider, GroqProvider, OllamaProvider, OpenAIProvider,
    AnthropicProvider, HuggingFaceProvider, NullProvider,
    get_llm_provider, LLMProvider, ProviderInfo,
)


# ─────────────────────── base.py coverage ───────────────────────

class _StubProvider(LLMProvider):
    """A fake provider we can hand the BaseAgent for exercising LLM paths."""
    name = "stub"
    default_model = "stub-1"

    def __init__(self, responses=None, raise_exc=False):
        self._responses = list(responses or [])
        self._raise = raise_exc
        self.model = self.default_model
        self._detail = "ready"

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str) -> str:
        if self._raise:
            raise RuntimeError("boom")
        if self._responses:
            return self._responses.pop(0)
        return "FINAL_ANSWER: default"


def _make_agent_with_stub(responses=None, raise_exc=False):
    """Build a BaseAgent then swap in a stub provider — avoids real network."""
    with patch("ml.agents.llm_provider.get_llm_provider", return_value=NullProvider()):
        agent = BaseAgent("t", "tester", "sys prompt")
    stub = _StubProvider(responses=responses, raise_exc=raise_exc)
    agent._provider = stub
    agent._llm_available = True
    return agent, stub


class TestBaseAgentLLMPaths:

    def test_init_logs_info_when_llm_available(self, caplog):
        """Lines 64-65 — the branch when the provider IS available."""
        stub = _StubProvider()
        with patch("ml.agents.llm_provider.get_llm_provider", return_value=stub):
            with caplog.at_level(logging.INFO, logger="ml.agents.base"):
                a = BaseAgent("A", "r", "p")
        assert a._llm_available is True
        assert any("LLM provider: stub" in rec.message for rec in caplog.records)

    def test_build_tool_descriptions_with_tools(self):
        """Lines 75-79 — produces a line per registered tool."""
        agent, _ = _make_agent_with_stub()
        agent.register_tool(AgentTool(
            name="foo", description="does foo",
            parameters={"x": "int", "y": "str"}, func=lambda x, y: None,
        ))
        out = agent._build_tool_descriptions()
        assert "foo" in out and "x: int" in out and "y: str" in out

    def test_build_prompt_formats_tool_history(self):
        """Line 86 — the branch that prints '[Tool Result: ...]'."""
        agent, _ = _make_agent_with_stub()
        agent.memory.append(AgentMessage(
            role="tool", content="42", tool_name="calc",
        ))
        prompt = agent._build_prompt("hi")
        assert "[Tool Result: calc]" in prompt
        assert "42" in prompt

    def test_parse_tool_call_bad_json_returns_empty_args(self):
        """Lines 119-120 — JSONDecodeError branch keeps the name, empties args."""
        agent, _ = _make_agent_with_stub()
        res = agent._parse_tool_call('TOOL_CALL: foo({not json})')
        assert res == ("foo", {})

    def test_call_llm_success_returns_stripped(self):
        """Lines 132-133 — happy path through the provider."""
        agent, _ = _make_agent_with_stub(responses=["  hello  "])
        assert agent._call_llm("prompt") == "hello"

    def test_call_llm_exception_returns_final_answer_error(self):
        """Lines 134-136 — provider raises → formatted FINAL_ANSWER error."""
        agent, _ = _make_agent_with_stub(raise_exc=True)
        out = agent._call_llm("prompt")
        assert "FINAL_ANSWER" in out and "stub" in out and "boom" in out

    def test_execute_tool_jsonifies_dict_result(self):
        """Line 165 — isinstance(result, (dict, list)) branch."""
        agent, _ = _make_agent_with_stub()
        agent.register_tool(AgentTool(
            name="dicttool", description="returns dict",
            parameters={}, func=lambda: {"a": 1, "b": 2},
        ))
        out = agent._execute_tool("dicttool", {})
        assert '"a"' in out and '"b"' in out  # JSON-formatted

    def test_run_tool_call_then_final_answer(self):
        """Lines 186-195 — tool invocation path + continue, then final answer."""
        agent, _ = _make_agent_with_stub(responses=[
            'TOOL_CALL: calc({"x": 2})',
            "FINAL_ANSWER: result is 4",
        ])
        agent.register_tool(AgentTool(
            name="calc", description="double",
            parameters={"x": "int"}, func=lambda x: x * 2,
        ))
        out = agent.run("double 2")
        assert "result is 4" in out
        # Memory should contain the tool message
        assert any(m.role == "tool" and m.tool_name == "calc" for m in agent.memory)

    def test_run_returns_raw_response_when_no_tool_no_final(self):
        """Line 202 — neither tool call nor final answer → return raw response."""
        agent, _ = _make_agent_with_stub(responses=["just chatting"])
        out = agent.run("hi")
        assert out == "just chatting"

    def test_run_hits_max_iterations_when_only_tool_calls(self):
        """Line 204 — exhausts MAX_ITERATIONS because every response is a tool call."""
        # 8+ tool-call responses so we never hit a final answer
        responses = ['TOOL_CALL: inc({"x": 1})'] * (MAX_ITERATIONS + 1)
        agent, _ = _make_agent_with_stub(responses=responses)
        agent.register_tool(AgentTool(
            name="inc", description="inc",
            parameters={"x": "int"}, func=lambda x: x + 1,
        ))
        out = agent.run("loop")
        assert "maximum iterations" in out

    def test_run_without_llm_default(self):
        """Line 208 — the base fallback message."""
        agent, _ = _make_agent_with_stub()
        assert "No rule-based" in agent.run_without_llm("q")


# ─────────────────── llm_provider.py coverage ──────────────────

class TestGeminiInit:

    def test_gemini_with_key_initializes_client(self, monkeypatch):
        """Lines 70-77 — successful genai init path."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        fake_mod = types.ModuleType("google.generativeai")
        fake_mod.configure = MagicMock()
        fake_mod.GenerativeModel = MagicMock(return_value=MagicMock(name="model"))
        fake_pkg = types.ModuleType("google")
        fake_pkg.generativeai = fake_mod
        with patch.dict(sys.modules, {
            "google": fake_pkg, "google.generativeai": fake_mod,
        }):
            p = GeminiProvider()
        assert p.is_available() is True
        assert "ready" in p.info().detail
        fake_mod.configure.assert_called_once_with(api_key="fake")

    def test_gemini_with_key_init_failure_marks_unavailable(self, monkeypatch):
        """Lines 76-77 — the exception branch when genai import or configure fails."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        # Simulate ImportError by patching __import__ to blow up on google.generativeai
        real_import = __import__

        def bad_import(name, *a, **kw):
            if name == "google.generativeai":
                raise ImportError("no genai")
            return real_import(name, *a, **kw)

        with patch("builtins.__import__", side_effect=bad_import):
            p = GeminiProvider()
        assert p.is_available() is False
        assert "init failed" in p.info().detail

    def test_gemini_generate_calls_client(self, monkeypatch):
        """Lines 83-84 — generate() goes through the client."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        fake_mod = types.ModuleType("google.generativeai")
        fake_mod.configure = MagicMock()
        model = MagicMock()
        model.generate_content.return_value = MagicMock(text="gemini-says-hi")
        fake_mod.GenerativeModel = MagicMock(return_value=model)
        fake_pkg = types.ModuleType("google")
        fake_pkg.generativeai = fake_mod
        with patch.dict(sys.modules, {
            "google": fake_pkg, "google.generativeai": fake_mod,
        }):
            p = GeminiProvider()
            out = p.generate("hi")
        assert out == "gemini-says-hi"


class TestOllamaBranches:

    def test_ollama_model_not_pulled_marks_unavailable(self):
        """Lines 141-142 — server up but requested model is missing."""
        p = OllamaProvider(model="missing-model", base_url="http://localhost:11434")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "other-model"}]}
        with patch("requests.get", return_value=mock_resp):
            assert p.is_available() is False
        assert "not pulled" in p.info().detail

    def test_ollama_non_200_marks_unavailable(self):
        p = OllamaProvider(base_url="http://localhost:11434")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("requests.get", return_value=mock_resp):
            assert p.is_available() is False

    def test_ollama_generate_posts_prompt(self):
        """Lines 154-162 — generate() POSTs to /api/generate."""
        p = OllamaProvider(model="llama3.1:8b", base_url="http://localhost:11434")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"response": "ollama-text"}
        with patch("requests.post", return_value=mock_resp) as mp:
            out = p.generate("hi")
        assert out == "ollama-text"
        assert mp.call_args[0][0].endswith("/api/generate")


class TestOpenAIGenerate:
    def test_openai_generate_uses_chat_completions(self, monkeypatch):
        """Lines 181-193."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
        p = OpenAIProvider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"choices": [{"message": {"content": "openai-out"}}]}
        with patch("requests.post", return_value=mock_resp) as mp:
            out = p.generate("hi")
        assert out == "openai-out"
        assert "chat/completions" in mp.call_args[0][0]


class TestAnthropicGenerate:
    def test_anthropic_generate(self, monkeypatch):
        """Lines 211-227."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        p = AnthropicProvider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"content": [{"text": "claude-out"}]}
        with patch("requests.post", return_value=mock_resp) as mp:
            out = p.generate("hi")
        assert out == "claude-out"
        headers = mp.call_args.kwargs["headers"]
        assert headers["x-api-key"] == "k"
        assert "anthropic.com" in mp.call_args[0][0]


class TestHFGenerate:
    def test_hf_generate_list_response(self, monkeypatch):
        """Lines 245-256 — list branch of the HF response."""
        monkeypatch.setenv("HF_API_KEY", "hf_k")
        p = HuggingFaceProvider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{"generated_text": "hf-out"}]
        with patch("requests.post", return_value=mock_resp):
            assert p.generate("hi") == "hf-out"

    def test_hf_generate_dict_response(self, monkeypatch):
        monkeypatch.setenv("HF_API_KEY", "hf_k")
        p = HuggingFaceProvider()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"error": "oops"}
        with patch("requests.post", return_value=mock_resp):
            out = p.generate("hi")
        assert "oops" in out


class TestFactoryBranches:
    def test_explicit_choice_not_available_still_returned(self, monkeypatch):
        """Line 309 — explicit provider missing creds logs warning but is returned."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = get_llm_provider("openai")
        # Factory returns the OpenAI instance even though it's not available
        assert isinstance(p, OpenAIProvider)
        assert p.is_available() is False


# ───────────────────── tools.py coverage ──────────────────────

class TestToolsCoverage:

    def test_query_recent_readings(self):
        """Lines 63-66 — nlargest + to_dict path."""
        tools_mod._data_cache.clear()
        out = query_recent_readings("office", domain="demand", n=3)
        assert isinstance(out, list)
        assert len(out) <= 3
        if out:
            assert "value" in out[0]

    def test_run_forecast_mocked(self):
        """Lines 113-117 — forecast dict assembly."""
        import pandas as pd
        tools_mod._data_cache.clear()
        fake_forecast = pd.DataFrame({
            "model": ["stub"] * 4,
            "predicted_kw": [10.0, 20.0, 30.0, 15.0],
        })
        fake_engine = MagicMock()
        fake_engine.forecast.return_value = fake_forecast
        with patch("ml.forecasting.ForecastEngine", return_value=fake_engine):
            out = run_forecast("office", horizon_hours=4)
        assert out["model_used"] == "stub"
        assert out["peak_predicted_kw"] == 30.0
        assert out["forecast_points"] == 4

    def test_run_drift_check_empty_demand(self):
        """Line 186 — 'no demand data' branch."""
        import pandas as pd
        tools_mod._data_cache.clear()
        empty = pd.DataFrame({"domain": [], "ts": [], "value": []})
        with patch("ml.agents.tools._get_data", return_value=empty):
            out = run_drift_check(days=14)
        assert out == {"drift_detected": False, "reason": "no demand data"}

    def test_run_drift_check_insufficient_data(self):
        """Line 191 — 'insufficient data' branch when the split is empty."""
        import pandas as pd
        tools_mod._data_cache.clear()
        # All timestamps on one side of the cutoff → ref or cur ends up empty
        ts = pd.Timestamp("2024-01-01", tz="UTC")
        df = pd.DataFrame({
            "domain": ["demand"] * 3,
            "ts": [ts, ts, ts],
            "value": [1.0, 2.0, 3.0],
        })
        with patch("ml.agents.tools._get_data", return_value=df):
            out = run_drift_check(days=14)
        assert out == {"drift_detected": False, "reason": "insufficient data for split"}

    def test_send_alert_success(self):
        """Lines 218-231 — happy path through TriggerHandler."""
        fake_handler = MagicMock()
        fake_handler.fire.return_value = True
        with patch("triggers.handler.TriggerHandler", return_value=fake_handler):
            out = send_alert("office", "anomaly", "hello")
        assert out == {"sent": True, "facility": "office", "type": "anomaly"}
        fake_handler.fire.assert_called_once()

    def test_send_alert_failure(self):
        fake_handler = MagicMock()
        fake_handler.fire.return_value = False
        with patch("triggers.handler.TriggerHandler", return_value=fake_handler):
            out = send_alert("warehouse", "peak_warning", "x")
        assert out["sent"] is False


# ────────────── specialist agent convenience methods ──────────────

def _patch_run_to(string: str):
    """Short-circuit BaseAgent.run so specialist methods don't hit the LLM path."""
    return patch.object(BaseAgent, "run", return_value=string)


class TestSpecialistConvenienceMethods:

    def test_anomaly_monitor_delegates_to_run(self):
        """anomaly_agent.py line 49."""
        a = AnomalyAgent()
        with patch.object(a, "run", return_value="OK") as mr:
            out = a.monitor("warehouse")
        assert out == "OK"
        assert "warehouse" in mr.call_args[0][0]

    def test_cost_analyze_delegates_to_run(self):
        """cost_agent.py line 50."""
        a = CostAgent()
        with patch.object(a, "run", return_value="OK") as mr:
            out = a.analyze("office")
        assert out == "OK"
        assert "office" in mr.call_args[0][0]

    def test_forecast_predict_delegates_to_run(self):
        """forecast_agent.py line 49."""
        a = ForecastAgent()
        with patch.object(a, "run", return_value="OK") as mr:
            out = a.predict("datacentre", horizon=12)
        assert out == "OK"
        assert "datacentre" in mr.call_args[0][0]
        assert "12" in mr.call_args[0][0]

    def test_optimizer_optimize_delegates_to_run(self):
        """optimizer_agent.py line 51."""
        a = OptimizerAgent()
        with patch.object(a, "run", return_value="OK") as mr:
            out = a.optimize("office", threshold_kw=200.0)
        assert out == "OK"
        assert "200" in mr.call_args[0][0]

    def test_chat_delegates_to_run(self):
        """chat_agent.py line 61."""
        a = ChatAgent()
        with patch.object(a, "run", return_value="OK") as mr:
            out = a.chat("why high?")
        assert out == "OK"
        assert "why high?" in mr.call_args[0][0]


# ─────────────────── orchestrator.py coverage ───────────────────

class TestOrchestratorCoverage:

    def test_ask_single_agent_path(self):
        """Lines 67-75 — single-agent branch of ask()."""
        orch = EnergyOrchestrator()
        with patch.object(orch.anomaly_agent, "run", return_value="no anomalies"):
            out = orch.ask("are there anomalies?", facility_id="office")
        assert "AnomalyAgent" in out
        assert "no anomalies" in out
        assert len(orch.reports) == 1
        assert orch.reports[0].facility_id == "office"

    def test_ask_multi_agent_concatenates(self):
        """Lines 77-85 — multi-agent branch with no exceptions."""
        orch = EnergyOrchestrator()
        # 'anomaly' + 'forecast' keywords → two agents
        with patch.object(orch.anomaly_agent, "run", return_value="A1"), \
             patch.object(orch.forecast_agent, "run", return_value="F1"):
            out = orch.ask("anomaly forecast query", facility_id="warehouse")
        assert "AnomalyAgent" in out and "ForecastAgent" in out
        assert "A1" in out and "F1" in out
        assert "---" in out

    def test_ask_multi_agent_handles_exception(self, caplog):
        """Lines 86-88 — one agent raises, orchestrator keeps going."""
        orch = EnergyOrchestrator()
        with patch.object(orch.anomaly_agent, "run", side_effect=RuntimeError("kaboom")), \
             patch.object(orch.forecast_agent, "run", return_value="F1"):
            with caplog.at_level(logging.ERROR):
                out = orch.ask("anomaly forecast combo")
        assert "Error" in out and "kaboom" in out
        assert "F1" in out

    def test_full_sweep_runs_every_agent(self):
        """Lines 94-123 — happy path for full_sweep."""
        orch = EnergyOrchestrator()
        with patch.object(orch.anomaly_agent, "monitor", return_value="anom"), \
             patch.object(orch.forecast_agent, "predict", return_value="fore"), \
             patch.object(orch.cost_agent, "analyze", return_value="cost"), \
             patch.object(orch.optimizer_agent, "optimize", return_value="opt"):
            res = orch.full_sweep("office")
        assert res == {
            "anomalies": "anom", "forecast": "fore",
            "costs": "cost", "optimization": "opt",
        }
        assert len(orch.reports) == 4
        names = {r.agent_name for r in orch.reports}
        assert names == {"AnomalyAgent", "ForecastAgent", "CostAgent", "OptimizerAgent"}

    def test_get_report_history_formatting(self):
        """get_report_history dict shape."""
        from datetime import datetime, timezone
        orch = EnergyOrchestrator()
        orch.reports.append(AgentReport(
            agent_name="AnomalyAgent", facility_id="office",
            summary="x" * 500, timestamp=datetime.now(timezone.utc),
        ))
        hist = orch.get_report_history()
        assert len(hist) == 1
        row = hist[0]
        assert row["agent"] == "AnomalyAgent"
        assert row["facility"] == "office"
        assert len(row["summary"]) == 200   # truncated to 200 chars
        assert "T" in row["timestamp"]       # ISO format
