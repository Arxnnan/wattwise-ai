# Week 17 Final Review — Demo Script

Following `PROJECT_BLUEPRINT.md` §9's 9-point outline, filled in with the actual
commands/URLs/numbers this build produces — not placeholders. Run through this
once end-to-end before the real review; if a step's real output doesn't match
what's written here, fix the step or fix this doc, don't present stale numbers.

**Pre-flight** (do this ~15 min before the review):
```powershell
podman machine start
podman compose up -d
$ip = (wsl -d podman-machine-default -- ip -4 -o addr show eth0) -replace '.*inet\s+([0-9.]+)/.*','$1'
# note $ip — every localhost:PORT below may need to be $ip:PORT depending on
# whether the WSL localhost relay is currently working (docs/LOCAL_SETUP.md §2)
.venv\Scripts\Activate.ps1
```

---

## 1. Live IoT ingestion (3 facilities × 6 device classes)
```powershell
python -m ingestion.simulator      # publishes to Mosquitto
python -m ingestion.pipeline       # subscribes, validates, writes to ClickHouse
```
Show `ingestion/simulator.py`'s `FACILITIES` dict on screen (office, warehouse,
datacentre × main_meter/sub_meter/hvac/lighting/occupancy/weather = 18 devices),
then the pipeline's log lines confirming batched writes. Query to prove it landed:
```sql
SELECT facility_id, device_class, count() FROM wattwise.telemetry
GROUP BY facility_id, device_class ORDER BY facility_id;
```
**Azure note:** real IoT Hub ingestion is blocked by an RBAC gap, not code —
see `docs/midterm/UC01_APPEAL.md`. This step runs against the local Mosquitto
stand-in, which is the same protocol and the same `ingestion/pipeline.py`.

## 2. All 3 domains end-to-end
```sql
SELECT DISTINCT domain, unit FROM wattwise.telemetry;
-- consumption/kWh, demand/kW, cost/INR
```
Cost domain comes from `ml/cost_engine.py::add_cost_domain()` — show the ToU
rate table (`TouRateConfig`) and one row of `monthly_cost_summary()` output.

## 3. All 5 dashboard views with drilldown
| # | View | URL |
|---|---|---|
| 1 | Real-Time Consumption | Grafana — `http://localhost:3001` (or `$ip:3001`) |
| 2 | Demand Pattern Analysis | same Grafana instance, second dashboard |
| 3 | Cost Analysis | Power BI — build from `docs/POWER_BI_GUIDE.md` |
| 4 | AI Optimization Intelligence | Streamlit — `streamlit run dashboards/streamlit/app.py` → `http://localhost:8501` |
| 5 | Cross-Facility Benchmarking | Power BI — build from `docs/POWER_BI_GUIDE.md` |

Drilldown: in Streamlit, switch the facility selector (office/warehouse/
datacentre) live and show the anomaly feed and forecast update.

## 4. Live anomaly injection → PyOD → LSTM-AE → trigger → alert
```powershell
python - <<'PY'
from ml.data_generator import generate_historical, get_facility_demand_series
from ml.anomaly import AnomalyDetector
from ml.lstm_autoencoder import LSTMAutoencoder
import requests, json

df = generate_historical(days=60, interval_minutes=15, anomaly_rate=0.03, seed=42)
series = get_facility_demand_series(df, "office")

det = AnomalyDetector(); det.fit(series)
flags = det.predict(series)
print("PyOD flagged:", int(flags.sum()), "candidate anomalies")

ae = LSTMAutoencoder(); ae.fit(series)
confirmed = ae.predict(series, candidate_flags=flags)
print("LSTM-AE confirmed:", int(confirmed.sum()))

# fire one confirmed event at the real deployed Azure Function
idx = confirmed[confirmed].index[0]
payload = {
    "event_type": "anomaly", "facility_id": "office", "device_id": "off-main-01",
    "observed_value": float(series.loc[idx]), "expected_value": float(series.mean()),
    "anomaly_score": 0.9, "narrative": "Live demo injection.",
}
r = requests.post(
    "https://wattwise-functions.azurewebsites.net/api/event?code=<see .env FUNCTIONS_EVENT_URL>",
    json=payload,
)
print(r.status_code, r.json())
PY
```
This is real, not a mock: the last call hits the actually-deployed
`wattwise-functions` app (verified live 2026-09-02). Response shows
`"email": {"channel": "log_only", ...}` until ACS is provisioned — say so
plainly rather than skip past it; the trigger firing and being logged is the
real, demonstrable part.

**Evidently drift check** (Stage 3 of the cascade):
```powershell
python -c "from ml.drift_monitor import DriftMonitor; from ml.data_generator import generate_historical; dm = DriftMonitor(); print(dm.run_nightly_report(generate_historical(days=14)))"
```

## 5. 24h demand forecast vs actuals, MAPE ≤ 8%
```powershell
python -m pytest tests/model_accuracy/test_forecast_mape.py -v
```
Real measured MAPE ≈2% (`docs/MODEL_EVIDENCE.md`), target is ≤8% — show the
passing assertion, not just a claimed number.

## 6. Peak-shave recommendation with explainability
```powershell
python -c "
from ml.peak_optimizer import rank_loads
# see ml/peak_optimizer.py for the exact signature/sample loads
"
```
Show the XGBoost load-ranker's top-N shed sequence and the
deferrability/demand_contribution/comfort_impact/response_time features that
justify the ranking (blueprint §7.3) — this is the "explainability" part,
not just a sorted list.

## 7. Month-to-date cost projection per facility
Run Query 3 from `docs/POWER_BI_GUIDE.md` View 3, or:
```powershell
python -c "
from ml.data_generator import generate_with_cost
from ml.cost_engine import monthly_cost_summary
df = generate_with_cost(days=30)
print(monthly_cost_summary(df))
"
```

## 8. QA evidence: green CI, ≥80% coverage, Locust at scale
```powershell
python -m pytest --cov=. --cov-fail-under=80 -q
```
Real measured: **87.1% coverage**, all tests green (verified 2026-09-02).

**Full RFP-spec load test — already run, real result** (`tests/load/full_run.log`,
`tests/load/results_stats.csv`): 1,000 simulated meters, 1 hour, against the
local Mosquitto broker —

| Metric | Result | Target |
|---|---|---|
| Failures | 0 / 4,954 (0.00%) | — |
| p95 latency | **1,500 ms** | < 2,000 ms ✅ |
| p99 latency | 1,800 ms | — |
| max latency | 1,900 ms | — |

Passes, but with real, honest margin, not the false comfort of the earlier
300-meter smoke test (17ms p95) — 1,000 concurrent MQTT connections on one
local broker create genuine contention a lighter test doesn't surface. Worth
saying in the room: this is the load profile a single Mosquitto container
sustains, not a claim about IoT Hub's own scaling (which has a separate,
real constraint — the F1 free tier caps at 8,000 msgs/day, while 1,000
meters at 5-min intervals need 288,000/day, so production would need a
paid IoT Hub tier regardless of latency headroom).

## 9. Documentation walkthrough on Moodle
Walk through, in order: `PROJECT_BLUEPRINT.md` (source of truth, status
markers now synced to reality) → `docs/midterm/MIDTERM_REPORT.md` +
`docs/midterm/UC01_APPEAL.md` (the honest account of the IoT Hub gap and its
resolution attempt) → `docs/MODEL_EVIDENCE.md` (AI accuracy, before/after) →
`docs/LOCAL_SETUP.md` (reproducibility) → `docs/POWER_BI_GUIDE.md` (hand-off
for the 2 manually-built views).

---

## Known gaps to disclose proactively, not if asked

Say these before the reviewer finds them — matches the standard the appeal
itself asks to be judged by:

- Azure IoT Hub and the B1s VM are not provisioned — confirmed `AuthorizationFailed`
  with the correct account, evidenced in `docs/midterm/UC01_APPEAL.md`. Storage
  and Functions ARE live.
- ACS email is not provisioned — the Functions app degrades to a logged,
  structured response rather than silently failing.
- Power BI views 3 and 5 need to be built from `docs/POWER_BI_GUIDE.md` before
  the review if not already done.
