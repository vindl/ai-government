"""Orchestrator — coordinates all ministry subagents for a cabinet session."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel, Field

from government.agents.critic import CriticAgent
from government.agents.ministry_economy import create_economy_agent
from government.agents.ministry_education import create_education_agent
from government.agents.ministry_environment import create_environment_agent
from government.agents.ministry_eu import create_eu_agent
from government.agents.ministry_finance import create_finance_agent
from government.agents.ministry_health import create_health_agent
from government.agents.ministry_interior import create_interior_agent
from government.agents.ministry_justice import create_justice_agent
from government.agents.ministry_tourism import create_tourism_agent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent
from government.config import SessionConfig
from government.models.assessment import Assessment, CounterProposal, CriticReport, ParliamentDebate
from government.models.decision import GovernmentDecision

if TYPE_CHECKING:
    from government.agents.base import GovernmentAgent


class SessionResult(BaseModel):
    """Complete result of a cabinet session for one decision."""

    decision: GovernmentDecision
    assessments: list[Assessment] = Field(default_factory=list)
    debate: ParliamentDebate | None = None
    critic_report: CriticReport | None = None
    counter_proposal: CounterProposal | None = None


class Orchestrator:
    """Coordinates all ministry agents for a full cabinet session."""

    def __init__(self, config: SessionConfig | None = None) -> None:
        self.config = config or SessionConfig()
        self.ministry_agents: list[GovernmentAgent] = self._create_ministry_agents()
        self.parliament = ParliamentAgent(self.config)
        self.critic = CriticAgent(self.config)
        self.synthesizer = SynthesizerAgent(self.config)

    def _create_ministry_agents(self) -> list[GovernmentAgent]:
        return [
            create_finance_agent(self.config),
            create_justice_agent(self.config),
            create_eu_agent(self.config),
            create_health_agent(self.config),
            create_interior_agent(self.config),
            create_education_agent(self.config),
            create_economy_agent(self.config),
            create_tourism_agent(self.config),
            create_environment_agent(self.config),
        ]

    async def run_session(
        self,
        decisions: list[GovernmentDecision],
    ) -> list[SessionResult]:
        """Run a full cabinet session analyzing all provided decisions."""
        results: list[SessionResult] = []
        for decision in decisions:
            result = await self._analyze_decision(decision)
            results.append(result)
        return results

    async def _analyze_decision(self, decision: GovernmentDecision) -> SessionResult:
        """Analyze a single decision through all agents."""
        result = SessionResult(decision=decision)

        # Phase 1: Run all ministry agents in parallel
        if self.config.parallel_agents:
            result.assessments = await self._run_ministries_parallel(decision)
        else:
            result.assessments = await self._run_ministries_sequential(decision)

        # Phase 2: Parliament debate + Critic review (can run in parallel)
        async with anyio.create_task_group() as tg:

            async def run_parliament() -> None:
                result.debate = await self.parliament.debate(
                    decision, result.assessments
                )

            async def run_critic() -> None:
                result.critic_report = await self.critic.review(
                    decision, result.assessments
                )

            tg.start_soon(run_parliament)
            tg.start_soon(run_critic)

        # Phase 3: Synthesize unified counter-proposal
        result.counter_proposal = await self.synthesizer.synthesize(
            decision, result.assessments
        )

        return result

    async def _run_ministries_parallel(
        self,
        decision: GovernmentDecision,
    ) -> list[Assessment]:
        """Run all ministry agents in parallel."""
        assessments: list[Assessment] = []

        async with anyio.create_task_group() as tg:
            for agent in self.ministry_agents:

                async def analyze(a: GovernmentAgent = agent) -> None:
                    assessment = await a.analyze(decision)
                    assessments.append(assessment)

                tg.start_soon(analyze)

        return assessments

    async def _run_ministries_sequential(
        self,
        decision: GovernmentDecision,
    ) -> list[Assessment]:
        """Run ministry agents one at a time (for debugging/budget control)."""
        assessments: list[Assessment] = []
        for agent in self.ministry_agents:
            assessment = await agent.analyze(decision)
            assessments.append(assessment)
        return assessments
