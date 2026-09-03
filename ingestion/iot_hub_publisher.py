"""WattWise AI — Azure IoT Hub device publisher.

Deliberately does NOT use the `azure-iot-device` SDK: that package pins
`paho-mqtt<2.0.0` on every 2.13-2.14 release, which conflicts with the
`paho-mqtt>=2.1` this project needs for `ingestion/simulator.py` and
`ingestion/pipeline.py`'s `mqtt.CallbackAPIVersion.VERSION2` calls (see the
note in `requirements.txt`). IoT Hub's device-facing protocol is documented,
plain MQTT with a SAS token as the password — no SDK is required to speak
it, so this module implements that directly with the same paho-mqtt 2.x
already in the dependency tree.

**Status: implemented, not yet exercised against a real hub.** IoT Hub
provisioning is blocked by an RBAC gap (`docs/midterm/UC01_APPEAL.md`,
PROJECT_BLUEPRINT.md §11) — there is no hub to connect to yet. The SAS token
generation and connection-string parsing below are pure functions, tested
directly (`tests/unit/test_iot_hub_publisher.py`); the actual
`connect()`/`publish()` path is written against IoT Hub's documented wire
protocol but has not been run against a live hub, and that gap is stated
here rather than implied away.

Wire protocol (per Microsoft's IoT Hub MQTT documentation):
  Host:     <hub-name>.azure-devices.net:8883 (TLS required)
  Username: <hub-name>.azure-devices.net/<device-id>/?api-version=2021-04-12
  Password: a SAS token (see `generate_sas_token`) — NOT the raw device key
  Topic:    devices/<device-id>/messages/events/
  Note:     IoT Hub's MQTT broker does not support SUBSCRIBE for telemetry;
            the read side needs the Event Hubs-compatible endpoint instead
            (see `ingestion/pipeline_iot_hub.py`).
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from dataclasses import dataclass

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


@dataclass
class DeviceConnectionInfo:
    host_name: str
    device_id: str
    shared_access_key: str


def parse_device_connection_string(conn_str: str) -> DeviceConnectionInfo:
    """Parse the `HostName=...;DeviceId=...;SharedAccessKey=...` format that
    `az iot hub device-identity connection-string show` prints."""
    parts = dict(kv.split("=", 1) for kv in conn_str.strip().rstrip(";").split(";"))
    missing = {"HostName", "DeviceId", "SharedAccessKey"} - parts.keys()
    if missing:
        raise ValueError(f"connection string missing fields: {sorted(missing)}")
    return DeviceConnectionInfo(
        host_name=parts["HostName"], device_id=parts["DeviceId"], shared_access_key=parts["SharedAccessKey"],
    )


def generate_sas_token(resource_uri: str, shared_access_key: str, expiry_seconds: int = 3600) -> str:
    """Generate an Azure SAS token — the standard HMAC-SHA256-over-the-resource-URI
    scheme used by IoT Hub, Event Hubs, and Service Bus alike.

    https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-security#sas-tokens
    """
    encoded_uri = urllib.parse.quote_plus(resource_uri)
    expiry = int(time.time()) + expiry_seconds
    string_to_sign = f"{encoded_uri}\n{expiry}"
    key_bytes = base64.b64decode(shared_access_key)
    signature = hmac.new(key_bytes, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = urllib.parse.quote_plus(base64.b64encode(signature))
    return f"SharedAccessSignature sr={encoded_uri}&sig={encoded_signature}&se={expiry}"


class IotHubPublisher:
    """Publishes telemetry to Azure IoT Hub over plain MQTT + SAS auth."""

    def __init__(self, connection_string: str, sas_ttl_seconds: int = 3600):
        self._info = parse_device_connection_string(connection_string)
        self._sas_ttl_seconds = sas_ttl_seconds
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._info.device_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.tls_set()

    def connect(self) -> None:
        resource_uri = f"{self._info.host_name}/devices/{self._info.device_id}"
        username = f"{self._info.host_name}/{self._info.device_id}/?api-version=2021-04-12"
        password = generate_sas_token(resource_uri, self._info.shared_access_key, self._sas_ttl_seconds)
        self._client.username_pw_set(username=username, password=password)
        self._client.connect(self._info.host_name, port=8883, keepalive=60)
        self._client.loop_start()
        log.info("Connecting device %s to %s", self._info.device_id, self._info.host_name)

    def publish(self, payload: str, qos: int = 1) -> mqtt.MQTTMessageInfo:
        topic = f"devices/{self._info.device_id}/messages/events/"
        return self._client.publish(topic, payload, qos=qos)

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
