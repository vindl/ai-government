"""Tests that agents do NOT pass betas to ClaudeAgentOptions.

The context-1m beta was removed because OAuth users cannot use custom betas —
the SDK warns and may return empty ResultMessage responses.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from government.agents.base import GovernmentAgent, MinistryConfig

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions
from government.agents.critic import CriticAgent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent
from government.models.assessment import Assessment, Verdict
from government.models.decision import GovernmentDecision


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


class TestGovernmentAgentNoBeta:
    """GovernmentAgent.analyze() should NOT pass betas to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_no_betas_in_options(self, decision: GovernmentDecision) -> None:
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
        assert not captured_opts[0].betas


class TestParliamentAgentNoBeta:
    """ParliamentAgent._call_model() should NOT pass betas."""

    @pytest.mark.anyio
    async def test_no_betas_in_options(self) -> None:
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
        assert not captured_opts[0].betas


class TestSynthesizerAgentNoBeta:
    """SynthesizerAgent._call_model() should NOT pass betas."""

    @pytest.mark.anyio
    async def test_no_betas_in_options(self) -> None:
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
        assert not captured_opts[0].betas


class TestCriticAgentNoBeta:
    """CriticAgent._call_model() should NOT pass betas."""

    @pytest.mark.anyio
    async def test_no_betas_in_options(self) -> None:
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
        assert not captured_opts[0].betas
