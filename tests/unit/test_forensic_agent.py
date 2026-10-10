"""Unit tests for ml.agents.forensic_agent — 100% coverage, zero real LLM calls."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ml.agents.forensic_agent import ForensicAgent, ForensicCard
from ml.agents.llm_provider import NullProvider


# ───────────────────────────── Fixtures ─────────────────────────────

@pytest.fixture
def mock_llm():
    m = MagicMock()
    m.is_available.return_value = True
    m.generate.return_value = "Likely stuck compressor contactor caused by weld fault."
    return m


@pytest.fixture
def agent(mock_llm):
    return ForensicAgent(llm_provider=mock_llm)


@pytest.fixture
def ts():
    return datetime(2026, 1, 15, 10, 30, 0)


@pytest.fixture
def pyod_scores():
    return {"iforest": 0.89, "copod": 0.91, "ecod": 0.94}


@pytest.fixture
def historical_df():
    return pd.DataFrame([
        {"id": "A1", "device_id": "compressor-2", "observed_value": 100.0,
         "date": "2025-12-01", "resolution": "Replaced contactor", "resolved_by": "tech1"},
        {"id": "A2", "device_id": "compressor-2", "observed_value": 102.0,
         "date": "2025-12-10", "resolution": "Reset breaker", "resolved_by": "tech2"},
        {"id": "A3", "device_id": "compressor-2", "observed_value": 50.0,
         "date": "2025-11-05", "resolution": "Replaced sensor", "resolved_by": "tech3"},
        {"id": "A4", "device_id": "compressor-2", "observed_value": 110.0,
         "date": "2025-10-15", "resolution": "Cleaned condenser", "resolved_by": "tech1"},
        {"id": "B1", "device_id": "pump-1", "observed_value": 300.0,
         "date": "2025-12-20", "resolution": "Replaced impeller", "resolved_by": "tech4"},
    ])


# ───────────────────────── Construction ─────────────────────────

class TestInit:
    def test_default_init_uses_get_llm_provider(self):
        with patch("ml.agents.llm_provider.get_llm_provider") as mock_get:
            mock_get.return_value = MagicMock()
            agent = ForensicAgent()
            mock_get.assert_called_once()
            assert agent._provider is mock_get.return_value

    def test_explicit_provider_overrides_default(self, mock_llm):
        agent = ForensicAgent(llm_provider=mock_llm)
        assert agent._provider is mock_llm


# ───────────────────────── forensic() end-to-end ─────────────────────────

class TestForensicEntry:
    def test_returns_complete_forensic_card(self, agent, ts, pyod_scores, historical_df):
        card = agent.forensic(
            anomaly_id="ANOM-001",
            anomaly_timestamp=ts,
            facility_id="HQ-1",
            device_id="compressor-2",
            observed_value=103.0,
            expected_value=80.0,
            pyod_scores=pyod_scores,
            historical_anomalies=historical_df,
            severity="major",
        )
        assert isinstance(card, ForensicCard)
        assert card.anomaly_id == "ANOM-001"
        assert card.anomaly_timestamp == ts
        assert card.facility_id == "HQ-1"
        assert card.device_id == "compressor-2"
        assert card.observed_value == 103.0
        assert card.expected_value == 80.0
        assert card.why_flagged
        assert card.hypothesis
        assert card.recommended_action
        assert card.confidence_note
        assert card.similar_past_events
        assert card.repeat_count_90d == len(card.similar_past_events)
        assert card.work_order_draft
        assert card.severity == "major"
        assert card.llm_source == "llm"
        assert isinstance(card.generated_at, datetime)

    def test_anomaly_id_passthrough(self, agent, ts, pyod_scores):
        card = agent.forensic(
            anomaly_id="UNIQUE-XYZ-42",
            anomaly_timestamp=ts,
            facility_id="F1",
            device_id="hvac-rtu-3",
            observed_value=10.0,
            expected_value=5.0,
            pyod_scores=pyod_scores,
        )
        assert card.anomaly_id == "UNIQUE-XYZ-42"

    def test_severity_threading(self, agent, ts, pyod_scores):
        for sev in ("critical", "major", "minor"):
            card = agent.forensic(
                anomaly_id="A",
                anomaly_timestamp=ts,
                facility_id="F",
                device_id="hvac-1",
                observed_value=1.0,
                expected_value=0.5,
                pyod_scores=pyod_scores,
                severity=sev,
            )
            assert card.severity == sev

    def test_generated_at_is_utc(self, agent, ts, pyod_scores):
        before = datetime.utcnow()
        card = agent.forensic(
            anomaly_id="A",
            anomaly_timestamp=ts,
            facility_id="F",
            device_id="hvac-1",
            observed_value=1.0,
            expected_value=0.5,
            pyod_scores=pyod_scores,
        )
        after = datetime.utcnow()
        assert before <= card.generated_at <= after
        # Naive datetime equals UTC-based utcnow()
        assert card.generated_at.tzinfo is None

    def test_null_provider_falls_back_to_template(self, ts, pyod_scores):
        agent = ForensicAgent(llm_provider=NullProvider())
        card = agent.forensic(
            anomaly_id="A",
            anomaly_timestamp=ts,
            facility_id="F",
            device_id="compressor-1",
            observed_value=100.0,
            expected_value=70.0,
            pyod_scores=pyod_scores,
        )
        assert card.llm_source == "template"
        assert "compressor" in card.hypothesis.lower()

    def test_llm_failure_falls_back_to_template(self, ts, pyod_scores):
        bad_llm = MagicMock()
        bad_llm.is_available.return_value = True
        bad_llm.generate.side_effect = RuntimeError("API down")
        agent = ForensicAgent(llm_provider=bad_llm)
        card = agent.forensic(
            anomaly_id="A",
            anomaly_timestamp=ts,
            facility_id="F",
            device_id="hvac-rtu-1",
            observed_value=10.0,
            expected_value=5.0,
            pyod_scores=pyod_scores,
        )
        assert card.llm_source == "template"
        assert "hvac" in card.hypothesis.lower()


# ───────────────────────── _why_flagged ─────────────────────────

class TestWhyFlagged:
    def test_formats_scores(self, agent):
        out = agent._why_flagged({"iforest": 0.89, "copod": 0.91, "ecod": 0.94})
        assert "IFOREST 0.89" in out
        assert "COPOD 0.91" in out
        assert "ECOD 0.94" in out
        assert "0.94" in out  # peak score

    def test_empty_scores_gives_generic_message(self, agent):
        out = agent._why_flagged({})
        assert "no detailed scores" in out.lower()


# ───────────────────────── _find_similar_past ─────────────────────────

class TestFindSimilarPast:
    def test_empty_historical_returns_empty(self, agent):
        assert agent._find_similar_past("dev", 10.0, None) == []
        assert agent._find_similar_past("dev", 10.0, pd.DataFrame()) == []

    def test_top_3_by_similarity(self, agent, historical_df):
        results = agent._find_similar_past("compressor-2", 103.0, historical_df)
        assert len(results) == 3
        # Closest to 103.0 are 102 (dist 1), 100 (dist 3), 110 (dist 7); 50 excluded
        ids = [r["id"] for r in results]
        assert ids == ["A2", "A1", "A4"]
        assert results[0]["resolution"] == "Reset breaker"
        assert results[0]["resolved_by"] == "tech2"
        assert results[0]["date"] == "2025-12-10"

    def test_no_matching_device_returns_empty(self, agent, historical_df):
        results = agent._find_similar_past("ghost-device", 100.0, historical_df)
        assert results == []

    def test_dataframe_without_device_column(self, agent):
        df = pd.DataFrame([
            {"id": "X1", "observed_value": 10.0, "date": "d", "resolution": "r", "resolved_by": "b"},
            {"id": "X2", "observed_value": 11.0, "date": "d2", "resolution": "r2", "resolved_by": "b2"},
        ])
        results = agent._find_similar_past("any", 10.5, df)
        assert len(results) == 2

    def test_dataframe_without_value_column(self, agent):
        df = pd.DataFrame([
            {"id": "X1", "device_id": "d", "date": "d", "resolution": "r", "resolved_by": "b"},
            {"id": "X2", "device_id": "d", "date": "d2", "resolution": "r2", "resolved_by": "b2"},
        ])
        results = agent._find_similar_past("d", 5.0, df)
        assert len(results) == 2

    def test_10_events_returns_top_3(self, agent):
        rows = [
            {"id": f"E{i}", "device_id": "pump-1", "observed_value": float(i),
             "date": f"2025-01-{i:02d}", "resolution": "fix", "resolved_by": "x"}
            for i in range(1, 11)
        ]
        df = pd.DataFrame(rows)
        results = agent._find_similar_past("pump-1", 5.0, df)
        assert len(results) == 3
        # closest to 5.0: 5 (0), 4 or 6 (1)
        assert results[0]["id"] == "E5"


# ───────────────────────── _hypothesis_llm ─────────────────────────

class TestHypothesisLLM:
    def test_success_returns_llm_text(self, agent, mock_llm):
        mock_llm.generate.return_value = "  Compressor seized due to overload.  "
        text = agent._hypothesis_llm("compressor-2", 100.0, 80.0, [
            {"date": "2025-01-01", "resolution": "replaced motor"},
        ])
        assert text == "Compressor seized due to overload."
        mock_llm.generate.assert_called_once()
        prompt = mock_llm.generate.call_args.args[0]
        assert "compressor-2" in prompt
        assert "100" in prompt
        assert "replaced motor" in prompt

    def test_handles_no_past_events(self, agent, mock_llm):
        mock_llm.generate.return_value = "Possible drift"
        text = agent._hypothesis_llm("hvac-1", 1.0, 0.5, [])
        assert text == "Possible drift"
        prompt = mock_llm.generate.call_args.args[0]
        assert "no similar past incidents" in prompt

    def test_handles_none_response(self, agent, mock_llm):
        mock_llm.generate.return_value = None
        text = agent._hypothesis_llm("x", 1.0, 0.5, [])
        assert text == ""


# ───────────────────────── _hypothesis_template ─────────────────────────

class TestHypothesisTemplate:
    def test_hvac_device(self, agent):
        out = agent._hypothesis_template("hvac-rtu-3", 100.0, 50.0)
        assert "HVAC" in out or "hvac" in out.lower()
        assert "50.00" in out
        assert "above" in out

    def test_compressor_device(self, agent):
        out = agent._hypothesis_template("compressor-2", 60.0, 80.0)
        assert "compressor" in out.lower()
        assert "below" in out

    def test_pump_device(self, agent):
        out = agent._hypothesis_template("pump-1", 300.0, 250.0)
        assert "pump" in out.lower() or "cavitation" in out.lower()

    def test_chiller_device(self, agent):
        out = agent._hypothesis_template("chiller-main", 500.0, 400.0)
        assert "chiller" in out.lower() or "condenser" in out.lower()

    def test_generic_device(self, agent):
        out = agent._hypothesis_template("meter-7", 10.0, 5.0)
        assert "sensor drift" in out.lower() or "equipment fault" in out.lower()

    def test_empty_device_id(self, agent):
        out = agent._hypothesis_template("", 10.0, 5.0)
        assert out  # does not crash


# ───────────────────────── _recommended_action ─────────────────────────

class TestRecommendedAction:
    def test_hvac_dispatches_hvac_technician(self, agent):
        out = agent._recommended_action("some hypothesis", "hvac-1")
        assert "HVAC technician" in out
        assert "hvac-1" in out
        assert "some hypothesis" in out

    def test_compressor_dispatches_hvac(self, agent):
        out = agent._recommended_action("h", "compressor-2")
        assert "HVAC technician" in out

    def test_chiller_dispatches_hvac(self, agent):
        out = agent._recommended_action("h", "chiller-main")
        assert "HVAC technician" in out

    def test_pump_dispatches_mechanical(self, agent):
        out = agent._recommended_action("h", "pump-1")
        assert "mechanical" in out.lower()

    def test_generic_dispatches_facilities(self, agent):
        out = agent._recommended_action("h", "meter-7")
        assert "facilities" in out.lower()


# ───────────────────────── _confidence_note ─────────────────────────

class TestConfidenceNote:
    def test_zero_events_is_low(self, agent):
        out = agent._confidence_note([])
        assert "Low confidence" in out

    def test_one_event_is_medium(self, agent):
        out = agent._confidence_note([{"resolution": "fix"}])
        assert "Medium confidence" in out
        assert "1 of 1" in out

    def test_two_events_is_medium(self, agent):
        out = agent._confidence_note([
            {"resolution": "fix"}, {"resolution": ""},
        ])
        assert "Medium confidence" in out
        assert "1 of 2" in out

    def test_three_events_is_high(self, agent):
        out = agent._confidence_note([
            {"resolution": "a"}, {"resolution": "b"}, {"resolution": "c"},
        ])
        assert "High confidence" in out
        assert "3 of 3" in out

    def test_four_events_is_high(self, agent):
        out = agent._confidence_note([
            {"resolution": "a"}, {"resolution": "b"},
            {"resolution": "c"}, {"resolution": ""},
        ])
        assert "High confidence" in out
        assert "3 of 4" in out


# ───────────────────────── _work_order_draft ─────────────────────────

class TestWorkOrderDraft:
    def _make_card(self, severity="minor", ts=None):
        return ForensicCard(
            anomaly_id="ANOM-9",
            anomaly_timestamp=ts or datetime(2026, 2, 1, 9, 0, 0),
            facility_id="BLDG-A",
            device_id="hvac-2",
            observed_value=42.5,
            expected_value=30.0,
            why_flagged="PyOD triggered",
            hypothesis="setpoint drift",
            recommended_action="Dispatch HVAC tech",
            confidence_note="Medium confidence",
            severity=severity,
        )

    def test_contains_all_servicenow_fields(self, agent):
        card = self._make_card()
        out = agent._work_order_draft(card)
        for field in (
            "Title:", "Facility:", "Device:", "Timestamp:",
            "Observed signature:", "Why flagged:", "Hypothesis:",
            "Suggested fix:", "Confidence:", "Priority:",
        ):
            assert field in out
        assert "ANOM-9" in out
        assert "hvac-2" in out
        assert "BLDG-A" in out
        assert "42.50" in out
        assert "30.00" in out

    def test_priority_mapping(self, agent):
        assert "P1" in agent._work_order_draft(self._make_card(severity="critical"))
        assert "P2" in agent._work_order_draft(self._make_card(severity="major"))
        assert "P3" in agent._work_order_draft(self._make_card(severity="minor"))

    def test_priority_default_for_unknown_severity(self, agent):
        card = self._make_card()
        card.severity = "weird"  # type: ignore[assignment]
        assert "P3" in agent._work_order_draft(card)

    def test_handles_non_datetime_timestamp(self, agent):
        card = self._make_card()
        card.anomaly_timestamp = "2026-02-01T09:00:00"  # type: ignore[assignment]
        out = agent._work_order_draft(card)
        assert "2026-02-01T09:00:00" in out


# ───────────────────────── Dataclass default ─────────────────────────

class TestForensicCardDataclass:
    def test_defaults(self):
        card = ForensicCard(
            anomaly_id="A",
            anomaly_timestamp=datetime(2026, 1, 1),
            facility_id="F",
            device_id="D",
            observed_value=1.0,
            expected_value=0.5,
        )
        assert card.similar_past_events == []
        assert card.repeat_count_90d == 0
        assert card.work_order_draft == ""
        assert card.severity == "minor"
        assert card.llm_source == "template"
        assert isinstance(card.generated_at, datetime)
