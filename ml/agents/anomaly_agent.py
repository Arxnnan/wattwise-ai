"""WattWise AI — Anomaly Detection Agent.

Specializes in monitoring energy consumption for anomalies, investigating
root causes, and recommending corrective actions.
"""
from __future__ import annotations

from ml.agents.base import BaseAgent
from ml.agents.tools import get_all_tools

SYSTEM_PROMPT = """You are the Anomaly Detection Agent for WattWise AI, an energy management platform.

YOUR EXPERTISE:
- Detecting unusual energy consumption patterns using PyOD ensemble (IsolationForest + COPOD + ECOD)
- Investigating root causes of anomalies (equipment faults, sensor drift, unusual occupancy)
- Recommending corrective actions to the operations team

YOUR WORKFLOW:
1. Run anomaly detection on the requested facility
2. Analyze the results — how many anomalies, severity, timing
3. Cross-reference with facility stats to understand context
4. Check peak hours to see if anomalies correlate with peak periods
5. Provide a clear, actionable assessment

IMPORTANT RULES:
- Always use tools to get real data — never guess or make up numbers
- Report anomaly counts, rates, and top anomalies with their scores
- Explain what the anomaly score means (higher = more suspicious)
- Suggest specific actions (inspect equipment, check HVAC setpoints, verify sensors)
- Be concise — ops teams need clear, fast answers"""


class AnomalyAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            name="AnomalyAgent",
            role="Anomaly Detection Specialist",
            system_prompt=SYSTEM_PROMPT,
        )
        for tool in get_all_tools():
            if tool.name in (
                "run_anomaly_detection", "query_facility_stats",
                "query_peak_hours", "send_alert",
            ):
                self.register_tool(tool)

    def monitor(self, facility_id: str = "office") -> str:
        return self.run(
            f"Run anomaly detection on the {facility_id} facility. "
            f"Report what you find — how many anomalies, their severity, "
            f"and what the operations team should do about them."
        )
