"""WattWise AI — integration tests for ingestion -> analytics pipeline.

End-to-end integration coverage proving data flows cleanly through
simulator.generate_readings -> TelemetryReading.from_mqtt_payload ->
IngestionPipeline._on_message -> ClickHouse insert, with the IoT Hub
Event Hubs consumer path exercised against the same payload format.

Zero network / broker / ClickHouse: paho.mqtt.client.Client and
clickhouse_connect.get_client are mocked at module scope.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ingestion.schema import TelemetryReading, DOMAIN_UNITS
from ingestion.simulator import (
    FACILITIES,
    MQTT_TOPIC_TEMPLATE,
    generate_readings,
)


# ---------- helpers --------------------------------------------------------


def _fake_msg(topic: str, payload: bytes) -> SimpleNamespace:
    """Mimic the paho.mqtt.client.MQTTMessage attributes used by on_message."""
    return SimpleNamespace(topic=topic, payload=payload)


def _msg_from_reading(reading: TelemetryReading) -> SimpleNamespace:
    topic = MQTT_TOPIC_TEMPLATE.format(
        facility_id=reading.facility_id,
        device_id=reading.device_id,
        domain=reading.domain,
    )
    return _fake_msg(topic, reading.to_mqtt_payload().encode("utf-8"))


# ---------- fixtures -------------------------------------------------------


@pytest.fixture
def pipeline():
    """IngestionPipeline with paho + clickhouse_connect mocked out."""
    from ingestion import pipeline as pipeline_mod

    with patch.object(pipeline_mod, "clickhouse_connect") as mock_ch_mod, \
         patch.object(pipeline_mod.mqtt, "Client") as mock_mqtt_cls:
        mock_ch_client = MagicMock()
        mock_ch_mod.get_client.return_value = mock_ch_client

        mock_mqtt_client = MagicMock()
        mock_mqtt_cls.return_value = mock_mqtt_client

        pl = pipeline_mod.IngestionPipeline(batch_size=5)
        pl._mock_ch = mock_ch_client  # expose for assertions
        pl._mock_mqtt = mock_mqtt_client
        yield pl


@pytest.fixture
def iot_hub_consumer():
    """IotHubEventHubConsumer with clickhouse_connect mocked."""
    from ingestion import pipeline_iot_hub as iot_mod

    with patch.object(iot_mod, "clickhouse_connect") as mock_ch_mod:
        mock_ch_client = MagicMock()
        mock_ch_mod.get_client.return_value = mock_ch_client

        consumer = iot_mod.IotHubEventHubConsumer(
            eventhub_connection_string="Endpoint=sb://fake.servicebus.windows.net/;SharedAccessKeyName=x;SharedAccessKey=y;EntityPath=z",
            batch_size=5,
        )
        consumer._mock_ch = mock_ch_client
        yield consumer


# ---------- 1. simulator <-> schema round-trip ----------------------------


def test_simulator_output_passes_schema_validation():
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    readings = list(generate_readings(now))

    # 3 facilities x 6 device classes x 3 domains = 54 readings per cycle.
    assert len(readings) == 3 * 6 * 3 == 54

    facilities, device_classes, domains = set(), set(), set()
    for r in readings:
        # Round-trip through the wire format exactly as MQTT would carry it.
        parsed = TelemetryReading.from_mqtt_payload(r.to_mqtt_payload())
        assert parsed.validate() is True
        assert parsed.unit == DOMAIN_UNITS[parsed.domain]
        facilities.add(parsed.facility_id)
        device_classes.add(parsed.device_class)
        domains.add(parsed.domain)

    assert facilities == {"office", "warehouse", "datacentre"}
    assert device_classes == {
        "main_meter", "sub_meter", "hvac", "lighting", "occupancy", "weather",
    }
    assert domains == {"consumption", "demand", "cost"}


# ---------- 2. MQTT publish -> subscribe chain ----------------------------


def test_on_message_populates_buffer(pipeline):
    reading = next(generate_readings(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)))
    msg = _msg_from_reading(reading)

    pipeline._on_message(pipeline._mock_mqtt, None, msg)

    assert len(pipeline._buffer) == 1
    buffered = pipeline._buffer[0]
    assert buffered.facility_id == reading.facility_id
    assert buffered.device_id == reading.device_id
    assert buffered.domain == reading.domain
    assert pipeline._mock_ch.insert.call_count == 0  # not yet flushed


# ---------- 3. batch flush to ClickHouse ----------------------------------


def test_flush_calls_clickhouse_insert_with_correct_shape(pipeline):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    gen = generate_readings(now)
    for _ in range(pipeline.batch_size):
        pipeline._on_message(pipeline._mock_mqtt, None, _msg_from_reading(next(gen)))

    assert pipeline._mock_ch.insert.call_count == 1
    args, kwargs = pipeline._mock_ch.insert.call_args
    assert args[0] == "telemetry"
    rows = args[1]
    assert len(rows) == pipeline.batch_size
    assert kwargs["column_names"] == [
        "facility_id", "device_id", "device_class", "domain",
        "ts", "value", "unit", "metadata",
    ]
    # Each row is a positional list in column order.
    for row in rows:
        assert len(row) == 8
        assert isinstance(row[4], datetime)  # ts
        assert isinstance(row[5], float)     # value
        assert isinstance(row[7], str)       # metadata serialized as JSON string
        json.loads(row[7])                   # must be valid JSON


# ---------- 4. buffer discipline (BUFFER_SIZE+1) --------------------------


def test_buffer_flushes_exactly_once_then_resets(pipeline):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    gen = generate_readings(now)
    for _ in range(pipeline.batch_size + 1):
        pipeline._on_message(pipeline._mock_mqtt, None, _msg_from_reading(next(gen)))

    assert pipeline._mock_ch.insert.call_count == 1
    assert len(pipeline._buffer) == 1  # the +1 message is still buffered
    assert pipeline._records_written == pipeline.batch_size


# ---------- 5. validation rejection ---------------------------------------


def test_invalid_message_is_rejected_and_not_inserted(pipeline):
    bad = TelemetryReading(
        facility_id="office",
        device_id="off-main-01",
        device_class="main_meter",
        domain="demand",         # expects kW
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        value=10.0,
        unit="kWh",              # WRONG unit for domain=demand
        metadata={},
    )
    pipeline._on_message(pipeline._mock_mqtt, None, _msg_from_reading(bad))

    assert pipeline._records_invalid == 1
    assert len(pipeline._buffer) == 0
    assert pipeline._mock_ch.insert.call_count == 0


# ---------- 6. multi-facility fan-in --------------------------------------


def test_multi_facility_fan_in_reaches_clickhouse(pipeline):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    # Grab exactly one 'demand' reading from each facility and interleave.
    picks: dict[str, TelemetryReading] = {}
    for r in generate_readings(now):
        if r.domain == "demand" and r.facility_id not in picks:
            picks[r.facility_id] = r
        if len(picks) == 3:
            break
    assert set(picks.keys()) == {"office", "warehouse", "datacentre"}

    pipeline.batch_size = 3  # force a flush after exactly 3 messages
    for facility_id in ("office", "datacentre", "warehouse"):
        pipeline._on_message(
            pipeline._mock_mqtt, None, _msg_from_reading(picks[facility_id])
        )

    assert pipeline._mock_ch.insert.call_count == 1
    rows = pipeline._mock_ch.insert.call_args.args[1]
    facilities_in_rows = {row[0] for row in rows}
    assert facilities_in_rows == {"office", "warehouse", "datacentre"}


# ---------- 7. topic parsing (publish side) -------------------------------


def test_topic_routing_matches_payload_fields():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    for r in generate_readings(now):
        topic = MQTT_TOPIC_TEMPLATE.format(
            facility_id=r.facility_id, device_id=r.device_id, domain=r.domain,
        )
        prefix, facility, device, domain = topic.split("/")
        assert prefix == "wattwise"
        assert facility == r.facility_id
        assert device == r.device_id
        assert domain == r.domain

        # Round-trip and confirm the subscriber would see the same identifiers.
        parsed = TelemetryReading.from_mqtt_payload(r.to_mqtt_payload())
        assert parsed.facility_id == facility
        assert parsed.device_id == device
        assert parsed.domain == domain


# ---------- 8. timezone correctness ---------------------------------------


def test_all_stored_rows_have_utc_timestamps(pipeline):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    gen = generate_readings(now)
    for _ in range(pipeline.batch_size):
        pipeline._on_message(pipeline._mock_mqtt, None, _msg_from_reading(next(gen)))

    rows = pipeline._mock_ch.insert.call_args.args[1]
    for row in rows:
        ts = row[4]
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None, "timestamp must be timezone-aware (not naive)"
        assert ts.utcoffset() == (now - now).__class__(0), "timestamp must be UTC"


# ---------- 9. TelemetryReading serialization round-trip ------------------


def test_telemetry_reading_json_round_trip():
    original = TelemetryReading(
        facility_id="warehouse",
        device_id="wh-hvac-01",
        device_class="hvac",
        domain="consumption",
        timestamp=datetime(2026, 2, 10, 9, 30, 15, tzinfo=timezone.utc),
        value=12.34567,
        unit="kWh",
        metadata={"interval_minutes": 5, "nested": {"ok": True}},
    )

    payload = original.to_mqtt_payload()
    assert isinstance(payload, str)
    # Payload is valid JSON.
    raw = json.loads(payload)
    assert isinstance(raw["metadata"], str)  # metadata is JSON-encoded inside

    parsed = TelemetryReading.from_mqtt_payload(payload)
    assert parsed.facility_id == original.facility_id
    assert parsed.device_id == original.device_id
    assert parsed.device_class == original.device_class
    assert parsed.domain == original.domain
    assert parsed.value == original.value
    assert parsed.unit == original.unit
    assert parsed.timestamp == original.timestamp
    assert parsed.timestamp.tzinfo is not None
    assert parsed.metadata == original.metadata
    assert parsed.validate() is True


# ---------- 10. IoT Hub consumer path -------------------------------------


def test_iot_hub_consumer_produces_same_row_shape(iot_hub_consumer):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    readings = []
    gen = generate_readings(now)
    for _ in range(iot_hub_consumer.batch_size):
        readings.append(next(gen))

    # Mock EventData objects: azure-eventhub events expose `.body` as an
    # iterable of bytes chunks. _on_event_batch does b"".join(event.body).
    class _FakeEvent:
        def __init__(self, body: bytes):
            self.body = [body]

    events = [_FakeEvent(r.to_mqtt_payload().encode("utf-8")) for r in readings]
    partition_ctx = MagicMock()

    iot_hub_consumer._on_event_batch(partition_ctx, events)

    assert iot_hub_consumer._mock_ch.insert.call_count == 1
    args, kwargs = iot_hub_consumer._mock_ch.insert.call_args
    assert args[0] == "telemetry"
    rows = args[1]
    assert len(rows) == iot_hub_consumer.batch_size
    assert kwargs["column_names"] == [
        "facility_id", "device_id", "device_class", "domain",
        "ts", "value", "unit", "metadata",
    ]
    # Row shape matches the MQTT pipeline's shape exactly.
    for row, source in zip(rows, readings):
        assert row[0] == source.facility_id
        assert row[1] == source.device_id
        assert row[2] == source.device_class
        assert row[3] == source.domain
        assert isinstance(row[4], datetime) and row[4].tzinfo is not None
        assert row[5] == source.value
        assert row[6] == source.unit
        assert json.loads(row[7]) == source.metadata

    partition_ctx.update_checkpoint.assert_called_once()


def test_iot_hub_consumer_rejects_invalid_event(iot_hub_consumer):
    bad_payload = json.dumps({
        "facility_id": "office",
        "device_id": "off-main-01",
        "device_class": "main_meter",
        "domain": "demand",
        "timestamp": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        "value": 5.0,
        "unit": "kWh",  # wrong unit for demand
        "metadata": json.dumps({}),
    }).encode("utf-8")

    iot_hub_consumer._process_event(bad_payload)
    assert iot_hub_consumer._records_invalid == 1
    assert len(iot_hub_consumer._buffer) == 0
    assert iot_hub_consumer._mock_ch.insert.call_count == 0
