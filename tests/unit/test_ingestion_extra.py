"""Additional unit tests boosting coverage for the ingestion/ package.

Covers branches not exercised by the per-module tests:
  * schema: unit mismatch, metadata-dict passthrough in from_mqtt_payload
  * simulator: Simulator (ctor/connect/disconnect/publish_once/run_forever),
    off-peak hour factor, occupancy/weather device branch, __main__ block
  * pipeline: run_forever + KeyboardInterrupt, __main__ block
  * pipeline_iot_hub: run_forever + KeyboardInterrupt, __main__ block
  * iot_hub_publisher: disconnect()

All network/transport calls (paho-mqtt, clickhouse_connect, azure.eventhub)
are mocked. No live connections are made.
"""
from __future__ import annotations

import base64
import importlib
import json
import runpy
import sys
from datetime import datetime, timezone

import pytest

from ingestion.schema import TelemetryReading, DOMAIN_UNITS


# ---------------------------------------------------------------------------
# schema.py — extra edge cases
# ---------------------------------------------------------------------------

class TestSchemaExtras:

    def test_unit_mismatch_raises(self):
        r = TelemetryReading(
            facility_id="office", device_id="d1", device_class="main_meter",
            domain="demand",  # expects kW
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            value=1.0, unit="kWh",  # wrong!
            metadata={},
        )
        with pytest.raises(AssertionError, match="Unit mismatch"):
            r.validate()

    def test_from_mqtt_payload_accepts_dict_metadata(self):
        # The branch where metadata is already a dict (not a JSON string).
        payload = json.dumps({
            "facility_id": "office",
            "device_id": "off-main-01",
            "device_class": "main_meter",
            "domain": "demand",
            "timestamp": "2026-01-15T10:00:00+00:00",
            "value": 10.0,
            "unit": "kW",
            "metadata": {"already": "a dict"},
        })
        restored = TelemetryReading.from_mqtt_payload(payload)
        assert restored.metadata == {"already": "a dict"}

    def test_to_dict_serializes_metadata_as_json_string(self, sample_reading):
        d = sample_reading.to_dict()
        # metadata becomes a JSON string on the wire
        assert isinstance(d["metadata"], str)
        assert json.loads(d["metadata"]) == sample_reading.metadata


# ---------------------------------------------------------------------------
# simulator.py — off-peak hour, sensor-class branch, Simulator class
# ---------------------------------------------------------------------------

class TestSimulatorBranches:

    def test_off_peak_hour_vs_peak_hour_office(self):
        """Office peak hours are 8-18; use a device_class with a non-zero
        share so the peak_factor branch (vs the 0.6 off-peak branch) actually
        makes a difference."""
        from ingestion.simulator import generate_readings
        peak = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)      # Wed 12:00
        off_peak = datetime(2026, 1, 14, 3, 0, tzinfo=timezone.utc)   # Wed 03:00
        peak_demand = sum(
            r.value for r in generate_readings(peak)
            if r.facility_id == "office" and r.domain == "demand"
            and r.device_class == "main_meter"
        )
        off_peak_demand = sum(
            r.value for r in generate_readings(off_peak)
            if r.facility_id == "office" and r.domain == "demand"
            and r.device_class == "main_meter"
        )
        # 1.8 (peak) >> 0.6 (off-peak), noise can't flip it on main_meter
        assert peak_demand > off_peak_demand

    def test_sensor_classes_use_passive_power_branch(self):
        """occupancy & weather devices take the special `return` on line ~84
        — power draw must be the small 0.1-0.5 kW range regardless of hour."""
        from ingestion.simulator import generate_readings
        now = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)
        for r in generate_readings(now):
            if r.device_class in ("occupancy", "weather") and r.domain == "demand":
                assert 0.1 <= r.value <= 0.5

    def test_generate_readings_defaults_now_to_utc(self):
        """Covers the `if now is None` branch."""
        from ingestion.simulator import generate_readings
        readings = list(generate_readings())
        assert len(readings) == 54


class TestSimulatorClass:

    @pytest.fixture
    def simulator(self, mocker):
        mock_client = mocker.MagicMock()
        mocker.patch("ingestion.simulator.mqtt.Client", return_value=mock_client)
        from ingestion.simulator import Simulator
        sim = Simulator(broker_host="broker.example.com", broker_port=1884,
                        interval_seconds=1)
        sim._mock_client = mock_client
        return sim

    def test_connect_starts_mqtt_loop(self, simulator):
        simulator.connect()
        simulator._mock_client.connect.assert_called_once_with(
            "broker.example.com", 1884, keepalive=60,
        )
        simulator._mock_client.loop_start.assert_called_once()

    def test_disconnect_stops_mqtt_loop(self, simulator):
        simulator.disconnect()
        simulator._mock_client.loop_stop.assert_called_once()
        simulator._mock_client.disconnect.assert_called_once()

    def test_publish_once_sends_all_readings(self, simulator):
        now = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)
        count = simulator.publish_once(now)
        # 3 facilities * 6 devices * 3 domains
        assert count == 54
        assert simulator._mock_client.publish.call_count == 54
        topic, payload = simulator._mock_client.publish.call_args_list[0][0][:2]
        assert topic.startswith("wattwise/")
        # payload must be a JSON string
        parsed = json.loads(payload)
        assert "value" in parsed

    def test_run_forever_exits_cleanly_on_keyboard_interrupt(self, simulator, mocker):
        """publish_once -> sleep -> KeyboardInterrupt -> disconnect in finally."""
        call_count = {"n": 0}

        def one_cycle_then_stop(*_a, **_kw):
            call_count["n"] += 1
            raise KeyboardInterrupt

        mocker.patch("ingestion.simulator.time.sleep", side_effect=one_cycle_then_stop)
        simulator.run_forever()
        # publish_once ran once, then disconnect was called in finally
        assert call_count["n"] == 1
        simulator._mock_client.loop_stop.assert_called_once()
        simulator._mock_client.disconnect.assert_called_once()


class TestSimulatorMain:

    def test_main_block_wires_env_and_runs(self, mocker, monkeypatch):
        """Exercise the `if __name__ == '__main__'` block (lines 203-210).

        We patch at the paho source module and at ingestion.simulator.time.sleep
        after the fresh re-exec. runpy will reload ingestion.simulator — any
        patch on its own attributes would be lost — so instead we patch
        `paho.mqtt.client.Client` (the source) and bail out of run_forever via
        KeyboardInterrupt the first time publish_once completes."""
        import paho.mqtt.client as paho
        mocker.patch.object(paho, "Client", return_value=mocker.MagicMock())
        monkeypatch.setenv("MQTT_HOST", "broker.local")
        monkeypatch.setenv("MQTT_PORT", "1999")
        monkeypatch.setenv("SIM_INTERVAL_SECONDS", "7")
        # time.sleep lives in the stdlib `time` module — patch there so the
        # fresh ingestion.simulator picks it up.
        import time as _time
        mocker.patch.object(_time, "sleep", side_effect=KeyboardInterrupt)

        glb = runpy.run_module("ingestion.simulator", run_name="__main__")
        # The Simulator instance was constructed with env-supplied values.
        assert glb["sim"].broker_host == "broker.local"
        assert glb["sim"].broker_port == 1999
        assert glb["sim"].interval_seconds == 7


# ---------------------------------------------------------------------------
# pipeline.py — run_forever + __main__
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline(mocker):
    mock_ch = mocker.MagicMock()
    mocker.patch("ingestion.pipeline.clickhouse_connect.get_client", return_value=mock_ch)
    mock_mqtt = mocker.MagicMock()
    mocker.patch("ingestion.pipeline.mqtt.Client", return_value=mock_mqtt)
    from ingestion.pipeline import IngestionPipeline
    p = IngestionPipeline(batch_size=2)
    p._ch_mock = mock_ch
    p._mqtt_mock = mock_mqtt
    return p


class TestPipelineRunForever:

    def test_run_forever_flushes_pending_buffer_on_interrupt(self, pipeline):
        # Pre-fill the buffer so KeyboardInterrupt -> _flush actually writes.
        valid = TelemetryReading(
            facility_id="office", device_id="d1", device_class="main_meter",
            domain="demand",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            value=1.0, unit="kW", metadata={},
        )
        pipeline._buffer.append(valid)
        pipeline._mqtt_mock.loop_forever.side_effect = KeyboardInterrupt
        pipeline.run_forever()
        pipeline._ch_mock.insert.assert_called_once()
        assert pipeline._records_written == 1


class TestPipelineMain:

    def test_main_block_wires_env(self, mocker, monkeypatch):
        """Patch at the source modules (paho + clickhouse_connect) so the
        fresh ingestion.pipeline re-executed by runpy inherits the mocks."""
        import clickhouse_connect as ch_mod
        import paho.mqtt.client as paho
        mock_ch_client = mocker.MagicMock()
        mock_mqtt_client = mocker.MagicMock()
        mock_mqtt_client.loop_forever.side_effect = KeyboardInterrupt
        mocker.patch.object(ch_mod, "get_client", return_value=mock_ch_client)
        mocker.patch.object(paho, "Client", return_value=mock_mqtt_client)

        monkeypatch.setenv("MQTT_HOST", "mqtt.local")
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch.local")
        monkeypatch.setenv("CLICKHOUSE_USER", "u")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "p")

        glb = runpy.run_module("ingestion.pipeline", run_name="__main__")
        # get_client was called with env-sourced host
        call_kwargs = ch_mod.get_client.call_args.kwargs
        assert call_kwargs["host"] == "ch.local"
        assert call_kwargs["username"] == "u"
        assert call_kwargs["password"] == "p"


# ---------------------------------------------------------------------------
# pipeline_iot_hub.py — run_forever + __main__
# ---------------------------------------------------------------------------

@pytest.fixture
def consumer(mocker):
    mocker.patch(
        "ingestion.pipeline_iot_hub.clickhouse_connect.get_client",
        return_value=mocker.MagicMock(),
    )
    from ingestion.pipeline_iot_hub import IotHubEventHubConsumer
    return IotHubEventHubConsumer(eventhub_connection_string="fake", batch_size=2)


class TestIotHubRunForever:

    def test_run_forever_uses_eventhubconsumerclient(self, consumer, mocker):
        """Patch azure.eventhub.EventHubConsumerClient so no real network is hit.
        receive_batch is driven to call the on_event_batch callback, exercising
        the full wiring path including context-manager usage."""
        fake_client = mocker.MagicMock()
        # Context-manager protocol — `with client:` must return `client`.
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False

        # Stand in for the imported class — patch sys.modules so the
        # local `from azure.eventhub import EventHubConsumerClient` picks it up.
        fake_module = mocker.MagicMock()
        fake_module.EventHubConsumerClient.from_connection_string.return_value = fake_client
        mocker.patch.dict(sys.modules, {"azure.eventhub": fake_module})

        # receive_batch should drive one empty batch, then stop.
        def receive_batch(on_event_batch, starting_position):
            # Call with an empty event list — just exercises the plumbing.
            fake_pc = mocker.MagicMock()
            on_event_batch(fake_pc, [])
        fake_client.receive_batch.side_effect = receive_batch

        consumer.run_forever()
        fake_module.EventHubConsumerClient.from_connection_string.assert_called_once()
        fake_client.receive_batch.assert_called_once()

    def test_run_forever_handles_keyboard_interrupt(self, consumer, mocker):
        fake_client = mocker.MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False
        fake_client.receive_batch.side_effect = KeyboardInterrupt

        fake_module = mocker.MagicMock()
        fake_module.EventHubConsumerClient.from_connection_string.return_value = fake_client
        mocker.patch.dict(sys.modules, {"azure.eventhub": fake_module})

        # Pre-fill buffer so the finally-path _flush does work.
        reading = TelemetryReading(
            facility_id="office", device_id="d1", device_class="main_meter",
            domain="demand",
            timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            value=1.0, unit="kW", metadata={},
        )
        consumer._buffer.append(reading)
        consumer.run_forever()
        assert consumer._records_written == 1


class TestIotHubMain:

    def test_main_block_wires_env(self, mocker, monkeypatch):
        import clickhouse_connect as ch_mod
        mocker.patch.object(ch_mod, "get_client", return_value=mocker.MagicMock())
        # Stub azure.eventhub so run_forever's late import doesn't need the
        # real package. receive_batch raises immediately so we return promptly.
        fake_client = mocker.MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False
        fake_client.receive_batch.side_effect = KeyboardInterrupt
        fake_azure = mocker.MagicMock()
        fake_azure.EventHubConsumerClient.from_connection_string.return_value = fake_client
        mocker.patch.dict(sys.modules, {"azure.eventhub": fake_azure})

        monkeypatch.setenv("IOT_HUB_EVENTHUB_CONNECTION_STRING", "Endpoint=sb://x/")
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch.local")
        monkeypatch.setenv("CLICKHOUSE_USER", "u")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "p")

        runpy.run_module("ingestion.pipeline_iot_hub", run_name="__main__")
        call_kwargs = ch_mod.get_client.call_args.kwargs
        assert call_kwargs["host"] == "ch.local"
        assert call_kwargs["username"] == "u"
        assert call_kwargs["password"] == "p"
        fake_azure.EventHubConsumerClient.from_connection_string.assert_called_once()


# ---------------------------------------------------------------------------
# iot_hub_publisher.py — disconnect()
# ---------------------------------------------------------------------------

FAKE_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
FAKE_CONN_STR = (
    f"HostName=wattwise-hub.azure-devices.net;DeviceId=off-main-01;"
    f"SharedAccessKey={FAKE_KEY}"
)


class TestIotHubPublisherDisconnect:

    def test_disconnect_stops_loop_and_disconnects(self, mocker):
        mock_client = mocker.MagicMock()
        mocker.patch("ingestion.iot_hub_publisher.mqtt.Client", return_value=mock_client)
        from ingestion.iot_hub_publisher import IotHubPublisher
        pub = IotHubPublisher(FAKE_CONN_STR)
        pub.disconnect()
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_sas_token_uses_mocked_time(self, mocker):
        """time.time is mocked so the expiry component is deterministic."""
        mocker.patch("ingestion.iot_hub_publisher.time.time", return_value=1_700_000_000)
        from ingestion.iot_hub_publisher import generate_sas_token
        token = generate_sas_token("res-uri", FAKE_KEY, expiry_seconds=600)
        params = dict(p.split("=", 1) for p in token[len("SharedAccessSignature "):].split("&"))
        assert int(params["se"]) == 1_700_000_600
