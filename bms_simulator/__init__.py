"""WattWise AI — Mock BMS Simulator.

A standalone FastAPI web server that mimics a commercial Building Management System
(Honeywell Niagara / Johnson Metasys / Siemens Desigo). It accepts HTTP POST commands
from the WattWise action dispatcher and shows them live on a dashboard, with a
simulated building-state view (current demand, active overrides, history).

Run with:
    python -m bms_simulator.server

Then open http://localhost:9100 and point WattWise Alert Settings
BMS_WEBHOOK_URL to http://localhost:9100/command.
"""
