"""Tests for CriticAgent parsing and retry logic."""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from government.agents.critic import CriticAgent
from government.models.assessment import Assessment, CriticReport, Verdict
from government.models.decision import GovernmentDecision


@pytest.fixture
def agent() -> CriticAgent:
    return CriticAgent()


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


VALID_REPORT_JSON = json.dumps({
    "decision_id": "test-001",
    "decision_score": 7,
    "assessment_quality_score": 8,
    "blind_spots": ["Small business impact"],
    "overall_analysis": "Solid decision with minor gaps.",
    "headline": "Fiscal reform on track but gaps remain",
})


class TestParseResponse:
    def test_valid_json(self, agent: CriticAgent) -> None:
        result = agent._parse_response(VALID_REPORT_JSON, "test-001")
        assert isinstance(result, CriticReport)
        assert result.decision_score == 7
        assert result.assessment_quality_score == 8

    def test_json_with_surrounding_text(self, agent: CriticAgent) -> None:
        text = f"My analysis:\n{VALID_REPORT_JSON}\nDone."
        result = agent._parse_response(text, "test-001")
        assert result.decision_score == 7

    def test_no_json_returns_fallback(self, agent: CriticAgent) -> None:
        text = "I'll analyze this decision package thoroughly."
        result = agent._parse_response(text, "test-001")
        assert result.decision_score == 5
        assert result.headline == "Analiza u toku"

    def test_empty_response_returns_fallback(self, agent: CriticAgent) -> None:
        result = agent._parse_response("", "test-001")
        assert result.decision_score == 5


class TestReviewRetry:
    @pytest.mark.anyio
    async def test_success_on_first_try(
        self,
        agent: CriticAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = VALID_REPORT_JSON
            result = await agent.review(decision, assessments)

        assert result.decision_score == 7
        assert mock_call.call_count == 1

    @pytest.mark.anyio
    async def test_retry_on_preamble_response(
        self,
        agent: CriticAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = [
                "I'll analyze this thoroughly...",
                VALID_REPORT_JSON,
            ]
            result = await agent.review(decision, assessments)

        assert result.decision_score == 7
        assert mock_call.call_count == 2

    @pytest.mark.anyio
    async def test_fallback_after_all_retries_exhausted(
        self,
        agent: CriticAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "I'll cross-reference the assessments."
            result = await agent.review(decision, assessments)

        assert result.decision_score == 5
        assert result.headline == "Analiza u toku"
        assert mock_call.call_count == 2
