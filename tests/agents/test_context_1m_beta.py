"""Tests for 1M context window beta flag on all agents."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from government.agents.base import CONTEXT_1M_BETA, GovernmentAgent, MinistryConfig
from government.agents.critic import CriticAgent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent
from government.models.assessment import Assessment, Verdict
from government.models.decision import GovernmentDecision


class TestContext1MBetaConstant:
    """The CONTEXT_1M_BETA constant should be a valid beta identifier."""

    def test_is_non_empty_list(self) -> None:
        assert isinstance(CONTEXT_1M_BETA, list)
        assert len(CONTEXT_1M_BETA) == 1

    def test_contains_expected_beta_id(self) -> None:
        assert CONTEXT_1M_BETA == ["context-1m-2025-08-07"]

    def test_accepted_by_sdk(self) -> None:
        """ClaudeAgentOptions should accept the beta without error."""
        opts = ClaudeAgentOptions(betas=CONTEXT_1M_BETA)
        assert opts.betas == CONTEXT_1M_BETA


@pytest.fixture
def decision() -> GovernmentDecision:
    return GovernmentDecision(
        id="test-001",
        title="Test Decision",
        summary="A test decision.",
        date=date(2025, 12, 15),
    )


@pytest.fixture
def assessments() -> list[Assessment]:
    return [
        Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good decision.",
            reasoning="Solid reasoning.",
            key_concerns=["Budget impact"],
            recommendations=["Monitor spending"],
        ),
    ]


async def _empty_stream(*args: Any, **kwargs: Any) -> Any:
    """Async generator that yields nothing — stands in for claude_agent_sdk.query."""
    return
    yield  # pragma: no cover


class TestGovernmentAgentBeta:
    """GovernmentAgent.analyze() should pass betas to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_betas_passed_to_options(self, decision: GovernmentDecision) -> None:
        config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(config)

        captured_opts: list[ClaudeAgentOptions] = []

        async def capture_query(*args: Any, **kwargs: Any) -> Any:
            if "options" in kwargs:
                captured_opts.append(kwargs["options"])
            return
            yield  # pragma: no cover

        with patch("government.agents.base.claude_agent_sdk.query", capture_query):
            await agent.analyze(decision)

        assert len(captured_opts) >= 1
        assert captured_opts[0].betas == CONTEXT_1M_BETA


class TestParliamentAgentBeta:
    """ParliamentAgent._call_model() should pass betas to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_betas_passed_to_options(self) -> None:
        agent = ParliamentAgent()
        captured_opts: list[ClaudeAgentOptions] = []

        async def capture_query(*args: Any, **kwargs: Any) -> Any:
            if "options" in kwargs:
                captured_opts.append(kwargs["options"])
            return
            yield  # pragma: no cover

        with patch("government.agents.parliament.claude_agent_sdk.query", capture_query):
            await agent._call_model("test prompt")

        assert len(captured_opts) >= 1
        assert captured_opts[0].betas == CONTEXT_1M_BETA


class TestSynthesizerAgentBeta:
    """SynthesizerAgent._call_model() should pass betas to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_betas_passed_to_options(self) -> None:
        agent = SynthesizerAgent()
        captured_opts: list[ClaudeAgentOptions] = []

        async def capture_query(*args: Any, **kwargs: Any) -> Any:
            if "options" in kwargs:
                captured_opts.append(kwargs["options"])
            return
            yield  # pragma: no cover

        with patch("government.agents.synthesizer.claude_agent_sdk.query", capture_query):
            await agent._call_model("test prompt")

        assert len(captured_opts) >= 1
        assert captured_opts[0].betas == CONTEXT_1M_BETA


class TestCriticAgentBeta:
    """CriticAgent._call_model() should pass betas to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_betas_passed_to_options(self) -> None:
        agent = CriticAgent()
        captured_opts: list[ClaudeAgentOptions] = []

        async def capture_query(*args: Any, **kwargs: Any) -> Any:
            if "options" in kwargs:
                captured_opts.append(kwargs["options"])
            return
            yield  # pragma: no cover

        with patch("government.agents.critic.claude_agent_sdk.query", capture_query):
            await agent._call_model("test prompt")

        assert len(captured_opts) >= 1
        assert captured_opts[0].betas == CONTEXT_1M_BETA
