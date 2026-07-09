"""Unit tests — telemetry schema validation."""
import json
import pytest
from datetime import datetime, timezone

from ingestion.schema import TelemetryReading, DOMAIN_UNITS, TOU_RATE_PER_KWH


class TestTelemetryReading:

    def test_valid_reading_passes(self, sample_reading):
        assert sample_reading.validate() is True

    def test_invalid_facility_raises(self):
        r = TelemetryReading(
            facility_id="unknown",
            device_id="d1", device_class="main_meter",
            domain="demand",
            timestamp=datetime.now(timezone.utc),
            value=10.0, unit="kW", metadata={},
        )
        with pytest.raises(AssertionError, match="Bad facility"):
            r.validate()

    def test_invalid_domain_raises(self):
        r = TelemetryReading(
            facility_id="office",
            device_id="d1", device_class="main_meter",
            domain="invalid_domain",
            timestamp=datetime.now(timezone.utc),
            value=10.0, unit="kW", metadata={},
        )
        with pytest.raises(AssertionError, match="Bad domain"):
            r.validate()

    def test_negative_value_raises(self, sample_reading):
        sample_reading.value = -1.0
        with pytest.raises(AssertionError, match="Negative value"):
            sample_reading.validate()
        sample_reading.value = 42.5  # restore

    def test_mqtt_roundtrip(self, sample_reading):
        payload = sample_reading.to_mqtt_payload()
        restored = TelemetryReading.from_mqtt_payload(payload)
        assert restored.facility_id == sample_reading.facility_id
        assert restored.domain == sample_reading.domain
        assert abs(restored.value - sample_reading.value) < 1e-6

    def test_to_dict_has_required_keys(self, sample_reading):
        d = sample_reading.to_dict()
        required = {"facility_id", "device_id", "device_class",
                    "domain", "timestamp", "value", "unit", "metadata"}
        assert required.issubset(d.keys())

    @pytest.mark.parametrize("domain,unit", DOMAIN_UNITS.items())
    def test_domain_unit_mapping(self, domain, unit):
        r = TelemetryReading(
            facility_id="warehouse",
            device_id="wh-main-01", device_class="main_meter",
            domain=domain,
            timestamp=datetime.now(timezone.utc),
            value=1.0, unit=unit, metadata={},
        )
        assert r.validate() is True

    def test_tou_rate_positive(self):
        assert TOU_RATE_PER_KWH > 0
