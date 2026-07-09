# WattWise AI — Smart Energy Management Platform

[![Semester](https://img.shields.io/badge/IMPACT%20pSiddhi-S4--I--14-0E9F8F)](.) [![Status](https://img.shields.io/badge/status-Week%204%20Build%20Phase%201-blue)](.) [![Budget](https://img.shields.io/badge/budget-%E2%82%B91%2C650%20%2F%20%E2%82%B92%2C500-success)](.)

> **From invoice-driven energy management to AI-powered, real-time optimization.**

An end-to-end, AI-core, Azure-deployed platform that ingests IoT smart-meter and sensor telemetry, processes it through a high-performance analytics engine, uses ML to forecast demand / detect anomalies / manage peak load, automatically triggers optimization actions, and surfaces it all through real-time dashboards with plain-language AI recommendations.

**Read [`PROJECT_BLUEPRINT.md`](PROJECT_BLUEPRINT.md) for the complete end-to-end design** — architecture, tech stack, data model, AI spec, build sequence, QA strategy, and the RFP requirement map.

## Quickstart

```powershell
# 1. Start Docker Desktop, then bring up local infra
docker compose up -d

# 2. Create the Python 3.11 environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure secrets
Copy-Item .env.example .env   # then fill in your keys

# 4. Run tests
pytest
```

## Architecture (5 layers)

`Smart meters & sensors → Azure IoT Hub → Azure Functions → ClickHouse + DuckDB + dbt → ML core (Chronos+Darts / PyOD+LSTM-AE / XGBoost / Evidently) → Gemini → Grafana + Power BI + Streamlit + automated triggers`

| Layer | Folder | Tech |
|---|---|---|
| IoT Ingestion | [`ingestion/`](ingestion/) | Azure IoT Hub, paho-mqtt |
| Analytics | [`analytics/`](analytics/) | ClickHouse, DuckDB, dbt |
| AI / ML Core | [`ml/`](ml/) | Chronos, Darts, PyOD, LSTM-AE, XGBoost, Evidently |
| Triggers | [`triggers/`](triggers/) | Azure Functions |
| Dashboards | [`dashboards/`](dashboards/) | Grafana, Power BI, Streamlit |
| Inference API | [`api/`](api/) | FastAPI |

## Tech Stack

Python 3.11 · Azure (IoT Hub, Functions, B1s VM, Blob, ACS) · ClickHouse · DuckDB · dbt · Chronos · Darts · PyOD · TensorFlow/Keras · XGBoost · Optuna · MLflow · Evidently · Gemini 2.5 Flash · Grafana · Power BI · Streamlit · Pytest · Locust · GitHub Actions.

## License & Attribution

Built for IMPACT pSiddhi 3.0 (Semester 4 Capstone). All tools used are open-source or free-tier.
