"""Tests for CriticAgent parsing and structured output."""

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


VALID_REPORT_DATA = {
    "decision_id": "test-001",
    "decision_score": 7,
    "assessment_quality_score": 8,
    "blind_spots": ["Small business impact"],
    "overall_analysis": "Solid decision with minor gaps.",
    "headline": "Fiscal reform on track but gaps remain",
}

VALID_REPORT_JSON = json.dumps(VALID_REPORT_DATA)


class TestParseResponse:
    """Test legacy _parse_response (uses extract_json for backward compat)."""

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


class TestBuildReport:
    def test_builds_from_dict(self, agent: CriticAgent) -> None:
        result = agent._build_report(dict(VALID_REPORT_DATA), "test-001")
        assert isinstance(result, CriticReport)
        assert result.decision_score == 7

    def test_defaults_decision_id(self, agent: CriticAgent) -> None:
        data = {k: v for k, v in VALID_REPORT_DATA.items() if k != "decision_id"}
        result = agent._build_report(data, "test-099")
        assert result.decision_id == "test-099"


class TestCriticPrompt:
    """Tests that the critic prompt includes EU accession chapter data."""

    def test_prompt_contains_chapter_23(self) -> None:
        from government.prompts.critic import CRITIC_SYSTEM_PROMPT

        assert "Ch. 23" in CRITIC_SYSTEM_PROMPT or "23" in CRITIC_SYSTEM_PROMPT
        assert "Judiciary and Fundamental Rights" in CRITIC_SYSTEM_PROMPT

    def test_prompt_contains_eu_chapter_relevance_field(self) -> None:
        from government.prompts.critic import CRITIC_SYSTEM_PROMPT

        assert "eu_chapter_relevance" in CRITIC_SYSTEM_PROMPT

    def test_prompt_mentions_key_benchmark_chapters(self) -> None:
        from government.prompts.critic import CRITIC_SYSTEM_PROMPT

        assert "key benchmark chapter" in CRITIC_SYSTEM_PROMPT

    def test_thirteen_chapters_provisionally_closed(self) -> None:
        from government.prompts.critic import _EU_ACCESSION_CHAPTERS

        closed_count = _EU_ACCESSION_CHAPTERS.count("Provisionally closed")
        assert closed_count == 13

    def test_provisionally_closed_chapter_numbers(self) -> None:
        from government.prompts.critic import _EU_ACCESSION_CHAPTERS

        expected_closed = {3, 4, 5, 6, 7, 10, 11, 13, 20, 25, 26, 30, 32}
        import re

        closed_chapters: set[int] = set()
        for line in _EU_ACCESSION_CHAPTERS.splitlines():
            if "Provisionally closed" in line:
                match = re.match(r"\|\s*(\d+)\s*\|", line)
                if match:
                    closed_chapters.add(int(match.group(1)))
        assert closed_chapters == expected_closed

    def test_chapter_30_provisionally_closed(self) -> None:
        """Ch.30 External Relations was closed in 2017 but was missing before."""
        from government.prompts.critic import _EU_ACCESSION_CHAPTERS

        assert "| 30 | External Relations | Provisionally closed |" in _EU_ACCESSION_CHAPTERS

    def test_last_updated_january_2026(self) -> None:
        from government.prompts.critic import _EU_ACCESSION_CHAPTERS  # noqa: F811

        # The module-level comment has the date, but we check the constant too
        assert "13 of 33 chapters provisionally closed as of January 2026" in _EU_ACCESSION_CHAPTERS


class TestEuChapterRelevance:
    """Tests for the eu_chapter_relevance field on CriticReport."""

    def test_field_defaults_to_empty_list(self) -> None:
        report = CriticReport(**VALID_REPORT_DATA)
        assert report.eu_chapter_relevance == []

    def test_field_accepts_chapters(self) -> None:
        data = {
            **VALID_REPORT_DATA,
            "eu_chapter_relevance": [
                "Ch.23 Judiciary and Fundamental Rights — strengthens judicial independence",
                "Ch.32 Financial Control — improves audit mechanisms",
            ],
        }
        report = CriticReport(**data)
        assert len(report.eu_chapter_relevance) == 2
        assert "Ch.23" in report.eu_chapter_relevance[0]

    def test_field_roundtrips_through_parse(self, agent: CriticAgent) -> None:
        data = {
            **VALID_REPORT_DATA,
            "eu_chapter_relevance": ["Ch.27 Environment — sets emission targets"],
        }
        report_json = json.dumps(data)
        result = agent._parse_response(report_json, "test-001")
        assert result.eu_chapter_relevance == ["Ch.27 Environment — sets emission targets"]

    def test_fallback_has_empty_eu_chapters(self, agent: CriticAgent) -> None:
        result = agent._parse_response("not json", "test-001")
        assert result.eu_chapter_relevance == []


class TestReviewStructuredOutput:
    @pytest.mark.anyio
    async def test_success(
        self,
        agent: CriticAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = dict(VALID_REPORT_DATA)
            result = await agent.review(decision, assessments)

        assert result.decision_score == 7
        assert mock_call.call_count == 1

    @pytest.mark.anyio
    async def test_fallback_on_none(
        self,
        agent: CriticAgent,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> None:
        with patch.object(agent, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = None
            result = await agent.review(decision, assessments)

        assert result.decision_score == 5
        assert result.headline == "Analiza u toku"
        assert mock_call.call_count == 1
