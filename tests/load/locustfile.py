"""WattWise AI — ingestion load test (RFP §12: 1,000 meters x 5-min, <2s p95).

Locust is built around HTTP; this project's ingestion path is MQTT
(`ingestion/pipeline.py`). Locust explicitly supports non-HTTP protocols via a
custom `User` that fires its own `request` events — this is that pattern
(see: https://docs.locust.io/en/stable/testing-other-systems.html).

Scope, stated plainly: this measures **MQTT publish-call latency** — how long
`client.publish()` takes to hand a reading to the broker under concurrent load
from many simulated meters. It does NOT measure all the way through to a
ClickHouse row landing (that would need a correlated subscriber matching each
published message to its eventual write, which `ingestion/pipeline.py`
doesn't currently expose a hook for). Publish-call latency is still the right
signal for "does the broker/network path degrade under 1,000 concurrent
meters" — but don't read a passing run here as proof of end-to-end DB-write
latency; that's a follow-up once the pipeline exposes a completion signal.

Each simulated Locust user = one meter, reusing the real device/reading
generation from `ingestion.simulator` and `ingestion.schema` so the payloads
are the same shape production traffic would be, not synthetic filler.

Run (1,000 meters, ramped up at 100/sec, against local Mosquitto):
    locust -f tests/load/locustfile.py --host tcp://localhost:1883 \
        -u 1000 -r 100 --run-time 1h --headless \
        --csv=tests/load/results
Then check `tests/load/results_stats.csv` — 95%ile column should be < 2000ms.
"""
from __future__ import annotations
import os
import random
import time

import paho.mqtt.client as mqtt
from locust import User, task, between, events

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingestion.schema import TelemetryReading, DOMAIN_UNITS
from ingestion.simulator import FACILITIES, _demand_kw
from datetime import datetime, timezone

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

# Flatten the real facility/device roster so each simulated meter picks a
# genuine (facility, device) pair instead of inventing fictitious ones.
_ALL_DEVICES = [
    (facility_id, device)
    for facility_id, cfg in FACILITIES.items()
    for device in cfg["devices"]
]


class MqttClient:
    """Thin wrapper so `client.publish(...)` reports to Locust like an HTTP call."""

    def __init__(self, host: str, port: int):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

    def publish_reading(self, facility_id: str, device: dict, domain: str) -> None:
        start = time.perf_counter()
        exc = None
        try:
            demand = _demand_kw(facility_id, device, datetime.now(timezone.utc))
            reading = TelemetryReading(
                facility_id=facility_id,
                device_id=device["id"],
                device_class=device["class"],
                domain=domain,
                timestamp=datetime.now(timezone.utc),
                value=round(demand, 4) if domain == "demand" else round(demand * 0.25, 4),
                unit=DOMAIN_UNITS[domain],
                metadata={"load_test": True},
            )
            topic = f"wattwise/{facility_id}/{device['id']}/{domain}"
            info = self._client.publish(topic, reading.to_mqtt_payload(), qos=1)
            info.wait_for_publish(timeout=5)
        except Exception as e:
            exc = e
        total_time_ms = (time.perf_counter() - start) * 1000
        events.request.fire(
            request_type="MQTT-PUB",
            name=f"{facility_id}/{device['class']}",
            response_time=total_time_ms,
            response_length=0,
            exception=exc,
        )

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


class MeterUser(User):
    """One simulated smart meter, publishing a reading every ~5 minutes."""

    wait_time = between(295, 305)  # ~5 min, jittered so 1,000 meters don't sync

    def on_start(self):
        self.facility_id, self.device = random.choice(_ALL_DEVICES)
        self.client = MqttClient(MQTT_HOST, MQTT_PORT)

    def on_stop(self):
        self.client.stop()

    @task
    def publish_demand_reading(self):
        self.client.publish_reading(self.facility_id, self.device, "demand")
