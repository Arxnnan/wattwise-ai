"""WattWise AI — ingestion pipeline.

Subscribes to MQTT topics, validates telemetry, writes to ClickHouse.
Topic pattern: wattwise/#
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone

import clickhouse_connect
import paho.mqtt.client as mqtt

from ingestion.schema import TelemetryReading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MQTT_TOPIC_SUBSCRIBE = "wattwise/#"

INSERT_SQL = """
INSERT INTO wattwise.telemetry
(facility_id, device_id, device_class, domain, ts, value, unit, metadata)
VALUES
"""


class IngestionPipeline:
    """MQTT subscriber that validates and writes telemetry to ClickHouse."""

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        ch_host: str = "localhost",
        ch_port: int = 8123,
        ch_user: str = "wattwise",
        ch_password: str = "wattwise_dev",
        ch_database: str = "wattwise",
        batch_size: int = 50,
    ):
        self.batch_size = batch_size
        self._buffer: list[TelemetryReading] = []
        self._records_written = 0
        self._records_invalid = 0

        # ClickHouse client
        self._ch = clickhouse_connect.get_client(
            host=ch_host,
            port=ch_port,
            username=ch_user,
            password=ch_password,
            database=ch_database,
        )
        log.info("ClickHouse connected: %s:%s/%s", ch_host, ch_port, ch_database)

        # MQTT client
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                 client_id="wattwise-ingestion")
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message
        self._mqtt.connect(mqtt_host, mqtt_port, keepalive=60)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("MQTT connected, subscribing to %s", MQTT_TOPIC_SUBSCRIBE)
        client.subscribe(MQTT_TOPIC_SUBSCRIBE, qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            reading = TelemetryReading.from_mqtt_payload(msg.payload.decode())
            reading.validate()
            self._buffer.append(reading)
            if len(self._buffer) >= self.batch_size:
                self._flush()
        except Exception as e:
            self._records_invalid += 1
            log.warning("Invalid message on %s: %s", msg.topic, e)

    def _flush(self) -> None:
        if not self._buffer:
            return
        rows = [
            [
                r.facility_id,
                r.device_id,
                r.device_class,
                r.domain,
                r.timestamp,
                r.value,
                r.unit,
                json.dumps(r.metadata),
            ]
            for r in self._buffer
        ]
        self._ch.insert(
            "telemetry",
            rows,
            column_names=["facility_id", "device_id", "device_class",
                           "domain", "ts", "value", "unit", "metadata"],
        )
        self._records_written += len(rows)
        log.info("Flushed %d records to ClickHouse (total: %d)",
                 len(rows), self._records_written)
        self._buffer.clear()

    def run_forever(self) -> None:
        log.info("Ingestion pipeline running...")
        try:
            self._mqtt.loop_forever()
        except KeyboardInterrupt:
            self._flush()
            log.info("Ingestion stopped. Written: %d, Invalid: %d",
                     self._records_written, self._records_invalid)

    @property
    def stats(self) -> dict:
        return {
            "records_written": self._records_written,
            "records_invalid": self._records_invalid,
            "buffer_size": len(self._buffer),
        }


if __name__ == "__main__":
    pipeline = IngestionPipeline(
        mqtt_host=os.getenv("MQTT_HOST", "localhost"),
        ch_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        ch_user=os.getenv("CLICKHOUSE_USER", "wattwise"),
        ch_password=os.getenv("CLICKHOUSE_PASSWORD", "wattwise_dev"),
    )
    pipeline.run_forever()
