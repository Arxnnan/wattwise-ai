"""WattWise AI — caption engine.

3-tier AI-powered caption generator for short natural-language "why" / "insight"
text under every KPI card and chart.

- Tier 1: pre-computed captions cached per-session (expensive but infrequent)
- Tier 2: on-demand template+LLM hybrid (fast, cached in-memory)
- Tier 3: fallback template-only (no LLM needed)

Reuses the existing provider-agnostic wrapper at ``ml.agents.llm_provider``.
Prompts are intentionally short (~100 tokens in, ~30 out) to keep latency
and cost low across free-tier providers (Gemini / Groq / Ollama).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Literal, Optional

log = logging.getLogger(__name__)

CaptionType = Literal["kpi", "chart", "delta", "trend"]

# Hard cap on words in a returned caption. The LLM is instructed to stay
# under 15 words; if it doesn't, we truncate to keep the UI stable.
MAX_WORDS = 15

SYSTEM_PROMPT = (
    "You write 1-line energy data insights. "
    "Max 15 words. No preamble. No \"I think\". Just the finding."
)


@dataclass
class CaptionResult:
    text: str
    source: Literal["llm", "template", "cache"]
    confidence: Literal["high", "medium", "low"]


def _truncate_words(text: str, max_words: int = MAX_WORDS) -> str:
    """Clip text to ``max_words`` words. If the clip chops a sentence, append '…'."""
    if not text:
        return ""
    # Collapse whitespace / strip quotes and leading dashes the LLM sometimes adds
    cleaned = " ".join(text.strip().strip('"').strip("'").split())
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]) + "…"


class CaptionEngine:
    """3-tier caption engine.

    Tier 1 (``_cache``): memoized ``CaptionResult`` per deterministic context hash.
    Tier 2 (``_call_llm``): LLM-generated 1-liner, cached on success.
    Tier 3 (``_template_fallback``): deterministic templated string that never raises.
    """

    def __init__(self, llm_provider=None):
        if llm_provider is None:
            # Lazy import so this module is importable without the agents subpackage ready.
            from ml.agents.llm_provider import get_llm_provider
            self._provider = get_llm_provider()
        else:
            self._provider = llm_provider
        self._cache: dict[str, CaptionResult] = {}

    # ────────────────────────── caching ──────────────────────────

    def _cache_key(self, caption_type: CaptionType, context: dict) -> str:
        """Deterministic SHA-1 hash of (type + context) for in-memory caching."""
        try:
            payload = json.dumps(context, sort_keys=True, default=str)
        except Exception:
            # Last-resort stringification so the engine never crashes on weird objects.
            payload = repr(sorted(context.items())) if context else ""
        raw = f"{caption_type}|{payload}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        self._cache.clear()

    # ────────────────────────── public API ──────────────────────────

    def caption_kpi(
        self,
        metric_name: str,
        current_value: float,
        prior_value: float,
        unit: str = "",
        facility: str = "",
    ) -> CaptionResult:
        """Short 1-line caption for a KPI card."""
        ctx = {
            "metric_name": metric_name,
            "current_value": current_value,
            "prior_value": prior_value,
            "unit": unit,
            "facility": facility,
        }
        key = self._cache_key("kpi", ctx)
        hit = self._cache.get(key)
        if hit is not None:
            return CaptionResult(text=hit.text, source="cache", confidence=hit.confidence)

        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"Metric: {metric_name} is {current_value}{unit} vs prior {prior_value}{unit}. "
            f"Facility: {facility or 'n/a'}. Say WHY in one line."
        )
        llm_text = self._call_llm(prompt)
        if llm_text:
            result = CaptionResult(
                text=_truncate_words(llm_text),
                source="llm",
                confidence="high",
            )
            self._cache[key] = result
            return result

        result = self._template_fallback("kpi", ctx)
        self._cache[key] = result
        return result

    def caption_chart(
        self,
        chart_title: str,
        data_summary: dict,
    ) -> CaptionResult:
        """1-2 sentence insight for a chart (truncated to 15 words max)."""
        ctx = {"chart_title": chart_title, "data_summary": dict(data_summary or {})}
        key = self._cache_key("chart", ctx)
        hit = self._cache.get(key)
        if hit is not None:
            return CaptionResult(text=hit.text, source="cache", confidence=hit.confidence)

        summary_str = ", ".join(f"{k}={v}" for k, v in (data_summary or {}).items())
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"Chart: {chart_title}. Summary: {summary_str or 'no data'}. "
            f"Say the main finding in one line."
        )
        llm_text = self._call_llm(prompt)
        if llm_text:
            result = CaptionResult(
                text=_truncate_words(llm_text),
                source="llm",
                confidence="high",
            )
            self._cache[key] = result
            return result

        result = self._template_fallback("chart", ctx)
        self._cache[key] = result
        return result

    def caption_delta(
        self,
        metric_name: str,
        pct_change: float,
        direction: Literal["up", "down", "flat"],
        context_hint: str = "",
    ) -> CaptionResult:
        """Short caption explaining WHY a delta exists."""
        ctx = {
            "metric_name": metric_name,
            "pct_change": pct_change,
            "direction": direction,
            "context_hint": context_hint,
        }
        key = self._cache_key("delta", ctx)
        hit = self._cache.get(key)
        if hit is not None:
            return CaptionResult(text=hit.text, source="cache", confidence=hit.confidence)

        hint = f" Context: {context_hint}." if context_hint else ""
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"Delta: {metric_name} moved {direction} by {pct_change:.1f}%.{hint} "
            f"Say WHY in one line."
        )
        llm_text = self._call_llm(prompt)
        if llm_text:
            result = CaptionResult(
                text=_truncate_words(llm_text),
                source="llm",
                confidence="high",
            )
            self._cache[key] = result
            return result

        result = self._template_fallback("delta", ctx)
        self._cache[key] = result
        return result

    # ────────────────────────── internals ──────────────────────────

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Thin wrapper around ``self._provider.generate``.

        Returns the raw string on success, or ``None`` on ANY failure
        (missing provider, unavailable provider, exception, empty response).
        Returning ``None`` triggers the template fallback path.
        """
        provider = self._provider
        if provider is None:
            return None
        try:
            if hasattr(provider, "is_available") and not provider.is_available():
                return None
            text = provider.generate(prompt)
        except Exception as e:  # noqa: BLE001 — fallback is the whole point
            log.debug("[caption_engine] LLM call failed: %s", e)
            return None
        if not text or not str(text).strip():
            return None
        return str(text)

    def _template_fallback(self, caption_type: CaptionType, context: dict) -> CaptionResult:
        """Deterministic templated caption. MUST NOT raise."""
        try:
            ctx = context or {}
            if caption_type == "kpi":
                name = ctx.get("metric_name", "metric")
                cur = ctx.get("current_value", 0) or 0
                prior = ctx.get("prior_value", 0) or 0
                unit = ctx.get("unit", "") or ""
                facility = ctx.get("facility", "") or ""
                try:
                    delta = float(cur) - float(prior)
                except (TypeError, ValueError):
                    delta = 0.0
                direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
                where = f" at {facility}" if facility else ""
                text = f"{name} {direction} vs prior ({cur}{unit} from {prior}{unit}){where}."
            elif caption_type == "chart":
                title = ctx.get("chart_title", "chart")
                summary = ctx.get("data_summary", {}) or {}
                trend = summary.get("trend", "steady")
                text = f"{title}: trend is {trend} based on the current window."
            elif caption_type == "delta":
                name = ctx.get("metric_name", "metric")
                pct = ctx.get("pct_change", 0.0) or 0.0
                direction = ctx.get("direction", "flat")
                hint = ctx.get("context_hint", "") or ""
                try:
                    pct_f = float(pct)
                except (TypeError, ValueError):
                    pct_f = 0.0
                base = f"{name} moved {direction} by {abs(pct_f):.1f}%."
                text = f"{base} {hint}".strip() if hint else base
            else:  # pragma: no cover - defensive; caption_type is a Literal
                text = "No insight available."
        except Exception as e:  # pragma: no cover - last-resort guard
            log.debug("[caption_engine] template fallback error: %s", e)
            text = "No insight available."
        return CaptionResult(
            text=_truncate_words(text),
            source="template",
            confidence="low",
        )
