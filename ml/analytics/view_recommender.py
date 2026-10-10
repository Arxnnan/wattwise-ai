"""WattWise AI — Per-View AI Recommendation Router.

Each dashboard view (Real-Time, Demand, Cost, Benchmark, etc.) renders a
single context-specific recommendation strip at the top of the page. This
module routes the full BriefingAgent output through a view -> category
filter and picks the single most relevant recommendation for that view.

The router adds business framing (business_value, why_this_matters) so the
UI can show a short, human-readable headline without re-querying any LLM.

Caching is per (view, facility_id). The cache lives on the instance; it is
small (bounded by the number of (view, facility) pairs) and is cleared with
``clear_cache()`` or bypassed with ``force_refresh=True``.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

log = logging.getLogger(__name__)


ViewName = Literal[
    "Real-Time Consumption",
    "Demand Pattern Analysis",
    "Cost Analysis",
    "AI Optimization",
    "Cross-Facility Benchmark",
    "Full Agent Sweep",
    "AI Chat Agent",
]


# Which agent categories each view surfaces. The order of the list is the
# priority order: when multiple categories are available, the earliest
# matching category wins. "AI Chat Agent" intentionally has no strip.
VIEW_TO_CATEGORY: dict[str, list[str]] = {
    "Real-Time Consumption":    ["anomaly", "optimization"],
    "Demand Pattern Analysis":  ["optimization", "forecast"],
    "Cost Analysis":            ["cost", "optimization"],
    "AI Optimization":          ["anomaly", "forecast", "optimization"],
    "Cross-Facility Benchmark": ["optimization", "cost"],
    "Full Agent Sweep":         ["anomaly", "forecast", "cost", "optimization"],
    "AI Chat Agent":            [],  # no strip
}


@dataclass
class ViewRecommendation:
    """One AI suggestion scoped to a specific view."""

    id: str
    view: str
    facility_id: str
    title: str
    rationale: str
    impact_inr_month: float
    confidence: float
    category: str
    agent_name: str
    action_type: str
    business_value: str
    why_this_matters: str
    one_click_payload: dict = field(default_factory=dict)
    counterfactual: str = ""


def _format_inr(value: float) -> str:
    """Compact Indian-rupee formatting: 150000 -> '1.5L', 2500 -> '2,500'."""
    abs_v = abs(value)
    if abs_v >= 1_00_000:  # >= 1 Lakh
        return f"Rs {value / 1_00_000:.1f}L"
    if abs_v >= 1_000:
        return f"Rs {int(round(value)):,}"
    return f"Rs {int(round(value))}"


class ViewRecommender:
    """Routes BriefingAgent output to view-specific recommendations.

    Caches per (view, facility) pair to avoid re-running agents on every
    Streamlit rerender. Use ``force_refresh=True`` to bypass the cache or
    ``clear_cache()`` to wipe it entirely.
    """

    def __init__(self, briefing_agent: Any | None = None) -> None:
        self._agent = briefing_agent
        self._cache: dict[tuple[str, str], Optional[ViewRecommendation]] = {}

    # ---- agent loading ---------------------------------------------------

    def _get_agent(self) -> Any:
        """Lazy-load BriefingAgent on first use."""
        if self._agent is None:
            from ml.agents.briefing_agent import BriefingAgent
            self._agent = BriefingAgent()
        return self._agent

    # ---- public API ------------------------------------------------------

    def recommend(
        self,
        view: str,
        facility_id: str,
        force_refresh: bool = False,
    ) -> Optional[ViewRecommendation]:
        """Return the top ViewRecommendation for this view, or None.

        Returns None for views with no configured categories (e.g. the
        chat view) and for views where the briefing produced nothing
        relevant to this view's category filter.
        """
        categories = VIEW_TO_CATEGORY.get(view, [])
        if not categories:
            return None

        cache_key = (view, facility_id)
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            agent = self._get_agent()
            raw: list = agent.generate(facility_id) or []
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("ViewRecommender: briefing agent failed: %s", exc)
            raw = []

        if not raw:
            self._cache[cache_key] = None
            return None

        filtered = self._filter_by_category(raw, categories)
        if not filtered:
            self._cache[cache_key] = None
            return None

        # Prefer the earliest category in the view's priority list, then
        # by impact * confidence (which is already BriefingAgent's rank).
        priority = {cat: i for i, cat in enumerate(categories)}
        filtered.sort(
            key=lambda r: (
                priority.get(r.category, len(categories)),
                -(r.impact_inr_month * r.confidence),
            )
        )
        top = filtered[0]
        enriched = self._enrich_business_value(top, view)
        self._cache[cache_key] = enriched
        return enriched

    # ---- filtering / enrichment -----------------------------------------

    def _filter_by_category(self, recommendations: list, categories: list[str]) -> list:
        """Keep only recs whose ``category`` is in ``categories``."""
        allowed = set(categories)
        return [r for r in recommendations if getattr(r, "category", None) in allowed]

    def _enrich_business_value(self, rec: Any, view: str) -> ViewRecommendation:
        """Convert an ActionRecommendation into a ViewRecommendation."""
        return ViewRecommendation(
            id=getattr(rec, "id", str(uuid.uuid4())),
            view=view,
            facility_id=getattr(rec, "facility_id", ""),
            title=getattr(rec, "title", ""),
            rationale=getattr(rec, "rationale", ""),
            impact_inr_month=float(getattr(rec, "impact_inr_month", 0.0)),
            confidence=float(getattr(rec, "confidence", 0.0)),
            category=getattr(rec, "category", ""),
            agent_name=getattr(rec, "agent_name", ""),
            action_type=getattr(rec, "action_type", ""),
            business_value=self._format_business_value(
                float(getattr(rec, "impact_inr_month", 0.0)),
                getattr(rec, "category", ""),
            ),
            why_this_matters=self._why_this_matters(
                view,
                getattr(rec, "category", ""),
                float(getattr(rec, "impact_inr_month", 0.0)),
            ),
            one_click_payload=dict(getattr(rec, "one_click_payload", {}) or {}),
            counterfactual=getattr(rec, "counterfactual", "") or "",
        )

    def _format_business_value(self, impact: float, category: str) -> str:
        """Human-friendly business value string, keyed by category."""
        amount = _format_inr(impact)
        if category == "cost":
            return f"{amount}/mo saved"
        if category == "anomaly":
            return f"Avoids {amount} compressor failure risk"
        if category == "optimization":
            return f"{amount}/mo peak-shed opportunity"
        if category == "forecast":
            return f"Peak charge avoidance ({amount}/mo)"
        return f"{amount}/mo impact"

    def _why_this_matters(self, view: str, category: str, impact: float) -> str:
        """View-aware business rationale shown under the headline."""
        amount = _format_inr(impact)
        if view == "Real-Time Consumption":
            return (
                f"Live telemetry shows an issue worth {amount}/mo if "
                "left unaddressed."
            )
        if view == "Demand Pattern Analysis":
            return (
                f"Demand patterns suggest a {amount}/mo scheduling "
                "opportunity."
            )
        if view == "Cost Analysis":
            return (
                f"Tariff exposure can be reduced by {amount}/mo with this "
                "action."
            )
        if view == "AI Optimization":
            return (
                f"Optimization sweep flagged a {category} opportunity "
                f"worth {amount}/mo."
            )
        if view == "Cross-Facility Benchmark":
            return (
                f"Peer facilities already capture this {amount}/mo "
                "benefit."
            )
        if view == "Full Agent Sweep":
            return (
                f"Top-ranked {category} finding across all agents "
                f"({amount}/mo)."
            )
        return f"Impact {amount}/mo for {category}."

    # ---- cache management -----------------------------------------------

    def clear_cache(self) -> None:
        """Drop every cached recommendation."""
        self._cache.clear()
