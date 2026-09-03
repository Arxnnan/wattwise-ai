"""Unit tests — ingestion pipeline (MQTT -> ClickHouse), fully mocked I/O."""
from __future__ import annotations
from datetime import datetime, timezone

import pytest

from ingestion.schema import TelemetryReading


def _valid_payload() -> str:
    reading = TelemetryReading(
        facility_id="office",
        device_id="off-main-01",
        device_class="main_meter",
        domain="demand",
        timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        value=42.5,
        unit="kW",
        metadata={},
    )
    return reading.to_mqtt_payload()


@pytest.fixture
def pipeline(mocker):
    mock_ch_client = mocker.MagicMock()
    mock_get_client = mocker.patch(
        "ingestion.pipeline.clickhouse_connect.get_client", return_value=mock_ch_client
    )
    mock_mqtt_client = mocker.MagicMock()
    mocker.patch("ingestion.pipeline.mqtt.Client", return_value=mock_mqtt_client)

    from ingestion.pipeline import IngestionPipeline
    p = IngestionPipeline(batch_size=2)
    p._ch_mock = mock_ch_client  # stash for assertions
    p._mqtt_mock = mock_mqtt_client
    p._get_client_mock = mock_get_client
    return p


class TestIngestionPipelineInit:

    def test_connects_clickhouse_and_mqtt(self, pipeline):
        pipeline._get_client_mock.assert_called_once()
        pipeline._mqtt_mock.connect.assert_called_once()

    def test_subscribes_on_connect(self, pipeline):
        pipeline._on_connect(pipeline._mqtt, None, None, 0, None)
        pipeline._mqtt_mock.subscribe.assert_called_once()
        topic = pipeline._mqtt_mock.subscribe.call_args[0][0]
        assert topic == "wattwise/#"


class TestOnMessage:

    def test_valid_payload_is_buffered(self, pipeline):
        msg = type("Msg", (), {"topic": "wattwise/office/demand", "payload": _valid_payload().encode()})()
        pipeline._on_message(None, None, msg)
        assert len(pipeline._buffer) == 1
        assert pipeline._records_invalid == 0

    def test_invalid_json_is_counted_not_raised(self, pipeline):
        msg = type("Msg", (), {"topic": "wattwise/office/demand", "payload": b"not-json"})()
        pipeline._on_message(None, None, msg)  # must not raise
        assert pipeline._records_invalid == 1
        assert len(pipeline._buffer) == 0

    def test_invalid_domain_is_counted_not_raised(self, pipeline):
        reading = TelemetryReading(
            facility_id="office", device_id="off-main-01", device_class="main_meter",
            domain="bogus_domain", timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            value=1.0, unit="kW", metadata={},
        )
        msg = type("Msg", (), {"topic": "wattwise/office/demand", "payload": reading.to_mqtt_payload().encode()})()
        pipeline._on_message(None, None, msg)
        assert pipeline._records_invalid == 1

    def test_reaching_batch_size_triggers_flush(self, pipeline):
        msg = type("Msg", (), {"topic": "t", "payload": _valid_payload().encode()})()
        pipeline._on_message(None, None, msg)
        pipeline._on_message(None, None, msg)  # batch_size=2
        pipeline._ch_mock.insert.assert_called_once()
        assert pipeline._records_written == 2
        assert len(pipeline._buffer) == 0


class TestFlush:

    def test_flush_writes_expected_columns(self, pipeline):
        msg = type("Msg", (), {"topic": "t", "payload": _valid_payload().encode()})()
        pipeline._on_message(None, None, msg)
        pipeline._flush()
        args, kwargs = pipeline._ch_mock.insert.call_args
        assert args[0] == "telemetry"
        assert kwargs["column_names"] == [
            "facility_id", "device_id", "device_class", "domain", "ts", "value", "unit", "metadata",
        ]
        assert len(args[1]) == 1

    def test_empty_buffer_is_a_noop(self, pipeline):
        pipeline._flush()
        pipeline._ch_mock.insert.assert_not_called()


class TestStats:

    def test_stats_reflects_written_and_invalid(self, pipeline):
        valid_msg = type("Msg", (), {"topic": "t", "payload": _valid_payload().encode()})()
        invalid_msg = type("Msg", (), {"topic": "t", "payload": b"garbage"})()
        pipeline._on_message(None, None, valid_msg)
        pipeline._on_message(None, None, invalid_msg)
        pipeline._flush()
        stats = pipeline.stats
        assert stats["records_written"] == 1
        assert stats["records_invalid"] == 1
        assert stats["buffer_size"] == 0
