"""Tests for ParliamentAgent parsing and structured output."""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from government.agents.parliament import ParliamentAgent
from government.models.assessment import Assessment, ParliamentDebate, Verdict
from government.models.decision import GovernmentDecision
from government.prompts.parliament import PARLIAMENT_SYSTEM_PROMPT


@pytest.fixture
def agent() -> ParliamentAgent:
    return ParliamentAgent()


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


VALID_DEBATE_DATA = {
    "decision_id": "test-001",
    "consensus_summary": "All ministries agree on fiscal prudence.",
    "disagreements": ["Budget allocation approach"],
    "overall_verdict": "positive",
    "debate_transcript": "Finance argues for spending controls...",
}

VALID_DEBATE_JSON = json.dumps(VALID_DEBATE_DATA)


class TestParliamentaryLandscape:
    """Test that the prompt includes real Montenegrin parliamentary parties."""

    def test_prompt_contains_parliamentary_landscape_section(self) -> None:
        assert "## Parliamentary Landscape" in PARLIAMENT_SYSTEM_PROMPT

    @pytest.mark.parametrize(
        "party",
        [
            "DPS",
            "SDP",
            "Europe Now!",
            "URA",
            "Demokratski front",
            "DNP",
            "Bošnjačka stranka",
        ],
    )
    def test_prompt_mentions_major_parties(self, party: str) -> None:
        assert party in PARLIAMENT_SYSTEM_PROMPT

    def test_prompt_includes_policy_orientations(self) -> None:
        assert "pro-EU" in PARLIAMENT_SYSTEM_PROMPT
        assert "sovereigntist" in PARLIAMENT_SYSTEM_PROMPT
        assert "pro-Serbian" in PARLIAMENT_SYSTEM_PROMPT

    def test_prompt_instructs_party_bloc_attribution(self) -> None:
        assert "party blocs or coalitions" in PARLIAMENT_SYSTEM_PROMPT
        assert "never to individual politicians" in PARLIAMENT_SYSTEM_PROMPT

    def test_prompt_instructs_debate_transcript_usage(self) -> None:
        assert "debate_transcript" in PARLIAMENT_SYSTEM_PROMPT

    def test_json_output_format_unchanged(self) -> None:
        """Verify the JSON response format spec is still present and unchanged."""
        assert '"decision_id"' in PARLIAMENT_SYSTEM_PROMPT
        assert '"consensus_summary"' in PARLIAMENT_SYSTEM_PROMPT
        assert '"disagreements"' in PARLIAMENT_SYSTEM_PROMPT
        assert '"overall_verdict"' in PARLIAMENT_SYSTEM_PROMPT
        assert '"debate_transcript"' in PARLIAMENT_SYSTEM_PROMPT


class TestParseResponse:
    """Test legacy _parse_response (uses extract_json for backward compat)."""

    def test_valid_json(self, agent: ParliamentAgent) -> None:
        result = agent._parse_response(VALID_DEBATE_JSON, "test-001")
        assert isinstance(result, ParliamentDebate)
        assert result.overall_verdict == Verdict.POSITIVE
        assert len(result.disagreements) == 1

    def test_json_with_surrounding_text(self, agent: ParliamentAgent) -> None:
        text = f"Here is the debate:\n{VALID_DEBATE_JSON}\nEnd."
        result = agent._parse_response(text, "test-001")
        assert result.overall_verdict == Verdict.POSITIVE

    def test_no_json_returns_fallback(self, agent: ParliamentAgent) -> None:
        text = "I'll analyze the assessments and synthesize a debate."
        result = agent._parse_response(text, "test-001")
        assert result.consensus_summary == "Debate could not be fully parsed."
        assert result.overall_verdict == Verdict.NEUTRAL

    def test_empty_response_returns_fallback(self, agent: ParliamentAgent) -> None:
        result = agent._parse_response("", "test-001")
        assert result.consensus_summary == "Debate could not be fully parsed."


class TestBuildDebate:
    def test_builds_from_dict(self, agent: ParliamentAgent) -> None:
        result = agent._build_debate(dict(VALID_DEBATE_DATA), "test-001")
        assert isinstance(result, ParliamentDebate)
        assert result.overall_verdict == Verdict.POSITIVE

    def test_defaults_decision_id(self, agent: ParliamentAgent) -> None:
        data = {k: v for k, v in VALID_DEBATE_DATA.items() if k != "decision_id"}
        result = agent._build_debate(data, "test-099")
        assert result.decision_id == "test-099"


class TestDebateStructuredOutput:
    @pytest.mark.anyio
    async def test_success(
        self,
        agent: ParliamentAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = dict(VALID_DEBATE_DATA)
            result = await agent.debate(decision, assessments)

        assert result.overall_verdict == Verdict.POSITIVE
        assert mock_call.call_count == 1

    @pytest.mark.anyio
    async def test_fallback_on_none(
        self,
        agent: ParliamentAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = None
            result = await agent.debate(decision, assessments)

        assert result.consensus_summary == "Debate could not be fully parsed."
        assert mock_call.call_count == 1
