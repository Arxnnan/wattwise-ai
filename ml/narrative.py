"""WattWise AI — AI Narrative Generation (Gemini 2.5 Flash).

Converts ML outputs (anomaly events, forecasts, peak warnings, optimization
recommendations) into plain-English narratives for the dashboard.

Priority:
  1. Google Gemini 2.5 Flash (free tier)
  2. Hugging Face Inference API (cloud fallback, 1K req/day)
  3. Rule-based template (offline fallback)
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

log = logging.getLogger(__name__)

NarrativeType = Literal["anomaly", "peak_warning", "forecast", "optimization"]


@dataclass
class NarrativeRequest:
    narrative_type: NarrativeType
    facility_id: str
    device_id: str
    observed_value: float
    expected_value: float
    anomaly_score: float = 0.0
    peak_threshold_kw: float = 0.0
    predicted_kw: float = 0.0
    shed_plan: list = None
    extra_context: str = ""


def _build_prompt(req: NarrativeRequest) -> str:
    pct_diff = ((req.observed_value - req.expected_value) /
                (req.expected_value + 1e-6) * 100)

    if req.narrative_type == "anomaly":
        return (
            f"You are an energy management AI assistant. Write a 2-3 sentence "
            f"plain-English alert for an energy operations team.\n\n"
            f"Facility: {req.facility_id} | Device: {req.device_id}\n"
            f"Observed demand: {req.observed_value:.1f} kW | "
            f"Expected: {req.expected_value:.1f} kW | "
            f"Deviation: {pct_diff:+.1f}%\n"
            f"Anomaly score: {req.anomaly_score:.3f}\n\n"
            f"Include: what is happening, likely cause, and recommended action. "
            f"Be specific and actionable. No markdown."
        )
    elif req.narrative_type == "peak_warning":
        return (
            f"You are an energy management AI assistant. Write a 2-3 sentence "
            f"peak demand warning for an energy operations team.\n\n"
            f"Facility: {req.facility_id}\n"
            f"Predicted demand: {req.predicted_kw:.1f} kW | "
            f"Peak threshold: {req.peak_threshold_kw:.1f} kW | "
            f"Utilisation: {req.predicted_kw/req.peak_threshold_kw*100:.1f}%\n"
            f"Loads to shed: {req.shed_plan}\n\n"
            f"Include: urgency, which loads to defer first, expected savings. "
            f"Be specific. No markdown."
        )
    elif req.narrative_type == "optimization":
        return (
            f"You are an energy management AI assistant. Write a 2-3 sentence "
            f"optimization recommendation for an energy manager.\n\n"
            f"Facility: {req.facility_id}\n"
            f"Current demand: {req.observed_value:.1f} kW | "
            f"Benchmark: {req.expected_value:.1f} kW\n"
            f"Context: {req.extra_context}\n\n"
            f"Include: what to optimize, expected savings, priority. "
            f"Be specific and actionable. No markdown."
        )
    else:
        return (
            f"Summarize this energy forecast in 2 sentences for an ops team. "
            f"Facility: {req.facility_id}. "
            f"24h peak forecast: {req.predicted_kw:.1f} kW."
        )


def _gemini_narrative(prompt: str) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        log.warning("Gemini failed: %s", e)
        return None


def _huggingface_narrative(prompt: str) -> str | None:
    token = os.getenv("HUGGINGFACE_API_TOKEN", "")
    if not token:
        return None
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=token)
        result = client.text_generation(
            prompt,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_new_tokens=150,
        )
        return result.strip()
    except Exception as e:
        log.warning("HuggingFace API failed: %s", e)
        return None


def _template_narrative(req: NarrativeRequest) -> str:
    pct_diff = ((req.observed_value - req.expected_value) /
                (req.expected_value + 1e-6) * 100)

    if req.narrative_type == "anomaly":
        direction = "above" if pct_diff > 0 else "below"
        return (
            f"{req.facility_id.title()} facility — {req.device_id} is drawing "
            f"{abs(pct_diff):.1f}% {direction} expected demand "
            f"({req.observed_value:.1f} kW vs {req.expected_value:.1f} kW expected). "
            f"Anomaly score: {req.anomaly_score:.3f}. "
            f"Recommended action: inspect device for faults, check setpoint configuration, "
            f"or verify sensor calibration."
        )
    elif req.narrative_type == "peak_warning":
        util = req.predicted_kw / (req.peak_threshold_kw + 1e-6) * 100
        return (
            f"PEAK WARNING — {req.facility_id.title()}: predicted demand "
            f"{req.predicted_kw:.1f} kW ({util:.1f}% of {req.peak_threshold_kw:.0f} kW threshold). "
            f"Immediate action: defer non-critical loads. "
            f"Recommended shed sequence: {req.shed_plan}."
        )
    elif req.narrative_type == "optimization":
        return (
            f"Optimization opportunity at {req.facility_id.title()}: "
            f"current demand {req.observed_value:.1f} kW vs benchmark {req.expected_value:.1f} kW. "
            f"Potential saving: {max(0, req.observed_value - req.expected_value):.1f} kW. "
            f"{req.extra_context}"
        )
    else:
        return (
            f"24h demand forecast for {req.facility_id.title()}: "
            f"peak predicted at {req.predicted_kw:.1f} kW."
        )


class NarrativeEngine:
    """Generates plain-English energy insights using Gemini → HF → template fallback."""

    def generate(self, req: NarrativeRequest) -> str:
        prompt = _build_prompt(req)

        # Try Gemini first
        narrative = _gemini_narrative(prompt)
        if narrative:
            log.info("Narrative from: Gemini 2.5 Flash")
            return narrative

        # Try HuggingFace
        narrative = _huggingface_narrative(prompt)
        if narrative:
            log.info("Narrative from: HuggingFace Inference API")
            return narrative

        # Rule-based template fallback
        log.info("Narrative from: template fallback")
        return _template_narrative(req)

    def generate_batch(self, requests: list[NarrativeRequest]) -> list[str]:
        return [self.generate(req) for req in requests]
