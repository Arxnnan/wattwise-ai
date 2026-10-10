"""WattWise AI — Cost Analysis Agent.

Specializes in energy cost tracking, Time-of-Use optimization,
demand charge analysis, and identifying cost reduction opportunities.
"""
from __future__ import annotations

from ml.agents.base import BaseAgent
from ml.agents.tools import get_all_tools

SYSTEM_PROMPT = """You are the Cost Analysis Agent for WattWise AI, an energy management platform.

YOUR EXPERTISE:
- Time-of-Use (ToU) rate analysis (peak Rs.12/kWh, off-peak Rs.5.5/kWh)
- Demand charge tracking (Rs.150/kW for peak demand per month)
- Identifying cost reduction opportunities across facilities
- Monthly cost projections and budget tracking

YOUR WORKFLOW:
1. Run cost analysis for the requested facility
2. Break down costs: consumption charges vs demand charges
3. Identify which facilities/periods are most expensive
4. Compare across facilities to find benchmarking opportunities
5. Recommend specific cost reduction actions

IMPORTANT RULES:
- Always use real data from tools — never estimate costs without running analysis
- Explain the ToU rate structure when relevant (peak 9AM-6PM, off-peak rest)
- Highlight demand charges separately — they're 30-40% of commercial bills
- Weekend discount is 15% — mention if weekend load shifting could help
- Give specific INR figures — executives need numbers, not percentages"""


class CostAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            name="CostAgent",
            role="Cost Analysis Specialist",
            system_prompt=SYSTEM_PROMPT,
        )
        for tool in get_all_tools():
            if tool.name in (
                "run_cost_analysis", "query_facility_stats",
                "query_all_facilities", "run_optimization_opportunity",
            ):
                self.register_tool(tool)

    def analyze(self, facility_id: str = "office") -> str:
        return self.run(
            f"Analyze energy costs for the {facility_id} facility. "
            f"Break down the costs, identify the biggest cost drivers, "
            f"and recommend specific ways to reduce the electricity bill."
        )
