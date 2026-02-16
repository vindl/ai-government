"""Tests for SynthesizerAgent parsing and structured output."""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from government.agents.synthesizer import SynthesizerAgent
from government.models.assessment import Assessment, CounterProposal, Verdict
from government.models.decision import GovernmentDecision


@pytest.fixture
def agent() -> SynthesizerAgent:
    return SynthesizerAgent()


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


VALID_PROPOSAL_DATA = {
    "decision_id": "test-001",
    "title": "Unified Fiscal Reform",
    "executive_summary": "A phased approach to VAT reform.",
    "detailed_proposal": "The proposal combines fiscal prudence with social justice.",
    "ministry_contributions": ["Finance: gradual rate reduction"],
    "key_differences": ["Gradual instead of one-time"],
    "implementation_steps": ["Phase 1: reduce to 15%"],
    "risks_and_tradeoffs": ["Slower citizen impact"],
}

VALID_PROPOSAL_JSON = json.dumps(VALID_PROPOSAL_DATA)


class TestParseResponse:
    """Test legacy _parse_response (uses extract_json for backward compat)."""

    def test_valid_json(self, agent: SynthesizerAgent) -> None:
        result = agent._parse_response(VALID_PROPOSAL_JSON, "test-001")
        assert isinstance(result, CounterProposal)
        assert result.title == "Unified Fiscal Reform"

    def test_json_with_surrounding_text(self, agent: SynthesizerAgent) -> None:
        text = f"Here is the synthesis:\n{VALID_PROPOSAL_JSON}\nComplete."
        result = agent._parse_response(text, "test-001")
        assert result.title == "Unified Fiscal Reform"

    def test_no_json_returns_fallback(self, agent: SynthesizerAgent) -> None:
        text = "I'll synthesize the counter-proposals into a unified policy."
        result = agent._parse_response(text, "test-001")
        assert result.title == "Counter-proposal in preparation"
        assert "failed" in result.detailed_proposal.lower()

    def test_empty_response_returns_fallback(self, agent: SynthesizerAgent) -> None:
        result = agent._parse_response("", "test-001")
        assert result.title == "Counter-proposal in preparation"


class TestBuildProposal:
    def test_builds_from_dict(self, agent: SynthesizerAgent) -> None:
        result = agent._build_proposal(dict(VALID_PROPOSAL_DATA), "test-001")
        assert isinstance(result, CounterProposal)
        assert result.title == "Unified Fiscal Reform"

    def test_defaults_decision_id(self, agent: SynthesizerAgent) -> None:
        data = {k: v for k, v in VALID_PROPOSAL_DATA.items() if k != "decision_id"}
        result = agent._build_proposal(data, "test-099")
        assert result.decision_id == "test-099"


class TestSynthesizeStructuredOutput:
    @pytest.mark.anyio
    async def test_success(
        self,
        agent: SynthesizerAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = dict(VALID_PROPOSAL_DATA)
            result = await agent.synthesize(decision, assessments)

        assert result.title == "Unified Fiscal Reform"
        assert mock_call.call_count == 1

    @pytest.mark.anyio
    async def test_fallback_on_none(
        self,
        agent: SynthesizerAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = None
            result = await agent.synthesize(decision, assessments)

        assert result.title == "Counter-proposal in preparation"
        assert mock_call.call_count == 1
