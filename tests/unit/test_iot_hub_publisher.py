"""Unit tests — ingestion/iot_hub_publisher.py.

Covers the pure SAS-token/connection-string logic (testable without a real
hub — none exists yet, see the module docstring). `connect()`/`publish()`
are mocked at the paho-mqtt boundary the same way tests/unit/test_pipeline.py
mocks the local pipeline's MQTT client.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import time
import urllib.parse

import pytest

from ingestion.iot_hub_publisher import (
    DeviceConnectionInfo,
    parse_device_connection_string,
    generate_sas_token,
    IotHubPublisher,
)

FAKE_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
FAKE_CONN_STR = f"HostName=wattwise-hub.azure-devices.net;DeviceId=off-main-01;SharedAccessKey={FAKE_KEY}"


class TestParseDeviceConnectionString:

    def test_parses_all_fields(self):
        info = parse_device_connection_string(FAKE_CONN_STR)
        assert info == DeviceConnectionInfo(
            host_name="wattwise-hub.azure-devices.net", device_id="off-main-01", shared_access_key=FAKE_KEY,
        )

    def test_tolerates_trailing_semicolon(self):
        info = parse_device_connection_string(FAKE_CONN_STR + ";")
        assert info.device_id == "off-main-01"

    def test_missing_field_raises(self):
        with pytest.raises(ValueError, match="missing fields"):
            parse_device_connection_string("HostName=x.azure-devices.net;DeviceId=d1")


class TestGenerateSasToken:

    def test_token_has_expected_structure(self):
        token = generate_sas_token("wattwise-hub.azure-devices.net/devices/off-main-01", FAKE_KEY)
        assert token.startswith("SharedAccessSignature ")
        params = dict(p.split("=", 1) for p in token[len("SharedAccessSignature "):].split("&"))
        assert set(params.keys()) == {"sr", "sig", "se"}

    def test_expiry_is_in_the_future(self):
        before = int(time.time())
        token = generate_sas_token("res-uri", FAKE_KEY, expiry_seconds=600)
        params = dict(p.split("=", 1) for p in token[len("SharedAccessSignature "):].split("&"))
        assert int(params["se"]) >= before + 600

    def test_signature_is_reproducible_hmac(self):
        # Recompute the signature independently and confirm it matches —
        # guards against silently changing the signing scheme.
        resource_uri = "wattwise-hub.azure-devices.net/devices/off-main-01"
        token = generate_sas_token(resource_uri, FAKE_KEY, expiry_seconds=3600)
        params = dict(p.split("=", 1) for p in token[len("SharedAccessSignature "):].split("&"))
        expiry = params["se"]
        encoded_uri = urllib.parse.quote_plus(resource_uri)
        string_to_sign = f"{encoded_uri}\n{expiry}"
        expected_sig = hmac.new(base64.b64decode(FAKE_KEY), string_to_sign.encode(), hashlib.sha256).digest()
        expected_encoded = urllib.parse.quote_plus(base64.b64encode(expected_sig))
        assert params["sig"] == expected_encoded


class TestIotHubPublisher:

    def test_init_parses_connection_string_and_enables_tls(self, mocker):
        mock_mqtt_client = mocker.MagicMock()
        mocker.patch("ingestion.iot_hub_publisher.mqtt.Client", return_value=mock_mqtt_client)

        publisher = IotHubPublisher(FAKE_CONN_STR)

        assert publisher._info.device_id == "off-main-01"
        mock_mqtt_client.tls_set.assert_called_once()

    def test_connect_sets_sas_token_as_password(self, mocker):
        mock_mqtt_client = mocker.MagicMock()
        mocker.patch("ingestion.iot_hub_publisher.mqtt.Client", return_value=mock_mqtt_client)
        publisher = IotHubPublisher(FAKE_CONN_STR)

        publisher.connect()

        mock_mqtt_client.username_pw_set.assert_called_once()
        _, kwargs = mock_mqtt_client.username_pw_set.call_args
        assert kwargs["username"] == "wattwise-hub.azure-devices.net/off-main-01/?api-version=2021-04-12"
        assert kwargs["password"].startswith("SharedAccessSignature ")
        mock_mqtt_client.connect.assert_called_once_with("wattwise-hub.azure-devices.net", port=8883, keepalive=60)

    def test_publish_uses_device_topic(self, mocker):
        mock_mqtt_client = mocker.MagicMock()
        mocker.patch("ingestion.iot_hub_publisher.mqtt.Client", return_value=mock_mqtt_client)
        publisher = IotHubPublisher(FAKE_CONN_STR)

        publisher.publish('{"value": 1}')

        mock_mqtt_client.publish.assert_called_once_with(
            "devices/off-main-01/messages/events/", '{"value": 1}', qos=1,
        )
