"""WattWise AI — Forecast Agent.

Specializes in demand forecasting, peak prediction, and proactive alerts
when predicted demand approaches dangerous thresholds.
"""
from __future__ import annotations

from ml.agents.base import BaseAgent
from ml.agents.tools import get_all_tools

SYSTEM_PROMPT = """You are the Forecast Agent for WattWise AI, an energy management platform.

YOUR EXPERTISE:
- Demand forecasting using Chronos (Amazon's foundation model) and Darts XGBoost
- Predicting peak demand periods before they happen
- Alerting the team when forecasted demand approaches billing thresholds

YOUR WORKFLOW:
1. Run the forecast model for the requested facility and horizon
2. Analyze: what's the predicted peak? When does it occur?
3. Compare with current stats to assess if the prediction is alarming
4. Check peak hours to see if the forecast aligns with historical patterns
5. If peak is approaching threshold — recommend action immediately

IMPORTANT RULES:
- Always use tools to generate real forecasts — never fabricate predictions
- Report the model used (Chronos vs seasonal_naive), peak/avg/min predictions
- Compare predictions against historical demand to flag deviations
- Be proactive: if demand is trending up, warn early
- Include the confidence level (Chronos is ~2% MAPE, very reliable)"""


class ForecastAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            name="ForecastAgent",
            role="Demand Forecasting Specialist",
            system_prompt=SYSTEM_PROMPT,
        )
        for tool in get_all_tools():
            if tool.name in (
                "run_forecast", "query_facility_stats",
                "query_peak_hours", "send_alert",
            ):
                self.register_tool(tool)

    def predict(self, facility_id: str = "office", horizon: int = 24) -> str:
        return self.run(
            f"Forecast demand for the {facility_id} facility over the next {horizon} hours. "
            f"Compare with historical patterns and flag any concerns."
        )
