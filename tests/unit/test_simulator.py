"""Unit tests — IoT simulator."""
import pytest
from datetime import datetime, timezone

from ingestion.simulator import generate_readings, FACILITIES


class TestSimulator:

    def test_generate_readings_count(self):
        now = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        readings = list(generate_readings(now))
        # 3 facilities x 6 devices x 3 domains = 54 readings
        assert len(readings) == 54

    def test_all_domains_present(self):
        readings = list(generate_readings())
        domains = {r.domain for r in readings}
        assert domains == {"consumption", "demand", "cost"}

    def test_all_facilities_present(self):
        readings = list(generate_readings())
        facilities = {r.facility_id for r in readings}
        assert facilities == set(FACILITIES.keys())

    def test_demand_non_negative(self):
        readings = list(generate_readings())
        for r in readings:
            assert r.value >= 0, f"Negative value for {r.facility_id}/{r.domain}"

    def test_cost_derived_from_consumption(self):
        readings = list(generate_readings())
        for fac in FACILITIES:
            cons = next(r for r in readings
                       if r.facility_id == fac and
                       r.domain == "consumption" and
                       r.device_class == "main_meter")
            cost = next(r for r in readings
                       if r.facility_id == fac and
                       r.domain == "cost" and
                       r.device_class == "main_meter")
            # cost = consumption * rate
            from ingestion.schema import TOU_RATE_PER_KWH
            expected_cost = round(cons.value * TOU_RATE_PER_KWH, 4)
            assert abs(cost.value - expected_cost) < 0.001

    def test_readings_validate(self):
        for r in generate_readings():
            assert r.validate() is True

    def test_weekend_lower_than_weekday_office(self):
        # Monday 10am
        weekday = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        # Saturday 10am
        weekend = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)

        weekday_demand = sum(
            r.value for r in generate_readings(weekday)
            if r.facility_id == "office" and r.domain == "demand"
        )
        weekend_demand = sum(
            r.value for r in generate_readings(weekend)
            if r.facility_id == "office" and r.domain == "demand"
        )
        # Office should be much lower on weekends
        assert weekend_demand < weekday_demand
