"""Unit tests — Narrative engine."""
import pytest
from datetime import datetime, timezone


class TestNarrativeEngine:

    def test_template_anomaly_narrative(self):
        from ml.narrative import NarrativeEngine, NarrativeRequest
        engine = NarrativeEngine()
        req = NarrativeRequest(
            narrative_type="anomaly",
            facility_id="office",
            device_id="off-hvac-01",
            observed_value=90.0,
            expected_value=45.0,
            anomaly_score=0.87,
        )
        narrative = engine.generate(req)
        assert isinstance(narrative, str)
        assert len(narrative) > 20
        assert "office" in narrative.lower() or "hvac" in narrative.lower() or "demand" in narrative.lower()

    def test_template_peak_narrative(self):
        from ml.narrative import NarrativeEngine, NarrativeRequest
        engine = NarrativeEngine()
        req = NarrativeRequest(
            narrative_type="peak_warning",
            facility_id="warehouse",
            device_id="wh-main-01",
            observed_value=270.0,
            expected_value=200.0,
            peak_threshold_kw=300.0,
            predicted_kw=275.0,
            shed_plan=["HVAC-Zone-A", "EV-Charger"],
        )
        narrative = engine.generate(req)
        assert isinstance(narrative, str)
        assert len(narrative) > 20

    def test_template_optimization_narrative(self):
        from ml.narrative import NarrativeEngine, NarrativeRequest
        engine = NarrativeEngine()
        req = NarrativeRequest(
            narrative_type="optimization",
            facility_id="datacentre",
            device_id="dc-hvac-01",
            observed_value=120.0,
            expected_value=95.0,
            extra_context="Cooling load 26% above benchmark for this time of day.",
        )
        narrative = engine.generate(req)
        assert isinstance(narrative, str)
        assert len(narrative) > 20

    def test_batch_generation(self):
        from ml.narrative import NarrativeEngine, NarrativeRequest
        engine = NarrativeEngine()
        reqs = [
            NarrativeRequest("anomaly", "office", "d1", 90.0, 45.0, 0.8),
            NarrativeRequest("forecast", "warehouse", "d2", 80.0, 80.0),
        ]
        results = engine.generate_batch(reqs)
        assert len(results) == 2
        assert all(isinstance(r, str) and len(r) > 0 for r in results)
