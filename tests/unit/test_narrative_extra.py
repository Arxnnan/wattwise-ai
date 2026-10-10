"""Additional unit tests for ml.narrative — exercises Gemini + HF fallback paths."""
import sys
import types
import pytest
from unittest.mock import MagicMock, patch

from ml import narrative as nmod
from ml.narrative import (
    NarrativeEngine,
    NarrativeRequest,
    _build_prompt,
    _template_narrative,
    _gemini_narrative,
    _huggingface_narrative,
)


# ---------------------------------------------------------------------------
# _build_prompt — every branch
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_anomaly_prompt_includes_facility_and_score(self):
        req = NarrativeRequest(
            narrative_type="anomaly",
            facility_id="office",
            device_id="hvac-01",
            observed_value=100.0,
            expected_value=50.0,
            anomaly_score=0.9,
        )
        prompt = _build_prompt(req)
        assert "office" in prompt
        assert "hvac-01" in prompt
        assert "Anomaly score" in prompt
        assert "+100.0%" in prompt

    def test_peak_warning_prompt_includes_shed_plan(self):
        req = NarrativeRequest(
            narrative_type="peak_warning",
            facility_id="warehouse",
            device_id="main",
            observed_value=0.0,
            expected_value=0.0,
            peak_threshold_kw=300.0,
            predicted_kw=270.0,
            shed_plan=["LoadA", "LoadB"],
        )
        prompt = _build_prompt(req)
        assert "warehouse" in prompt
        assert "LoadA" in prompt
        assert "Utilisation" in prompt

    def test_optimization_prompt_includes_context(self):
        req = NarrativeRequest(
            narrative_type="optimization",
            facility_id="dc",
            device_id="d1",
            observed_value=120.0,
            expected_value=95.0,
            extra_context="cooling spike",
        )
        prompt = _build_prompt(req)
        assert "optimization" in prompt.lower()
        assert "cooling spike" in prompt

    def test_forecast_prompt_default_branch(self):
        req = NarrativeRequest(
            narrative_type="forecast",
            facility_id="plant",
            device_id="x",
            observed_value=0.0,
            expected_value=0.0,
            predicted_kw=175.0,
        )
        prompt = _build_prompt(req)
        assert "forecast" in prompt.lower()
        assert "plant" in prompt
        assert "175.0" in prompt


# ---------------------------------------------------------------------------
# _template_narrative — the forecast branch not covered elsewhere, and a
# negative-deviation anomaly to hit the "below" branch.
# ---------------------------------------------------------------------------

class TestTemplateNarrative:
    def test_template_forecast(self):
        req = NarrativeRequest(
            narrative_type="forecast",
            facility_id="plant",
            device_id="x",
            observed_value=0.0,
            expected_value=0.0,
            predicted_kw=42.0,
        )
        text = _template_narrative(req)
        assert "Plant" in text
        assert "42.0 kW" in text

    def test_template_anomaly_below(self):
        req = NarrativeRequest(
            narrative_type="anomaly",
            facility_id="office",
            device_id="d",
            observed_value=10.0,
            expected_value=20.0,
            anomaly_score=0.5,
        )
        text = _template_narrative(req)
        assert "below" in text


# ---------------------------------------------------------------------------
# _gemini_narrative
# ---------------------------------------------------------------------------

class TestGeminiNarrative:
    def test_returns_none_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert _gemini_narrative("hi") is None

    def test_returns_none_on_empty_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        assert _gemini_narrative("hi") is None

    def test_success_returns_stripped_text(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        fake_response = MagicMock()
        fake_response.text = "  Gemini says hi.  "
        fake_model = MagicMock()
        fake_model.generate_content.return_value = fake_response

        fake_genai = types.ModuleType("google.generativeai")
        fake_genai.configure = MagicMock()
        fake_genai.GenerativeModel = MagicMock(return_value=fake_model)

        fake_google = types.ModuleType("google")
        fake_google.generativeai = fake_genai

        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

        out = _gemini_narrative("prompt-text")
        assert out == "Gemini says hi."
        fake_genai.configure.assert_called_once_with(api_key="fake-key")
        fake_genai.GenerativeModel.assert_called_once_with("gemini-2.5-flash")
        fake_model.generate_content.assert_called_once_with("prompt-text")

    def test_exception_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        fake_genai = types.ModuleType("google.generativeai")
        def boom(*a, **k):
            raise RuntimeError("configure blew up")
        fake_genai.configure = boom
        fake_genai.GenerativeModel = MagicMock()

        fake_google = types.ModuleType("google")
        fake_google.generativeai = fake_genai

        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

        assert _gemini_narrative("prompt") is None


# ---------------------------------------------------------------------------
# _huggingface_narrative
# ---------------------------------------------------------------------------

class TestHuggingFaceNarrative:
    def test_returns_none_without_token(self, monkeypatch):
        monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
        assert _huggingface_narrative("hi") is None

    def test_returns_none_on_empty_token(self, monkeypatch):
        monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "")
        assert _huggingface_narrative("hi") is None

    def test_success_returns_stripped_text(self, monkeypatch):
        monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "hf-token")

        fake_client = MagicMock()
        fake_client.text_generation.return_value = "   HF reply.   "

        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.InferenceClient = MagicMock(return_value=fake_client)
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

        out = _huggingface_narrative("hello")
        assert out == "HF reply."
        fake_hub.InferenceClient.assert_called_once_with(token="hf-token")
        fake_client.text_generation.assert_called_once()
        kwargs = fake_client.text_generation.call_args.kwargs
        assert kwargs["model"] == "mistralai/Mistral-7B-Instruct-v0.3"
        assert kwargs["max_new_tokens"] == 150

    def test_exception_returns_none(self, monkeypatch):
        monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "hf-token")

        fake_hub = types.ModuleType("huggingface_hub")
        def boom(*a, **k):
            raise RuntimeError("network down")
        fake_hub.InferenceClient = boom
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

        assert _huggingface_narrative("hello") is None


# ---------------------------------------------------------------------------
# NarrativeEngine.generate — fallback chain
# ---------------------------------------------------------------------------

class TestEngineFallbackChain:
    def _req(self):
        return NarrativeRequest(
            narrative_type="anomaly",
            facility_id="office",
            device_id="d1",
            observed_value=100.0,
            expected_value=50.0,
            anomaly_score=0.8,
        )

    def test_engine_uses_gemini_when_available(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative",
                            lambda prompt: "GEMINI-OUTPUT")
        monkeypatch.setattr(nmod, "_huggingface_narrative",
                            lambda prompt: pytest.fail("HF should not run"))
        monkeypatch.setattr(nmod, "_template_narrative",
                            lambda req: pytest.fail("template should not run"))

        out = NarrativeEngine().generate(self._req())
        assert out == "GEMINI-OUTPUT"

    def test_engine_falls_back_to_hf_when_gemini_none(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: None)
        monkeypatch.setattr(nmod, "_huggingface_narrative",
                            lambda prompt: "HF-OUTPUT")
        monkeypatch.setattr(nmod, "_template_narrative",
                            lambda req: pytest.fail("template should not run"))

        out = NarrativeEngine().generate(self._req())
        assert out == "HF-OUTPUT"

    def test_engine_falls_back_to_template_when_both_none(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: None)
        monkeypatch.setattr(nmod, "_huggingface_narrative", lambda prompt: None)

        out = NarrativeEngine().generate(self._req())
        assert isinstance(out, str)
        assert "office" in out.lower()

    def test_engine_treats_empty_gemini_output_as_failure(self, monkeypatch):
        """Empty strings are falsy, so engine should fall through to HF."""
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: "")
        monkeypatch.setattr(nmod, "_huggingface_narrative",
                            lambda prompt: "HF-FALLBACK")
        out = NarrativeEngine().generate(self._req())
        assert out == "HF-FALLBACK"


# ---------------------------------------------------------------------------
# Edge-case inputs
# ---------------------------------------------------------------------------

class TestEdgeCaseInputs:
    def test_zero_expected_value_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: None)
        monkeypatch.setattr(nmod, "_huggingface_narrative", lambda prompt: None)
        req = NarrativeRequest(
            narrative_type="anomaly",
            facility_id="site",
            device_id="d",
            observed_value=5.0,
            expected_value=0.0,
            anomaly_score=0.1,
        )
        out = NarrativeEngine().generate(req)
        assert isinstance(out, str) and len(out) > 0

    def test_peak_warning_template_handles_zero_threshold(self):
        """_template_narrative uses +1e-6 guard, so a zero threshold is safe
        in the template path (even though _build_prompt itself would raise)."""
        req = NarrativeRequest(
            narrative_type="peak_warning",
            facility_id="site",
            device_id="d",
            observed_value=0.0,
            expected_value=0.0,
            peak_threshold_kw=0.0,
            predicted_kw=10.0,
            shed_plan=[],
        )
        out = _template_narrative(req)
        assert "PEAK WARNING" in out

    def test_peak_warning_full_chain_with_nonzero_threshold(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: None)
        monkeypatch.setattr(nmod, "_huggingface_narrative", lambda prompt: None)
        req = NarrativeRequest(
            narrative_type="peak_warning",
            facility_id="site",
            device_id="d",
            observed_value=0.0,
            expected_value=0.0,
            peak_threshold_kw=100.0,
            predicted_kw=90.0,
            shed_plan=["load-a"],
        )
        out = NarrativeEngine().generate(req)
        assert "PEAK WARNING" in out

    def test_optimization_negative_savings_clamped(self, monkeypatch):
        monkeypatch.setattr(nmod, "_gemini_narrative", lambda prompt: None)
        monkeypatch.setattr(nmod, "_huggingface_narrative", lambda prompt: None)
        req = NarrativeRequest(
            narrative_type="optimization",
            facility_id="site",
            device_id="d",
            observed_value=10.0,
            expected_value=100.0,
            extra_context="under benchmark",
        )
        out = NarrativeEngine().generate(req)
        # max(0, 10 - 100) == 0, so "0.0 kW" must appear
        assert "0.0 kW" in out
        assert "under benchmark" in out
