"""WattWise AI — IoT device simulator.

Generates realistic energy telemetry for 3 facilities x 6 device classes
grounded in real-world consumption patterns (daily/weekly cycles + noise).
Publishes to local Mosquitto MQTT broker on topic:
  wattwise/{facility_id}/{device_id}/{domain}
"""
from __future__ import annotations
import json
import math
import random
import time
import logging
from datetime import datetime, timezone
from typing import Generator

import paho.mqtt.client as mqtt

from ingestion.schema import TelemetryReading, DOMAIN_UNITS, TOU_RATE_PER_KWH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---- Facility definitions ----
FACILITIES = {
    "office": {
        "base_kw": 45.0,       # typical 5,000 sqft office
        "peak_hours": (8, 18),
        "peak_factor": 1.8,
        "weekend_factor": 0.2,
        "devices": [
            {"id": "off-main-01", "class": "main_meter", "share": 1.0},
            {"id": "off-sub-hvac", "class": "sub_meter", "share": 0.45},
            {"id": "off-hvac-01", "class": "hvac", "share": 0.43},
            {"id": "off-light-01", "class": "lighting", "share": 0.18},
            {"id": "off-occ-01", "class": "occupancy", "share": 0.0},
            {"id": "off-wx-01", "class": "weather", "share": 0.0},
        ],
    },
    "warehouse": {
        "base_kw": 80.0,
        "peak_hours": (6, 22),
        "peak_factor": 1.5,
        "weekend_factor": 0.6,
        "devices": [
            {"id": "wh-main-01", "class": "main_meter", "share": 1.0},
            {"id": "wh-sub-light", "class": "sub_meter", "share": 0.35},
            {"id": "wh-hvac-01", "class": "hvac", "share": 0.30},
            {"id": "wh-light-01", "class": "lighting", "share": 0.33},
            {"id": "wh-occ-01", "class": "occupancy", "share": 0.0},
            {"id": "wh-wx-01", "class": "weather", "share": 0.0},
        ],
    },
    "datacentre": {
        "base_kw": 120.0,      # 24/7 near-constant load
        "peak_hours": (0, 24),
        "peak_factor": 1.1,
        "weekend_factor": 0.95,
        "devices": [
            {"id": "dc-main-01", "class": "main_meter", "share": 1.0},
            {"id": "dc-sub-cooling", "class": "sub_meter", "share": 0.40},
            {"id": "dc-hvac-01", "class": "hvac", "share": 0.38},
            {"id": "dc-light-01", "class": "lighting", "share": 0.05},
            {"id": "dc-occ-01", "class": "occupancy", "share": 0.0},
            {"id": "dc-wx-01", "class": "weather", "share": 0.0},
        ],
    },
}

MQTT_TOPIC_TEMPLATE = "wattwise/{facility_id}/{device_id}/{domain}"


def _demand_kw(facility: str, device: dict, now: datetime) -> float:
    """Generate realistic demand using time-of-day + day-of-week patterns."""
    cfg = FACILITIES[facility]
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun

    # Base load
    base = cfg["base_kw"] * device["share"] if device["share"] > 0 else 0.0

    # Non-energy devices (occupancy, weather sensors draw no power)
    if device["class"] in ("occupancy", "weather"):
        return round(random.uniform(0.1, 0.5), 3)

    # Time-of-day factor
    peak_start, peak_end = cfg["peak_hours"]
    if peak_start <= hour < peak_end:
        tod_factor = cfg["peak_factor"]
    else:
        tod_factor = 0.6

    # Day-of-week factor
    dow_factor = cfg["weekend_factor"] if weekday >= 5 else 1.0

    # Smooth sinusoidal variation + noise
    sin_factor = 0.85 + 0.15 * math.sin(2 * math.pi * hour / 24)
    noise = random.gauss(0, 0.03)

    kw = base * tod_factor * dow_factor * sin_factor * (1 + noise)
    return round(max(0.0, kw), 3)


def generate_readings(now: datetime | None = None) -> Generator[TelemetryReading, None, None]:
    """Yield one full set of readings (all facilities x devices x domains) for a timestamp."""
    if now is None:
        now = datetime.now(timezone.utc)

    interval_hours = 5 / 60  # 5-minute reading interval

    for facility_id, cfg in FACILITIES.items():
        for device in cfg["devices"]:
            demand = _demand_kw(facility_id, device, now)
            consumption = round(demand * interval_hours, 5)  # kWh = kW * hours
            cost = round(consumption * TOU_RATE_PER_KWH, 4)

            readings = [
                TelemetryReading(
                    facility_id=facility_id,
                    device_id=device["id"],
                    device_class=device["class"],
                    domain="consumption",
                    timestamp=now,
                    value=consumption,
                    unit="kWh",
                    metadata={"interval_minutes": 5},
                ),
                TelemetryReading(
                    facility_id=facility_id,
                    device_id=device["id"],
                    device_class=device["class"],
                    domain="demand",
                    timestamp=now,
                    value=demand,
                    unit="kW",
                    metadata={"rolling_window_minutes": 15},
                ),
                TelemetryReading(
                    facility_id=facility_id,
                    device_id=device["id"],
                    device_class=device["class"],
                    domain="cost",
                    timestamp=now,
                    value=cost,
                    unit="INR",
                    metadata={"rate_per_kwh": TOU_RATE_PER_KWH},
                ),
            ]
            for r in readings:
                yield r


class Simulator:
    """MQTT-publishing IoT simulator."""

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883,
                 interval_seconds: int = 5):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.interval_seconds = interval_seconds
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id="wattwise-simulator")

    def connect(self) -> None:
        self._client.connect(self.broker_host, self.broker_port, keepalive=60)
        self._client.loop_start()
        log.info("Simulator connected to MQTT broker at %s:%s",
                 self.broker_host, self.broker_port)

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_once(self, now: datetime | None = None) -> int:
        """Publish one full set of readings. Returns count published."""
        count = 0
        for reading in generate_readings(now):
            topic = MQTT_TOPIC_TEMPLATE.format(
                facility_id=reading.facility_id,
                device_id=reading.device_id,
                domain=reading.domain,
            )
            self._client.publish(topic, reading.to_mqtt_payload(), qos=1)
            count += 1
        return count

    def run_forever(self) -> None:
        """Stream telemetry at interval_seconds cadence."""
        self.connect()
        log.info("Simulator running — publishing every %ss", self.interval_seconds)
        try:
            while True:
                count = self.publish_once()
                log.info("Published %d readings at %s", count,
                         datetime.now(timezone.utc).isoformat())
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            log.info("Simulator stopped.")
        finally:
            self.disconnect()


if __name__ == "__main__":
    import os
    sim = Simulator(
        broker_host=os.getenv("MQTT_HOST", "localhost"),
        broker_port=int(os.getenv("MQTT_PORT", "1883")),
        interval_seconds=int(os.getenv("SIM_INTERVAL_SECONDS", "5")),
    )
    sim.run_forever()
