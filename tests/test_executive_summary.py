"""Tests for executive_summary field in Assessment model."""

from __future__ import annotations

from government.models.assessment import Assessment, Verdict


class TestExecutiveSummary:
    """Test the executive_summary field in Assessment model."""

    def test_assessment_with_executive_summary(self) -> None:
        """Test creating an Assessment with executive_summary."""
        exec_summary = (
            "Verdict: Negative. Top concern: no budget impact analysis. "
            "Recommendation: require full fiscal impact statement."
        )
        assessment = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.NEGATIVE,
            score=4,
            summary="This decision lacks fiscal transparency.",
            executive_summary=exec_summary,
            reasoning="The decision proposes spending without budget allocation...",
            key_concerns=["No budget allocation", "Missing fiscal impact analysis"],
            recommendations=["Require fiscal impact statement"],
        )
        assert assessment.executive_summary == exec_summary

    def test_assessment_without_executive_summary(self) -> None:
        """Test creating an Assessment without executive_summary (optional field)."""
        assessment = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=8,
            summary="This decision is fiscally sound.",
            reasoning="The decision includes proper budget allocation...",
        )
        assert assessment.executive_summary is None

    def test_json_roundtrip_with_executive_summary(self) -> None:
        """Test JSON serialization with executive_summary."""
        exec_summary = (
            "Verdict: Neutral. Improves primary care but underfunds specialists. "
            "Recommendation: increase specialist funding by 20%."
        )
        assessment = Assessment(
            ministry="Health",
            decision_id="test-002",
            verdict=Verdict.NEUTRAL,
            score=6,
            summary="Mixed impact on healthcare system.",
            executive_summary=exec_summary,
            reasoning="The decision allocates funds to primary care...",
            key_concerns=["Underfunded specialists"],
            recommendations=["Increase specialist funding"],
        )
        json_str = assessment.model_dump_json()
        restored = Assessment.model_validate_json(json_str)
        assert restored.executive_summary == exec_summary
        assert restored.ministry == "Health"
        assert restored.verdict == Verdict.NEUTRAL

    def test_json_roundtrip_without_executive_summary(self) -> None:
        """Test JSON serialization without executive_summary."""
        assessment = Assessment(
            ministry="Education",
            decision_id="test-003",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Positive impact on education.",
            reasoning="This decision improves school infrastructure...",
        )
        json_str = assessment.model_dump_json()
        restored = Assessment.model_validate_json(json_str)
        assert restored.executive_summary is None
        assert restored.ministry == "Education"
