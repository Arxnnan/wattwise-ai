# triggers/ — Automated Optimization Triggers (Layer 4)

Two implementations, both real:
- `handler.py` — local dev path (Mailpit SMTP), used against the Podman stack.
- `function_app.py` + `dispatch.py` — the actual Azure Functions app,
  **deployed and verified live** at `wattwise-functions.azurewebsites.net`
  (2026-09-02). Not yet wired to fire automatically from IoT Hub events
  (IoT Hub itself is blocked — see `docs/midterm/UC01_APPEAL.md`); both
  endpoints accept and correctly process a manually-posted event today.

## Live endpoints
| Endpoint | Purpose | Status |
|---|---|---|
| `POST /api/event` | AI event (anomaly/peak/optimization) → alert dispatch | ✅ live, HTTP 200 verified |
| `POST /api/bms/webhook` | Mock load-shed command (logged, no real BMS) | ✅ live, HTTP 200 verified |

## Action channels
- **Email** via Azure Communication Services — code complete (`dispatch.py::send_alert_email`), but ACS itself is provisioning-blocked (same RBAC gap as IoT Hub/VM), so this degrades to a logged response, not a silent no-op.
- **SMS** via Twilio (optional/demo per blueprint §4) — code complete (`dispatch.py::send_alert_sms`), no Twilio account exists for this project, same log-only fallback.
- **BMS command** via mock REST webhook (logs the action) — this one has no real backing system by design, not by gap.

## QA
`tests/unit/test_dispatch.py` (15 tests) covers both dispatch functions'
configured and fallback paths. `tests/unit/test_trigger_handler.py` (6 tests)
covers the local SMTP path. Trigger-correctness against labeled anomaly
events (≥95% precision/recall target) is not yet a separate suite — today's
coverage is functional correctness of the dispatch logic itself.
