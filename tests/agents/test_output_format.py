"""Tests for SDK output_format on government agents.

Verifies that each agent passes the correct JSON schema via ``output_format``
in ``ClaudeAgentOptions``, and that the ``output_format_for`` helper produces
the expected structure.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from government.agents.base import (
    GovernmentAgent,
    MinistryConfig,
    output_format_for,
)
from government.agents.critic import CriticAgent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent
from government.models.assessment import (
    Assessment,
    CounterProposal,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# output_format_for helper
# ---------------------------------------------------------------------------


class _Dummy(BaseModel):
    name: str = Field(description="a name")
    value: int = Field(default=0)


class TestOutputFormatFor:
    def test_returns_json_schema_type(self) -> None:
        result = output_format_for(_Dummy)
        assert result["type"] == "json_schema"

    def test_schema_key_contains_properties(self) -> None:
        result = output_format_for(_Dummy)
        schema = result["schema"]
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "value" in schema["properties"]

    def test_schema_matches_model_json_schema(self) -> None:
        result = output_format_for(_Dummy)
        assert result["schema"] == _Dummy.model_json_schema()

    def test_assessment_schema(self) -> None:
        result = output_format_for(Assessment)
        assert result["type"] == "json_schema"
        assert "verdict" in result["schema"]["properties"]

    def test_parliament_debate_schema(self) -> None:
        result = output_format_for(ParliamentDebate)
        assert "consensus_summary" in result["schema"]["properties"]

    def test_counter_proposal_schema(self) -> None:
        result = output_format_for(CounterProposal)
        assert "executive_summary" in result["schema"]["properties"]

    def test_critic_report_schema(self) -> None:
        result = output_format_for(CriticReport)
        assert "decision_score" in result["schema"]["properties"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def decision() -> GovernmentDecision:
    return GovernmentDecision(
        id="test-001",
        title="Test Decision",
        summary="A test decision.",
        date=date(2025, 12, 15),
    )


@pytest.fixture()
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


def _valid_assessment_data() -> dict[str, Any]:
    return {
        "ministry": "Finance",
        "decision_id": "test-001",
        "verdict": "positive",
        "score": 7,
        "summary": "Good decision.",
        "reasoning": "Solid reasoning.",
        "key_concerns": ["Budget impact"],
        "recommendations": ["Monitor spending"],
    }


def _valid_debate_data() -> dict[str, Any]:
    return {
        "decision_id": "test-001",
        "consensus_summary": "All agree.",
        "disagreements": [],
        "overall_verdict": "positive",
        "debate_transcript": "Transcript here.",
    }


def _valid_proposal_data() -> dict[str, Any]:
    return {
        "decision_id": "test-001",
        "title": "Unified Proposal",
        "executive_summary": "A summary.",
        "detailed_proposal": "Details.",
        "ministry_contributions": ["Finance"],
    }


def _valid_report_data() -> dict[str, Any]:
    return {
        "decision_id": "test-001",
        "decision_score": 7,
        "assessment_quality_score": 8,
        "blind_spots": [],
        "overall_analysis": "Analysis.",
        "headline": "Headline",
    }


# ---------------------------------------------------------------------------
# GovernmentAgent passes output_format with Assessment schema
# ---------------------------------------------------------------------------


class TestGovernmentAgentOutputFormat:
    @pytest.mark.anyio()
    async def test_options_include_output_format(
        self, decision: GovernmentDecision
    ) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)

        captured_opts: list[Any] = []

        async def fake_query(
            *_args: Any, prompt: str, options: Any, **_kwargs: Any
        ) -> Any:
            captured_opts.append(options)
            return
            yield  # noqa: RET503 — makes this an async generator

        with patch("government.agents.base.claude_agent_sdk.query", fake_query):
            await agent.analyze(decision)

        assert len(captured_opts) >= 1
        opts = captured_opts[0]
        assert opts.output_format is not None
        assert opts.output_format["type"] == "json_schema"
        assert opts.output_format["schema"] == Assessment.model_json_schema()


# ---------------------------------------------------------------------------
# ParliamentAgent passes output_format with ParliamentDebate schema
# ---------------------------------------------------------------------------


class TestParliamentAgentOutputFormat:
    @pytest.mark.anyio()
    async def test_options_include_output_format(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        agent = ParliamentAgent()
        captured_opts: list[Any] = []

        async def fake_query(
            *_args: Any, prompt: str, options: Any, **_kwargs: Any
        ) -> Any:
            captured_opts.append(options)
            return
            yield  # noqa: RET503

        with patch("government.agents.parliament.claude_agent_sdk.query", fake_query):
            await agent.debate(decision, assessments)

        assert len(captured_opts) >= 1
        opts = captured_opts[0]
        assert opts.output_format is not None
        assert opts.output_format["type"] == "json_schema"
        assert opts.output_format["schema"] == ParliamentDebate.model_json_schema()


# ---------------------------------------------------------------------------
# SynthesizerAgent passes output_format with CounterProposal schema
# ---------------------------------------------------------------------------


class TestSynthesizerAgentOutputFormat:
    @pytest.mark.anyio()
    async def test_options_include_output_format(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        agent = SynthesizerAgent()
        captured_opts: list[Any] = []

        async def fake_query(
            *_args: Any, prompt: str, options: Any, **_kwargs: Any
        ) -> Any:
            captured_opts.append(options)
            return
            yield  # noqa: RET503

        with patch("government.agents.synthesizer.claude_agent_sdk.query", fake_query):
            await agent.synthesize(decision, assessments)

        assert len(captured_opts) >= 1
        opts = captured_opts[0]
        assert opts.output_format is not None
        assert opts.output_format["type"] == "json_schema"
        assert opts.output_format["schema"] == CounterProposal.model_json_schema()


# ---------------------------------------------------------------------------
# CriticAgent passes output_format with CriticReport schema
# ---------------------------------------------------------------------------


class TestCriticAgentOutputFormat:
    @pytest.mark.anyio()
    async def test_options_include_output_format(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        agent = CriticAgent()
        captured_opts: list[Any] = []

        async def fake_query(
            *_args: Any, prompt: str, options: Any, **_kwargs: Any
        ) -> Any:
            captured_opts.append(options)
            return
            yield  # noqa: RET503

        with patch("government.agents.critic.claude_agent_sdk.query", fake_query):
            await agent.review(decision, assessments)

        assert len(captured_opts) >= 1
        opts = captured_opts[0]
        assert opts.output_format is not None
        assert opts.output_format["type"] == "json_schema"
        assert opts.output_format["schema"] == CriticReport.model_json_schema()
