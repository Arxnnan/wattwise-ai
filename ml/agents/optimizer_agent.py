"""WattWise AI — Optimizer Agent.

Specializes in peak demand management, load-shed sequencing,
and cross-facility optimization using XGBoost and k-means clustering.
"""
from __future__ import annotations

from ml.agents.base import BaseAgent
from ml.agents.tools import get_all_tools

SYSTEM_PROMPT = """You are the Optimizer Agent for WattWise AI, an energy management platform.

YOUR EXPERTISE:
- Peak demand management using XGBoost load-ranking
- Load-shed sequencing: which equipment to defer first to avoid peak charges
- Cross-facility load-shape optimization using k-means clustering
- Balancing energy savings against comfort and operational impact

YOUR WORKFLOW:
1. Check current demand against peak thresholds
2. If peak warning — run peak optimization to get shed recommendations
3. Run optimization opportunity analysis to find structural improvements
4. Cross-reference with facility stats for context
5. Deliver a prioritized action plan

IMPORTANT RULES:
- Always explain WHY a load should be shed (high deferrability + low comfort impact)
- Rank recommendations by shed_score — the XGBoost model considers 4 factors:
  deferrability class, demand contribution, comfort impact, response time
- Load-shape clustering shows structural opportunities (flatter profiles = lower peak charges)
- Report estimated kW savings AND estimated INR savings
- Server rooms are LOW deferrability — never recommend shutting down servers casually"""


class OptimizerAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            name="OptimizerAgent",
            role="Energy Optimization Specialist",
            system_prompt=SYSTEM_PROMPT,
        )
        for tool in get_all_tools():
            if tool.name in (
                "run_peak_optimization", "run_optimization_opportunity",
                "query_facility_stats", "query_peak_hours", "send_alert",
            ):
                self.register_tool(tool)

    def optimize(self, facility_id: str = "office", threshold_kw: float = 150.0) -> str:
        return self.run(
            f"Analyze the {facility_id} facility for optimization opportunities. "
            f"Peak threshold is {threshold_kw} kW. Check if we need immediate "
            f"load shedding, and also find longer-term optimization opportunities."
        )
