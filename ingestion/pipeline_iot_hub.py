"""WattWise AI — ingestion read side for real Azure IoT Hub deployments.

IoT Hub's MQTT broker only accepts device-to-cloud PUBLISH — it does not
support SUBSCRIBE (`ingestion/pipeline.py`'s Mosquitto-based approach doesn't
carry over). The supported way to read telemetry back out is IoT Hub's
built-in Event Hubs-compatible endpoint, consumed here with `azure-eventhub`.

Reuses the same validate -> buffer -> batch-insert shape as
`ingestion/pipeline.py` (`IngestionPipeline`) and the same
`TelemetryReading.from_mqtt_payload` wire format that
`ingestion/iot_hub_publisher.py` sends, so a device publishing through the
IoT Hub path produces byte-identical payloads to one publishing through
Mosquitto — only the transport differs.

**Status: implemented, not yet exercised against a real hub** — same caveat
as `iot_hub_publisher.py`. `_process_event` (the parsing/validation/batching
logic) is unit-tested directly against constructed `EventData` objects
without needing a live Event Hub connection; `run_forever()`'s actual
`EventHubConsumerClient` wiring has not been.
"""
from __future__ import annotations
import json
import logging
import os

import clickhouse_connect

from ingestion.schema import TelemetryReading

log = logging.getLogger(__name__)

INSERT_SQL_COLUMNS = ["facility_id", "device_id", "device_class", "domain", "ts", "value", "unit", "metadata"]


class IotHubEventHubConsumer:
    """Consumes IoT Hub's Event Hubs-compatible endpoint, validates, writes to ClickHouse."""

    def __init__(
        self,
        eventhub_connection_string: str,
        consumer_group: str = "$Default",
        ch_host: str = "localhost",
        ch_port: int = 8123,
        ch_user: str = "wattwise",
        ch_password: str = "wattwise_dev",
        ch_database: str = "wattwise",
        batch_size: int = 50,
    ):
        self.eventhub_connection_string = eventhub_connection_string
        self.consumer_group = consumer_group
        self.batch_size = batch_size
        self._buffer: list[TelemetryReading] = []
        self._records_written = 0
        self._records_invalid = 0

        self._ch = clickhouse_connect.get_client(
            host=ch_host, port=ch_port, username=ch_user, password=ch_password, database=ch_database,
        )
        log.info("ClickHouse connected: %s:%s/%s", ch_host, ch_port, ch_database)

    def _process_event(self, event_body: bytes) -> None:
        """Validate one Event Hub message body and buffer it. Pure logic,
        deliberately separated from the EventHubConsumerClient wiring so it's
        testable without a live connection."""
        try:
            reading = TelemetryReading.from_mqtt_payload(event_body.decode("utf-8"))
            reading.validate()
            self._buffer.append(reading)
            if len(self._buffer) >= self.batch_size:
                self._flush()
        except Exception as e:
            self._records_invalid += 1
            log.warning("Invalid event: %s", e)

    def _flush(self) -> None:
        if not self._buffer:
            return
        rows = [
            [r.facility_id, r.device_id, r.device_class, r.domain, r.timestamp, r.value, r.unit, json.dumps(r.metadata)]
            for r in self._buffer
        ]
        self._ch.insert("telemetry", rows, column_names=INSERT_SQL_COLUMNS)
        self._records_written += len(rows)
        log.info("Flushed %d records to ClickHouse (total: %d)", len(rows), self._records_written)
        self._buffer.clear()

    def _on_event_batch(self, partition_context, events) -> None:
        for event in events:
            self._process_event(b"".join(event.body))
        self._flush()
        partition_context.update_checkpoint()

    def run_forever(self) -> None:
        from azure.eventhub import EventHubConsumerClient

        client = EventHubConsumerClient.from_connection_string(
            self.eventhub_connection_string, consumer_group=self.consumer_group,
        )
        log.info("IoT Hub Event Hub consumer starting (consumer_group=%s)...", self.consumer_group)
        try:
            with client:
                client.receive_batch(on_event_batch=self._on_event_batch, starting_position="-1")
        except KeyboardInterrupt:
            self._flush()
            log.info("Consumer stopped. Written: %d, Invalid: %d", self._records_written, self._records_invalid)

    @property
    def stats(self) -> dict:
        return {
            "records_written": self._records_written,
            "records_invalid": self._records_invalid,
            "buffer_size": len(self._buffer),
        }


if __name__ == "__main__":
    consumer = IotHubEventHubConsumer(
        eventhub_connection_string=os.environ["IOT_HUB_EVENTHUB_CONNECTION_STRING"],
        ch_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        ch_user=os.getenv("CLICKHOUSE_USER", "wattwise"),
        ch_password=os.getenv("CLICKHOUSE_PASSWORD", "wattwise_dev"),
    )
    consumer.run_forever()
