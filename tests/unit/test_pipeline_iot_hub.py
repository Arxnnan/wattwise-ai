"""Unit tests — ingestion/pipeline_iot_hub.py (Event Hub-compatible read side).

`_process_event`/`_flush`/`_on_event_batch` are pure logic tested directly;
`run_forever()`'s EventHubConsumerClient wiring is not (no real IoT Hub to
connect to yet — see the module docstring).
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest

from ingestion.schema import TelemetryReading


def _valid_payload_bytes() -> bytes:
    reading = TelemetryReading(
        facility_id="office", device_id="off-main-01", device_class="main_meter",
        domain="demand", timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        value=42.5, unit="kW", metadata={},
    )
    return reading.to_mqtt_payload().encode("utf-8")


@pytest.fixture
def consumer(mocker):
    mock_ch_client = mocker.MagicMock()
    mocker.patch("ingestion.pipeline_iot_hub.clickhouse_connect.get_client", return_value=mock_ch_client)

    from ingestion.pipeline_iot_hub import IotHubEventHubConsumer
    c = IotHubEventHubConsumer(eventhub_connection_string="fake", batch_size=2)
    c._ch_mock = mock_ch_client
    return c


class TestProcessEvent:

    def test_valid_event_is_buffered(self, consumer):
        consumer._process_event(_valid_payload_bytes())
        assert len(consumer._buffer) == 1
        assert consumer._records_invalid == 0

    def test_invalid_event_is_counted_not_raised(self, consumer):
        consumer._process_event(b"not json")
        assert consumer._records_invalid == 1
        assert len(consumer._buffer) == 0

    def test_batch_size_triggers_flush(self, consumer):
        consumer._process_event(_valid_payload_bytes())
        consumer._process_event(_valid_payload_bytes())  # batch_size=2
        consumer._ch_mock.insert.assert_called_once()
        assert consumer._records_written == 2
        assert len(consumer._buffer) == 0


class TestFlush:

    def test_writes_expected_columns(self, consumer):
        consumer._process_event(_valid_payload_bytes())
        consumer._flush()
        args, kwargs = consumer._ch_mock.insert.call_args
        assert args[0] == "telemetry"
        assert kwargs["column_names"] == [
            "facility_id", "device_id", "device_class", "domain", "ts", "value", "unit", "metadata",
        ]

    def test_empty_buffer_is_noop(self, consumer):
        consumer._flush()
        consumer._ch_mock.insert.assert_not_called()


class TestOnEventBatch:

    def test_processes_events_and_checkpoints(self, consumer, mocker):
        fake_event = mocker.MagicMock()
        fake_event.body = [_valid_payload_bytes()]
        fake_partition_context = mocker.MagicMock()

        consumer._on_event_batch(fake_partition_context, [fake_event, fake_event])

        assert consumer._records_written == 2
        fake_partition_context.update_checkpoint.assert_called_once()


class TestStats:

    def test_stats_reflects_state(self, consumer):
        consumer._process_event(_valid_payload_bytes())
        consumer._process_event(b"garbage")
        consumer._flush()
        assert consumer.stats == {"records_written": 1, "records_invalid": 1, "buffer_size": 0}
