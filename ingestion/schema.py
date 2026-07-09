"""WattWise AI — unified telemetry schema and validation."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal

Domain = Literal["consumption", "demand", "cost"]
DeviceClass = Literal["main_meter", "sub_meter", "hvac", "lighting", "occupancy", "weather"]
FacilityID = Literal["office", "warehouse", "datacentre"]

DOMAIN_UNITS: dict[str, str] = {
    "consumption": "kWh",
    "demand": "kW",
    "cost": "INR",
}

TOU_RATE_PER_KWH = 8.0  # ₹ per kWh (flat rate for dev; ToU in Phase 2)


@dataclass
class TelemetryReading:
    facility_id: str
    device_id: str
    device_class: str
    domain: str
    timestamp: datetime
    value: float
    unit: str
    metadata: dict

    def validate(self) -> bool:
        assert self.facility_id in ("office", "warehouse", "datacentre"), f"Bad facility: {self.facility_id}"
        assert self.domain in DOMAIN_UNITS, f"Bad domain: {self.domain}"
        assert self.unit == DOMAIN_UNITS[self.domain], f"Unit mismatch: {self.unit} for {self.domain}"
        assert self.value >= 0, f"Negative value: {self.value}"
        return True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["metadata"] = json.dumps(self.metadata)
        return d

    def to_mqtt_payload(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_mqtt_payload(cls, payload: str) -> "TelemetryReading":
        d = json.loads(payload)
        d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        d["metadata"] = json.loads(d["metadata"]) if isinstance(d["metadata"], str) else d["metadata"]
        return cls(**d)
