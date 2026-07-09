# ingestion/ — IoT Ingestion (Layer 1)

**Built in:** Weeks 4–5

Smart-meter and building-sensor simulators plus Azure IoT Hub device clients. Generates telemetry for 3 facilities (office, warehouse, data centre) across 6 device classes (main_meter, sub_meter, hvac, lighting, occupancy, weather) and 3 energy domains (consumption kWh, demand kW, cost ₹).

## Will contain
- `simulator.py` — paho-mqtt / Azure IoT Device SDK telemetry generator
- `schema.py` — the unified telemetry schema + validation
- `device_clients/` — per-facility device-twin clients
- `seed_loader.py` — replays UCI / ASHRAE / OpenEI datasets as realistic load shapes

## Telemetry schema
```
facility_id, device_id, device_class, domain, timestamp, value, unit, metadata
```

## Success criteria (Wk 5)
Consumption + demand domains stream end-to-end: simulator → IoT Hub → ClickHouse, validated by integration tests.
