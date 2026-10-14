# scripts/

One-command runners for every form of automated testing WattWise AI has.
Each script prints a clear PASS/FAIL table and exits with code 0 or 1 so it
can be dropped into CI directly.

## Available scripts

| Script | What it does | Typical use |
|---|---|---|
| `test-all.ps1` | Lint + unit + integration + model-accuracy, one summary table | Pre-commit, pre-push |
| `smoke.ps1` | Hits Streamlit + Mock BMS endpoints, verifies they respond | Post-deploy sanity check |
| `load-test.ps1` | Runs Locust against MQTT broker (100 meters quick, 1000 meters full) | Weekly perf regression / before major release |
| `model-gates.ps1` | Runs just the ML accuracy gates (Chronos MAPE / PyOD F1 / LSTM-AE ROC-AUC) | After any ML code change |

## Quick reference

```powershell
# Full test suite (unit + integration + model-accuracy + lint)
./scripts/test-all.ps1

# Fast suite (skip Chronos load, ~30s saved)
./scripts/test-all.ps1 -Fast

# Smoke-test local deployment
./scripts/smoke.ps1

# Smoke-test Azure Container Group deployment
./scripts/smoke.ps1 -Host "ww152650-wattwise.eastus.azurecontainer.io"

# Quick load test (100 meters, 2 min)
./scripts/load-test.ps1

# Full load test matching RFP spec (1000 meters, 1 hour)
./scripts/load-test.ps1 -Full

# Interactive Locust UI
./scripts/load-test.ps1 -UI

# Model accuracy gates only
./scripts/model-gates.ps1
```

## What each script actually checks

### `test-all.ps1`
- **Lint**: `ruff check .` (non-blocking warnings reported)
- **Unit**: `pytest tests/unit/` (~500 tests)
- **Integration**: `pytest tests/integration/` (~55 tests, cross-module paths)
- **Model accuracy**: `pytest tests/model_accuracy/` (Chronos MAPE gate)

Exit code is non-zero if any suite reports a failure.

### `smoke.ps1`
Hits 6 endpoints:
1. Streamlit `/_stcore/health` -> 200
2. Streamlit `/` -> HTML contains "Streamlit" or "WattWise"
3. Mock BMS `/health` -> `{"status":"ok"}`
4. Mock BMS `/api/state` -> JSON with 3 facilities
5. Mock BMS `/` -> HTML contains "Mock BMS"
6. Mock BMS `POST /command` -> accepts a sample shed command

Default host is `localhost`. Pass `-Host <fqdn>` for a deployed stack.

### `load-test.ps1`
Runs the Locust test at `tests/load/locustfile.py`. Measures MQTT publish-call
latency under concurrent meter load.

**Prerequisite**: Mosquitto MQTT broker running at the host/port you specify
(default `localhost:1883`). Start with `podman compose up -d mqtt`.

**Pass gate**: aggregated p95 latency < 2000 ms (RFP target).

Modes:
- `./load-test.ps1`              -> 100 meters, 2 minutes (quick smoke)
- `./load-test.ps1 -Full`        -> 1000 meters, 1 hour (RFP spec)
- `./load-test.ps1 -UI`          -> opens Locust web UI at http://localhost:8089

### `model-gates.ps1`
Runs only `tests/model_accuracy/` and prints the three RFP targets alongside
measured numbers:

- Chronos T5: MAPE <= 8%
- PyOD ensemble: F1 >= 0.88
- LSTM Autoencoder: ROC-AUC >= 0.90

## CI/CD integration

These scripts are mirrored by `.github/workflows/ci.yml` (runs on every push
+ PR). The workflow:
1. Runs `test-all.ps1` equivalent (lint + unit + integration)
2. Enforces `>= 80%` coverage via `pytest --cov-fail-under=80`
3. Uploads coverage.xml as an artifact
4. (Optional) Runs model-accuracy gates nightly to catch model drift

Load tests are too heavy for every-commit CI; schedule them weekly or run
manually before a release.

## Troubleshooting

**`.venv not found`** -> create virtualenv first: `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`

**Locust fails with "connect refused"** -> Mosquitto broker not running. `podman compose up -d mqtt` or point `-MqttHost` elsewhere.

**Smoke test fails on Streamlit** -> Streamlit container cold-start takes 60-90s. Wait and re-run.

**Model-gates slow on first run** -> Chronos downloads ~45 MB weights from HuggingFace on first load. Subsequent runs are cached.
