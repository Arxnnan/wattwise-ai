# tests/ — QA Suites

**Built in:** every week (QA is embedded, not appended)

Mandatory. CI runs on every push. Target ≥80% coverage. Covers the 4 RFP-mandated areas: IoT ingestion completeness, analytics accuracy, optimization trigger correctness, AI model quality.

## Layout
- `unit/` — schema validation, normalization, ToU calc, trigger logic, feature engineering
- `integration/` — simulator → IoT Hub → Function → ClickHouse → DuckDB (Testcontainers)
- `e2e/` — anomaly → AI → trigger → alert; forecast → dashboard render (Selenium)
- `load/` — Locust load profile (1,000 meters), lives in `locustfile.py` at repo root or here
- `conftest.py` — shared fixtures

## Test matrix
See `PROJECT_BLUEPRINT.md` §12 for the full 10-row matrix and targets (Anomaly F1 ≥ 0.88, Forecast MAPE ≤ 8%, LSTM-AE ROC-AUC ≥ 0.90, trigger precision/recall ≥ 95%, ingest p95 < 2s).

## Run
```powershell
pytest --cov=. --cov-report=term-missing
```
