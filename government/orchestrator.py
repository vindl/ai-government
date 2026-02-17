"""Orchestrator — coordinates all ministry subagents for a cabinet session."""

from __future__ import annotations

import logging
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
from government.agents.ministry_labour import create_labour_agent
from government.agents.ministry_tourism import create_tourism_agent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent
from government.config import SessionConfig
from government.models.assessment import Assessment, CounterProposal, CriticReport, ParliamentDebate
from government.models.decision import GovernmentDecision

if TYPE_CHECKING:
    from government.agents.base import GovernmentAgent

log = logging.getLogger(__name__)

# Sentinel strings used in agent fallbacks to detect failed responses.
FALLBACK_MARKERS: frozenset[str] = frozenset({
    "could not be fully parsed",
    "No response received",
    "Response parsing failed",
    "No debate generated",
    "No review generated",
    "Synthesis not generated",
    "Synthesis of ministry counter-proposals failed",
    "Analiza u toku",
})


def _is_fallback_assessment(assessment: Assessment) -> bool:
    """Return True if the assessment looks like an agent fallback."""
    text = f"{assessment.summary} {assessment.reasoning} {' '.join(assessment.key_concerns)}"
    return any(marker in text for marker in FALLBACK_MARKERS)


def _is_fallback_debate(debate: ParliamentDebate | None) -> bool:
    """Return True if the debate is missing or a fallback."""
    if debate is None:
        return True
    text = f"{debate.consensus_summary} {debate.debate_transcript}"
    return any(marker in text for marker in FALLBACK_MARKERS)


def _is_fallback_critic(report: CriticReport | None) -> bool:
    """Return True if the critic report is missing or a fallback."""
    if report is None:
        return True
    text = f"{report.overall_analysis} {report.headline} {' '.join(report.blind_spots)}"
    return any(marker in text for marker in FALLBACK_MARKERS)


def _is_fallback_counter_proposal(proposal: CounterProposal | None) -> bool:
    """Return True if the counter-proposal is missing or a fallback."""
    if proposal is None:
        return True
    text = (
        f"{proposal.executive_summary} {proposal.detailed_proposal} "
        f"{' '.join(proposal.ministry_contributions)}"
    )
    return any(marker in text for marker in FALLBACK_MARKERS)


class PipelineHealthCheck(BaseModel):
    """Result of a pipeline health check on a SessionResult."""

    passed: bool = Field(description="Whether the analysis is healthy enough to publish")
    failed_assessments: int = Field(description="Number of ministry assessments that failed")
    total_assessments: int = Field(description="Total number of ministry assessments")
    debate_failed: bool = Field(description="Whether the parliament debate failed")
    critic_failed: bool = Field(description="Whether the critic report failed")
    counter_proposal_failed: bool = Field(description="Whether the counter-proposal failed")
    failures: list[str] = Field(default_factory=list, description="List of failure descriptions")


class SessionResult(BaseModel):
    """Complete result of a cabinet session for one decision."""

    decision: GovernmentDecision
    assessments: list[Assessment] = Field(default_factory=list)
    debate: ParliamentDebate | None = None
    critic_report: CriticReport | None = None
    counter_proposal: CounterProposal | None = None

    def check_health(self) -> PipelineHealthCheck:
        """Validate that the pipeline produced substantive output.

        Returns a PipelineHealthCheck indicating whether the analysis is
        healthy enough to publish. A result is considered unhealthy (and
        should not be published) when the majority of assessments are
        fallbacks, signaling a systemic pipeline failure.
        """
        failed_assessments = sum(
            1 for a in self.assessments if _is_fallback_assessment(a)
        )
        total = len(self.assessments)
        debate_failed = _is_fallback_debate(self.debate)
        critic_failed = _is_fallback_critic(self.critic_report)
        cp_failed = _is_fallback_counter_proposal(self.counter_proposal)

        failures: list[str] = []

        if total == 0:
            failures.append("No ministry assessments were produced")
        elif failed_assessments == total:
            failures.append(
                f"All {total} ministry assessments failed (fallback responses)"
            )
        elif failed_assessments > total // 2:
            failures.append(
                f"{failed_assessments}/{total} ministry assessments failed "
                f"(majority are fallback responses)"
            )

        if debate_failed:
            failures.append("Parliament debate is missing or a fallback")
        if critic_failed:
            failures.append("Critic report is missing or a fallback")
        if cp_failed:
            failures.append("Counter-proposal is missing or a fallback")

        # The pipeline fails health check when the majority of assessments
        # are fallbacks. Individual component failures (debate, critic,
        # counter-proposal) are noted but don't alone block publishing.
        passed = (
            total > 0
            and failed_assessments <= total // 2
        )

        return PipelineHealthCheck(
            passed=passed,
            failed_assessments=failed_assessments,
            total_assessments=total,
            debate_failed=debate_failed,
            critic_failed=critic_failed,
            counter_proposal_failed=cp_failed,
            failures=failures,
        )


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
            create_labour_agent(self.config),
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
                    decision, result.assessments, effort="high",
                )

            async def run_critic() -> None:
                result.critic_report = await self.critic.review(
                    decision, result.assessments, effort="high",
                )

            tg.start_soon(run_parliament)
            tg.start_soon(run_critic)

        # Phase 3: Synthesize unified counter-proposal
        result.counter_proposal = await self.synthesizer.synthesize(
            decision, result.assessments, effort="high",
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
                    assessment = await a.analyze(decision, effort="medium")
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
            assessment = await agent.analyze(decision, effort="medium")
            assessments.append(assessment)
        return assessments
