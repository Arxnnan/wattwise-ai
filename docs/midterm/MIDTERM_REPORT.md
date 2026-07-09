# WattWise AI — Mid-Term Review Evidence Package
**Week 10 Checkpoint · IMPACT pSiddhi 3.0 · S4-I-14**

| | |
|---|---|
| **Participant** | Arunn Thiayagarajan |
| **Project** | WattWise AI — Smart Energy Management Platform |
| **Topic ID** | S4-I-14 |
| **Checkpoint** | Week 10 — Mid-Term Review |
| **Date** | Week 10 of pSiddhi-2026-01 |

---

## Mid-Term Checkpoint Checklist (RFP Requirement)

| Requirement | Status | Evidence |
|---|---|---|
| ✅ IoT Hub ingestion operational | **DONE** | `ingestion/pipeline.py` — MQTT → ClickHouse pipeline live |
| ✅ Analytics for ≥2 energy domains | **DONE** | Consumption (kWh) + Demand (kW) ingesting end-to-end |
| ✅ Dashboard with ≥2 views | **DONE** | Grafana (Real-Time Consumption + Demand Pattern) + Streamlit (4 views) |
| ✅ Initial AI model trained | **DONE** | PyOD anomaly ensemble fitted; Chronos zero-shot forecast operational |
| ✅ Unit tests passing | **DONE** | 35+ unit tests across schema, simulator, anomaly, forecasting, data generator |
| ✅ Mid-term documentation | **DONE** | This document |

---

## 1. What Was Built (Weeks 4–9)

### Layer 1 — IoT Ingestion
- **`ingestion/schema.py`** — unified telemetry schema with validation
- **`ingestion/simulator.py`** — IoT device simulator for 3 facilities × 6 device classes × 3 domains
- **`ingestion/pipeline.py`** — MQTT subscriber + ClickHouse writer
- Local MQTT broker: **Mosquitto** (Docker, same protocol as Azure IoT Hub)
- 54 readings per 5-minute cycle (3 facilities × 6 devices × 3 domains)

### Layer 2 — High-Performance Analytics
- **ClickHouse** running in Docker with the full production schema (`analytics/clickhouse/001_init_schema.sql`)
- Tables: `telemetry`, `demand_15min`, `anomaly_events`, `forecasts`
- 90 days of historical data generated for model training

### Layer 3 — AI / ML Core
- **`ml/data_generator.py`** — 90-day historical generator grounded in real consumption patterns
- **`ml/anomaly.py`** — PyOD 3-algorithm ensemble (IsolationForest + COPOD + ECOD), 2-of-3 vote
- **`ml/forecasting.py`** — Chronos zero-shot foundation model + seasonal naive fallback

### Layer 5 — Dashboards
- **Grafana** provisioned with ClickHouse datasource (docker-compose auto-provisions)
- **`dashboards/streamlit/app.py`** — 4-view Streamlit demo app:
  - View 1: Real-Time Consumption
  - View 2: Demand Pattern Analysis
  - View 3: AI Anomaly Detection
  - View 4: Demand Forecast

### Triggers
- **`triggers/handler.py`** — local event handler → MailHog email alerts

---

## 2. Architecture Diagram

```
IoT Simulator (Python)
        │ publishes MQTT (paho-mqtt)
        ▼
Mosquitto (Docker:1883)     ← local Azure IoT Hub equivalent
        │
        ▼
Ingestion Pipeline (Python)
        │ validated, batched writes
        ▼
ClickHouse (Docker:8123)    ← time-series analytics store
        │ queried by
        ▼
ML Core                     ← AI is the engine
  ├── PyOD Anomaly Ensemble (IForest + COPOD + ECOD)
  └── Chronos Foundation Model (zero-shot forecast)
        │ events + forecasts
        ▼
Trigger Handler             → MailHog (email) + console log
        │
        ▼
Grafana (Docker:3001)       ← real-time ops dashboards
Streamlit (local:8501)      ← 4-view public demo dashboard
```

---

## 3. Test Evidence

### Test Suite
| Test File | Tests | Coverage area |
|---|---|---|
| `test_schema.py` | 9 tests | Telemetry schema, validation, MQTT roundtrip |
| `test_simulator.py` | 7 tests | IoT simulator, domain coverage, physics validity |
| `test_data_generator.py` | 8 tests | Historical data generation, reproducibility |
| `test_anomaly.py` | 5 tests | PyOD ensemble, spike detection, scoring |
| `test_forecasting.py` | 6 tests | Forecast shape, CI ordering, peak warning |
| **Total** | **35+ tests** | **Schema · Ingestion · AI Core** |

All tests pass. Run: `pytest --cov=. --cov-report=term-missing`

---

## 4. AI Models — Mid-Term Status

### Anomaly Detection (PyOD Ensemble)
- **Algorithm:** IsolationForest + COPOD + ECOD (2-of-3 majority vote)
- **Training data:** 30–90 days of generated historical telemetry
- **Contamination parameter:** 2%
- **Spike injection test:** ✅ 5× normal demand spike detected reliably
- **Status:** Fitted and working. F1 tuning continues in Phase 2.

### Demand Forecasting (Chronos)
- **Algorithm:** Amazon Chronos T5-tiny (zero-shot, no training required)
- **Output:** 24h-ahead hourly predictions with 80% confidence intervals
- **Fallback:** Seasonal naive (same time yesterday) when Chronos unavailable
- **Status:** Operational day 1 (zero-shot foundation model)

---

## 5. Budget Status

| | Amount |
|---|---|
| Ceiling | ₹2,500 |
| Planned | ₹1,250 |
| **Spent to date** | **₹0** |
| Buffer remaining | ₹1,250 |

All development has been on local free-tier / OSS tools. Azure cloud account provisioning deferred to Week 15 (deployment phase).

---

## 6. Risks Encountered and Mitigations

| Risk | Status | Mitigation applied |
|---|---|---|
| Azure not yet provisioned | ✅ Mitigated | Built with Azure-native-local stack (Functions Core Tools + Azurite + Mosquitto) — cloud-portable |
| Python 3.14 ML library incompatibility | ✅ Resolved | Project uses Python 3.11 venv; 3.14 retained for other use |
| Chronos library heavy installation | ✅ Handled | Graceful fallback to seasonal naive if Chronos unavailable |

---

## 7. Phase 2 Plan (Weeks 11–16)

| Week | Focus |
|---|---|
| Wk 11 | Cost domain (ToU) + LSTM Autoencoder + Evidently drift |
| Wk 12 | Cost Analysis + AI Optimization Intelligence dashboard views |
| Wk 13 | XGBoost load-ranker + Azure Functions trigger wiring |
| Wk 14 | Gemini 2.5 Flash narratives + HF API fallback |
| Wk 15 | Cross-facility benchmarking view + Azure deployment |
| Wk 16 | Final docs, demo video, presentation, Moodle upload |

---

*Submitted for Week 10 Mid-Term Review · WattWise AI · IMPACT pSiddhi 3.0*
