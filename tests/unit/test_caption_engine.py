"""Tests for ml.analytics.caption_engine.

ZERO real LLM calls — every provider is a MagicMock.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ml.analytics.caption_engine import (
    CaptionEngine,
    CaptionResult,
    MAX_WORDS,
    SYSTEM_PROMPT,
    _truncate_words,
)


# ────────────────────────── helpers ──────────────────────────


def make_provider(return_value="Driven mostly by warehouse 3rd shift", available=True):
    """Return a MagicMock that quacks like an LLMProvider."""
    m = MagicMock()
    m.is_available.return_value = available
    m.generate.return_value = return_value
    return m


# ────────────────────────── _truncate_words ──────────────────────────


class TestTruncateWords:
    def test_short_untouched(self):
        assert _truncate_words("short string") == "short string"

    def test_empty_safe(self):
        assert _truncate_words("") == ""
        assert _truncate_words(None) == ""  # type: ignore[arg-type]

    def test_strips_quotes_and_whitespace(self):
        assert _truncate_words('  "hello world"  ') == "hello world"

    def test_truncates_past_limit(self):
        long = " ".join([f"w{i}" for i in range(MAX_WORDS + 5)])
        out = _truncate_words(long)
        assert out.endswith("…")
        # 15 words + ellipsis suffix
        assert len(out.rstrip("…").split()) == MAX_WORDS


# ────────────────────────── init / provider wiring ──────────────────────────


class TestInit:
    def test_uses_injected_provider(self):
        p = make_provider()
        eng = CaptionEngine(llm_provider=p)
        assert eng._provider is p
        assert eng._cache == {}

    def test_default_provider_from_factory(self):
        with patch("ml.agents.llm_provider.get_llm_provider") as factory:
            factory.return_value = make_provider()
            eng = CaptionEngine()
            factory.assert_called_once()
            assert eng._provider is factory.return_value


# ────────────────────────── caption_kpi ──────────────────────────


class TestCaptionKpi:
    def test_happy_path(self):
        p = make_provider("Peak demand climbing fast")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("peak_demand_kw", 42.0, 34.0, unit="kW", facility="warehouse")
        assert isinstance(out, CaptionResult)
        assert out.source == "llm"
        assert out.confidence == "high"
        assert out.text == "Peak demand climbing fast"
        p.generate.assert_called_once()
        # Prompt carries the instructions and metric details
        prompt = p.generate.call_args[0][0]
        assert "15 words" in prompt
        assert "peak_demand_kw" in prompt
        assert "warehouse" in prompt

    def test_llm_failure_falls_back_to_template(self):
        p = make_provider()
        p.generate.side_effect = RuntimeError("provider exploded")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("usage_kwh", 100.0, 110.0, unit="kWh", facility="office")
        assert out.source == "template"
        assert out.confidence == "low"
        assert "usage_kwh" in out.text
        assert "down" in out.text  # 100 < 110

    def test_llm_unavailable_falls_back(self):
        p = make_provider(available=False)
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("x", 1.0, 2.0)
        assert out.source == "template"
        p.generate.assert_not_called()

    def test_empty_llm_response_falls_back(self):
        p = make_provider("   ")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("x", 1.0, 1.0)
        assert out.source == "template"
        assert "flat" in out.text

    def test_llm_long_response_is_truncated(self):
        long = " ".join([f"word{i}" for i in range(50)])
        p = make_provider(long)
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("x", 1.0, 2.0)
        assert out.source == "llm"
        assert out.text.endswith("…")
        assert len(out.text.rstrip("…").split()) == MAX_WORDS


# ────────────────────────── caption_chart ──────────────────────────


class TestCaptionChart:
    @pytest.mark.parametrize("trend", ["rising", "flat", "falling"])
    def test_each_trend_type(self, trend):
        p = make_provider(f"Trend is {trend} this week")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_chart(
            "Hourly demand",
            {"max": 42, "mean": 18, "trend": trend, "facility": "office"},
        )
        assert out.source == "llm"
        assert trend in out.text
        prompt = p.generate.call_args[0][0]
        assert "Hourly demand" in prompt
        assert f"trend={trend}" in prompt

    def test_template_fallback_uses_trend(self):
        p = make_provider(available=False)
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_chart("Load", {"trend": "rising"})
        assert out.source == "template"
        assert "rising" in out.text
        assert "Load" in out.text

    def test_empty_data_summary(self):
        p = make_provider("Steady baseline")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_chart("Load", {})
        assert out.source == "llm"
        assert "no data" in p.generate.call_args[0][0]

    def test_none_data_summary_safe(self):
        p = make_provider("ok")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_chart("Load", None)  # type: ignore[arg-type]
        assert out.source == "llm"


# ────────────────────────── caption_delta ──────────────────────────


class TestCaptionDelta:
    @pytest.mark.parametrize("direction", ["up", "down", "flat"])
    def test_each_direction(self, direction):
        p = make_provider(f"Moved {direction}")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_delta("usage", 12.3, direction, context_hint="3rd shift")
        assert out.source == "llm"
        prompt = p.generate.call_args[0][0]
        assert direction in prompt
        assert "3rd shift" in prompt
        assert "12.3%" in prompt

    def test_template_fallback_no_hint(self):
        p = make_provider(available=False)
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_delta("usage", -5.0, "down")
        assert out.source == "template"
        assert "down" in out.text
        assert "5.0%" in out.text

    def test_template_fallback_with_hint(self):
        p = make_provider(available=False)
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_delta("usage", 5.0, "up", context_hint="holiday")
        assert out.source == "template"
        assert "holiday" in out.text


# ────────────────────────── caching ──────────────────────────


class TestCaching:
    def test_cache_hit_on_second_call(self):
        p = make_provider("One liner")
        eng = CaptionEngine(llm_provider=p)
        first = eng.caption_kpi("m", 1.0, 2.0, unit="kW", facility="A")
        second = eng.caption_kpi("m", 1.0, 2.0, unit="kW", facility="A")
        assert first.source == "llm"
        assert second.source == "cache"
        assert second.text == first.text
        assert second.confidence == first.confidence
        # LLM called exactly once
        assert p.generate.call_count == 1

    def test_different_contexts_different_keys(self):
        p = make_provider("x")
        eng = CaptionEngine(llm_provider=p)
        k1 = eng._cache_key("kpi", {"metric": "a"})
        k2 = eng._cache_key("kpi", {"metric": "b"})
        k3 = eng._cache_key("chart", {"metric": "a"})
        assert k1 != k2
        assert k1 != k3
        # Deterministic
        assert k1 == eng._cache_key("kpi", {"metric": "a"})

    def test_cache_key_insensitive_to_dict_order(self):
        eng = CaptionEngine(llm_provider=make_provider())
        a = eng._cache_key("kpi", {"a": 1, "b": 2})
        b = eng._cache_key("kpi", {"b": 2, "a": 1})
        assert a == b

    def test_cache_key_handles_non_serializable(self):
        eng = CaptionEngine(llm_provider=make_provider())

        class Weird:
            def __repr__(self):
                return "WEIRD"

        # Must not raise; must be deterministic.
        key = eng._cache_key("kpi", {"obj": Weird()})
        assert isinstance(key, str)
        assert len(key) == 40  # sha1 hex

    def test_cache_key_recovers_when_json_dumps_raises(self):
        """Covers the except-branch for truly un-dumpable contexts."""
        eng = CaptionEngine(llm_provider=make_provider())
        with patch("ml.analytics.caption_engine.json.dumps", side_effect=TypeError("nope")):
            key = eng._cache_key("kpi", {"a": 1})
            empty = eng._cache_key("kpi", {})
        assert isinstance(key, str) and len(key) == 40
        assert isinstance(empty, str) and len(empty) == 40
        assert key != empty

    def test_clear_cache_resets_state(self):
        p = make_provider("A")
        eng = CaptionEngine(llm_provider=p)
        eng.caption_kpi("m", 1.0, 2.0)
        assert eng._cache  # populated
        eng.clear_cache()
        assert eng._cache == {}
        # Next call hits LLM again
        eng.caption_kpi("m", 1.0, 2.0)
        assert p.generate.call_count == 2

    def test_source_is_cache_on_hit_for_each_type(self):
        p = make_provider("short")
        eng = CaptionEngine(llm_provider=p)
        eng.caption_chart("t", {"trend": "rising"})
        again = eng.caption_chart("t", {"trend": "rising"})
        assert again.source == "cache"

        eng.caption_delta("m", 1.0, "up")
        again2 = eng.caption_delta("m", 1.0, "up")
        assert again2.source == "cache"

    def test_template_results_also_cached(self):
        """Fallback results cache too, so the LLM isn't retried on every miss."""
        p = make_provider(available=False)
        eng = CaptionEngine(llm_provider=p)
        first = eng.caption_kpi("x", 1.0, 2.0)
        second = eng.caption_kpi("x", 1.0, 2.0)
        assert first.source == "template"
        assert second.source == "cache"


# ────────────────────────── _call_llm safety ──────────────────────────


class TestCallLlm:
    def test_returns_none_when_provider_missing(self):
        eng = CaptionEngine(llm_provider=make_provider())
        eng._provider = None
        assert eng._call_llm("p") is None

    def test_returns_none_when_unavailable(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        assert eng._call_llm("p") is None

    def test_catches_arbitrary_exception(self):
        p = make_provider()
        p.generate.side_effect = ValueError("boom")
        eng = CaptionEngine(llm_provider=p)
        assert eng._call_llm("p") is None

    def test_catches_base_exception_like_runtime(self):
        p = make_provider()
        p.generate.side_effect = RuntimeError("nope")
        eng = CaptionEngine(llm_provider=p)
        assert eng._call_llm("p") is None

    def test_empty_string_returns_none(self):
        p = make_provider("")
        eng = CaptionEngine(llm_provider=p)
        assert eng._call_llm("p") is None

    def test_whitespace_returns_none(self):
        p = make_provider("    \n\t ")
        eng = CaptionEngine(llm_provider=p)
        assert eng._call_llm("p") is None

    def test_non_string_coerced(self):
        p = make_provider(12345)  # provider could return an int by mistake
        eng = CaptionEngine(llm_provider=p)
        out = eng._call_llm("p")
        assert out == "12345"

    def test_provider_without_is_available_still_works(self):
        """A duck-typed provider that lacks ``is_available`` must still be callable."""
        p = MagicMock(spec=["generate"])
        p.generate.return_value = "hi"
        eng = CaptionEngine(llm_provider=p)
        assert eng._call_llm("p") == "hi"


# ────────────────────────── template fallback safety ──────────────────────────


class TestTemplateFallback:
    def test_never_raises_on_empty_context(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        out = eng._template_fallback("kpi", {})
        assert out.source == "template"
        assert out.text  # non-empty

    def test_never_raises_on_none_context(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        out = eng._template_fallback("chart", None)  # type: ignore[arg-type]
        assert out.source == "template"
        assert out.text

    def test_handles_bad_numeric_values(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        out = eng._template_fallback(
            "kpi",
            {"metric_name": "m", "current_value": "not-a-number", "prior_value": None, "unit": "kW"},
        )
        assert out.source == "template"
        assert "flat" in out.text  # non-numeric collapses to zero-delta

    def test_delta_handles_bad_pct(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        out = eng._template_fallback(
            "delta",
            {"metric_name": "m", "pct_change": "bad", "direction": "up"},
        )
        assert out.source == "template"
        assert "0.0%" in out.text

    def test_kpi_up_direction(self):
        eng = CaptionEngine(llm_provider=make_provider(available=False))
        out = eng._template_fallback(
            "kpi",
            {"metric_name": "m", "current_value": 10, "prior_value": 5},
        )
        assert "up" in out.text


# ────────────────────────── empty / edge contexts ──────────────────────────


class TestEdgeCases:
    def test_caption_kpi_with_no_optional_args(self):
        p = make_provider("ok")
        eng = CaptionEngine(llm_provider=p)
        out = eng.caption_kpi("x", 0.0, 0.0)
        assert out.source == "llm"
        # Facility missing → prompt uses n/a
        assert "n/a" in p.generate.call_args[0][0]

    def test_system_prompt_constant(self):
        assert "15 words" in SYSTEM_PROMPT
        assert "preamble" in SYSTEM_PROMPT

    def test_dataclass_shape(self):
        r = CaptionResult(text="x", source="llm", confidence="high")
        assert r.text == "x"
        assert r.source == "llm"
        assert r.confidence == "high"
