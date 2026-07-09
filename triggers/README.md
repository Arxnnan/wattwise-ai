# triggers/ — Automated Optimization Triggers (Layer 4)

**Built in:** Week 13

Azure Functions app that closes the optimization loop. Subscribes to IoT Hub events; on an AI-detected peak or anomaly it writes the event to ClickHouse, calls Gemini for a narrative, and dispatches actions.

## Will contain
- `function_app.py` — Azure Functions v2 programming model entry point
- `handlers/peak.py` — peak-demand event handler → load-shave recommendation
- `handlers/anomaly.py` — anomaly event handler → alert + narrative
- `dispatch/` — ACS email, Twilio SMS, mock BMS webhook
- `local.settings.json` — local secrets (gitignored)

## Action channels
- **Email** via Azure Communication Services (free tier)
- **SMS** via Twilio (demo)
- **BMS command** via mock REST webhook (logs the action)

## QA
Trigger-correctness tests verify Functions fire on labelled anomaly events and do **not** fire on labelled normal events. Target ≥95% precision/recall.
