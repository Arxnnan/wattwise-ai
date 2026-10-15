# Grafana — Real-Time Operations Dashboards

Grafana OSS runs via `compose.yaml` on port **3001**, pre-wired to ClickHouse
with 2 auto-provisioned dashboards.

## Quick start

```powershell
# 1. Start the full local stack (ClickHouse + Mosquitto + Grafana + Mailpit + Azurite)
podman compose up -d

# 2. Populate ClickHouse with ~30 days of synthetic telemetry
.venv\Scripts\python.exe -m ingestion.simulator &  # publishes to MQTT
.venv\Scripts\python.exe -m ingestion.pipeline      # subscribes + writes to ClickHouse

# 3. Open Grafana
Start-Process http://localhost:3001
```

**Login:** `admin` / `wattwise_dev` (set via `GF_SECURITY_ADMIN_PASSWORD` in `compose.yaml`)

## What ships out of the box

| Dashboard | URL | Purpose |
|---|---|---|
| **Real-Time Consumption** | http://localhost:3001/d/wattwise-realtime | Live kW per facility, device-class consumption stack, current demand per facility |
| **Demand Pattern Analysis** | http://localhost:3001/d/wattwise-demand | 15-min rolling demand vs 150 kW threshold, exceedances, demand-charge estimate, hour-of-day heatmap |

Both dashboards auto-refresh (10s on real-time, 30s on demand analysis) and
support facility filtering via the top-left dropdown.

## File layout

```
dashboards/grafana/
├── provisioning/
│   ├── datasources/
│   │   └── clickhouse.yaml           # auto-provisioned datasource
│   └── dashboards/
│       ├── dashboards.yaml           # tells Grafana where to find JSON
│       ├── wattwise-realtime.json    # dashboard 1
│       └── wattwise-demand.json      # dashboard 2
└── README.md                         # this file
```

## How provisioning works

`compose.yaml` mounts `./dashboards/grafana/provisioning` at
`/etc/grafana/provisioning` (read-only). On container start, Grafana:

1. Reads `datasources/clickhouse.yaml` → auto-creates the ClickHouse datasource
2. Reads `dashboards/dashboards.yaml` → scans `dashboards/*.json`
3. Imports every dashboard JSON it finds into the "WattWise AI" folder

**You don't click "Add datasource" or "Import dashboard" manually.** Everything
is reproducible from the compose file.

## If dashboards show "No data"

Dashboards query `wattwise.telemetry` — if it's empty, panels are blank. Run:

```powershell
# Terminal 1: publish synthetic readings to Mosquitto
.venv\Scripts\python.exe -m ingestion.simulator

# Terminal 2: subscribe + batch-insert to ClickHouse
.venv\Scripts\python.exe -m ingestion.pipeline
```

After ~2 min of ingestion, refresh Grafana and panels light up.

## Why Grafana AND Streamlit?

| | Streamlit (localhost:8501) | Grafana (localhost:3001) |
|---|---|---|
| Audience | Facility manager, operator | Ops team, on-call engineers |
| Purpose | Daily workflow + AI recommendations + Approve/Dismiss | Real-time monitoring + alerting + trend investigation |
| Data | In-memory synthetic (via `ml.data_generator`) | ClickHouse (persistent) |
| AI integration | Deep — 8 agents, 7 ML models | Thin — reads ClickHouse only |

Both are deliberate. Streamlit is the AI-advisor experience; Grafana is the
"what energy companies actually use" ops surface promised in the proposal.

## Reset Grafana to defaults

```powershell
podman compose down
podman volume rm wattwise-ai_grafana-data
podman compose up -d
```
