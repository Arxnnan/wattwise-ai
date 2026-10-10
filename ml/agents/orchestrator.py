"""WattWise AI — Multi-Agent Orchestrator.

Coordinates the 4 specialist agents and routes queries to the right expert.
Can run autonomous monitoring sweeps or answer specific user questions.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from ml.agents.base import BaseAgent, AgentTool
from ml.agents.anomaly_agent import AnomalyAgent
from ml.agents.forecast_agent import ForecastAgent
from ml.agents.cost_agent import CostAgent
from ml.agents.optimizer_agent import OptimizerAgent

log = logging.getLogger(__name__)


@dataclass
class AgentReport:
    agent_name: str
    facility_id: str
    summary: str
    timestamp: datetime


class EnergyOrchestrator:
    """Coordinates specialist agents to provide comprehensive energy intelligence."""

    def __init__(self):
        self.anomaly_agent = AnomalyAgent()
        self.forecast_agent = ForecastAgent()
        self.cost_agent = CostAgent()
        self.optimizer_agent = OptimizerAgent()
        self.reports: list[AgentReport] = []

    def _route_query(self, query: str) -> list[BaseAgent]:
        """Determine which agent(s) should handle a query."""
        q = query.lower()
        agents = []

        if any(w in q for w in ["anomaly", "anomalies", "unusual", "fault",
                                  "spike", "abnormal", "outlier", "weird"]):
            agents.append(self.anomaly_agent)

        if any(w in q for w in ["forecast", "predict", "future", "tomorrow",
                                  "next", "upcoming", "will demand"]):
            agents.append(self.forecast_agent)

        if any(w in q for w in ["cost", "bill", "expense", "price", "rate",
                                  "inr", "rupee", "money", "budget", "save"]):
            agents.append(self.cost_agent)

        if any(w in q for w in ["optimize", "optimization", "peak", "shed",
                                  "reduce", "load", "efficiency", "shave"]):
            agents.append(self.optimizer_agent)

        if not agents:
            agents = [self.anomaly_agent, self.forecast_agent,
                      self.cost_agent, self.optimizer_agent]

        return agents

    def ask(self, query: str, facility_id: str = "office") -> str:
        """Route a user query to the right specialist agent(s)."""
        agents = self._route_query(query)

        if len(agents) == 1:
            response = agents[0].run(query)
            self.reports.append(AgentReport(
                agent_name=agents[0].name, facility_id=facility_id,
                summary=response, timestamp=datetime.now(timezone.utc),
            ))
            return f"**{agents[0].name}:**\n{response}"

        responses = []
        for agent in agents:
            try:
                response = agent.run(query)
                self.reports.append(AgentReport(
                    agent_name=agent.name, facility_id=facility_id,
                    summary=response, timestamp=datetime.now(timezone.utc),
                ))
                responses.append(f"**{agent.name}:**\n{response}")
            except Exception as e:
                responses.append(f"**{agent.name}:** Error — {e}")
                log.error("[Orchestrator] %s failed: %s", agent.name, e)

        return "\n\n---\n\n".join(responses)

    def full_sweep(self, facility_id: str = "office") -> dict[str, str]:
        """Run all 4 agents on a facility — comprehensive health check."""
        results = {}

        log.info("[Orchestrator] Starting full sweep for %s", facility_id)

        results["anomalies"] = self.anomaly_agent.monitor(facility_id)
        self.reports.append(AgentReport(
            agent_name="AnomalyAgent", facility_id=facility_id,
            summary=results["anomalies"], timestamp=datetime.now(timezone.utc),
        ))

        results["forecast"] = self.forecast_agent.predict(facility_id)
        self.reports.append(AgentReport(
            agent_name="ForecastAgent", facility_id=facility_id,
            summary=results["forecast"], timestamp=datetime.now(timezone.utc),
        ))

        results["costs"] = self.cost_agent.analyze(facility_id)
        self.reports.append(AgentReport(
            agent_name="CostAgent", facility_id=facility_id,
            summary=results["costs"], timestamp=datetime.now(timezone.utc),
        ))

        results["optimization"] = self.optimizer_agent.optimize(facility_id)
        self.reports.append(AgentReport(
            agent_name="OptimizerAgent", facility_id=facility_id,
            summary=results["optimization"], timestamp=datetime.now(timezone.utc),
        ))

        log.info("[Orchestrator] Full sweep complete for %s", facility_id)
        return results

    def get_report_history(self) -> list[dict]:
        """Get all agent reports from this session."""
        return [
            {
                "agent": r.agent_name,
                "facility": r.facility_id,
                "summary": r.summary[:200],
                "timestamp": r.timestamp.isoformat(),
            }
            for r in self.reports
        ]
