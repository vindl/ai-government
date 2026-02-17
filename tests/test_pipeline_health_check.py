"""Tests for pipeline health check functionality."""

from datetime import date

from government.models.assessment import (
    Assessment,
    CounterProposal,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from government.orchestrator import (
    PipelineHealthCheck,
    SessionResult,
    _is_fallback_assessment,
    _is_fallback_counter_proposal,
    _is_fallback_critic,
    _is_fallback_debate,
)


def _make_decision(decision_id: str = "test-001") -> GovernmentDecision:
    return GovernmentDecision(
        id=decision_id,
        title="Test Decision",
        summary="A test decision.",
        date=date(2025, 12, 15),
    )


def _make_good_assessment(ministry: str = "Finance", decision_id: str = "test-001") -> Assessment:
    return Assessment(
        ministry=ministry,
        decision_id=decision_id,
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Solid analysis with detailed reasoning.",
        reasoning="The decision has clear fiscal implications.",
        key_concerns=["Budget impact", "Revenue projection"],
        recommendations=["Monitor spending", "Quarterly review"],
    )


def _make_fallback_assessment(
    ministry: str = "Finance", decision_id: str = "test-001"
) -> Assessment:
    """Mimics the fallback from GovernmentAgent._parse_response."""
    return Assessment(
        ministry=ministry,
        decision_id=decision_id,
        verdict=Verdict.NEUTRAL,
        score=5,
        summary=f"Assessment by {ministry} could not be fully parsed.",
        reasoning="No response received.",
        key_concerns=["Response parsing failed"],
        recommendations=["Re-run assessment"],
    )


def _make_good_debate(decision_id: str = "test-001") -> ParliamentDebate:
    return ParliamentDebate(
        decision_id=decision_id,
        consensus_summary="Ministries agree on the core approach.",
        disagreements=["Fiscal impact disputed"],
        overall_verdict=Verdict.POSITIVE,
        debate_transcript="A substantive debate transcript here.",
    )


def _make_fallback_debate(decision_id: str = "test-001") -> ParliamentDebate:
    return ParliamentDebate(
        decision_id=decision_id,
        consensus_summary="Debate could not be fully parsed.",
        disagreements=[],
        overall_verdict=Verdict.NEUTRAL,
        debate_transcript="No debate generated.",
    )


def _make_good_critic(decision_id: str = "test-001") -> CriticReport:
    return CriticReport(
        decision_id=decision_id,
        decision_score=7,
        assessment_quality_score=6,
        blind_spots=["Impact on small businesses"],
        overall_analysis="A thorough and well-structured analysis.",
        headline="Strong reform with caveats",
    )


def _make_fallback_critic(decision_id: str = "test-001") -> CriticReport:
    return CriticReport(
        decision_id=decision_id,
        decision_score=5,
        assessment_quality_score=5,
        blind_spots=["Review could not be fully parsed"],
        overall_analysis="No review generated.",
        headline="Analiza u toku",
    )


def _make_good_counter_proposal(decision_id: str = "test-001") -> CounterProposal:
    return CounterProposal(
        decision_id=decision_id,
        title="Alternative Approach",
        executive_summary="A detailed alternative approach.",
        detailed_proposal="Full proposal text here.",
        ministry_contributions=["Finance: budget analysis", "Justice: legal review"],
    )


def _make_fallback_counter_proposal(decision_id: str = "test-001") -> CounterProposal:
    return CounterProposal(
        decision_id=decision_id,
        title="Counter-proposal in preparation",
        executive_summary="Synthesis not generated.",
        detailed_proposal="Synthesis of ministry counter-proposals failed.",
        ministry_contributions=["Response parsing failed"],
    )


class TestFallbackDetection:
    """Test individual fallback detection functions."""

    def test_good_assessment_not_fallback(self) -> None:
        assert not _is_fallback_assessment(_make_good_assessment())

    def test_fallback_assessment_detected(self) -> None:
        assert _is_fallback_assessment(_make_fallback_assessment())

    def test_assessment_with_no_response_marker(self) -> None:
        a = Assessment(
            ministry="Test",
            decision_id="x",
            verdict=Verdict.NEUTRAL,
            score=5,
            summary="Some summary",
            reasoning="No response received.",
            key_concerns=[],
            recommendations=[],
        )
        assert _is_fallback_assessment(a)

    def test_good_debate_not_fallback(self) -> None:
        assert not _is_fallback_debate(_make_good_debate())

    def test_fallback_debate_detected(self) -> None:
        assert _is_fallback_debate(_make_fallback_debate())

    def test_none_debate_is_fallback(self) -> None:
        assert _is_fallback_debate(None)

    def test_good_critic_not_fallback(self) -> None:
        assert not _is_fallback_critic(_make_good_critic())

    def test_fallback_critic_detected(self) -> None:
        assert _is_fallback_critic(_make_fallback_critic())

    def test_none_critic_is_fallback(self) -> None:
        assert _is_fallback_critic(None)

    def test_good_counter_proposal_not_fallback(self) -> None:
        assert not _is_fallback_counter_proposal(_make_good_counter_proposal())

    def test_fallback_counter_proposal_detected(self) -> None:
        assert _is_fallback_counter_proposal(_make_fallback_counter_proposal())

    def test_none_counter_proposal_is_fallback(self) -> None:
        assert _is_fallback_counter_proposal(None)


class TestPipelineHealthCheck:
    """Test SessionResult.check_health()."""

    def test_all_healthy_passes(self) -> None:
        """Fully healthy analysis should pass."""
        result = SessionResult(
            decision=_make_decision(),
            assessments=[_make_good_assessment(m) for m in [
                "Finance", "Justice", "EU Integration", "Health",
                "Interior", "Education", "Economy", "Tourism", "Environment",
            ]],
            debate=_make_good_debate(),
            critic_report=_make_good_critic(),
            counter_proposal=_make_good_counter_proposal(),
        )
        health = result.check_health()
        assert health.passed is True
        assert health.failed_assessments == 0
        assert health.total_assessments == 9
        assert health.debate_failed is False
        assert health.critic_failed is False
        assert health.counter_proposal_failed is False
        assert health.failures == []

    def test_all_assessments_failed_blocks(self) -> None:
        """When all assessments are fallbacks, health check should fail."""
        result = SessionResult(
            decision=_make_decision(),
            assessments=[_make_fallback_assessment(m) for m in [
                "Finance", "Justice", "EU Integration", "Health",
                "Interior", "Education", "Economy", "Tourism", "Environment",
            ]],
            debate=_make_fallback_debate(),
            critic_report=_make_fallback_critic(),
            counter_proposal=_make_fallback_counter_proposal(),
        )
        health = result.check_health()
        assert health.passed is False
        assert health.failed_assessments == 9
        assert health.total_assessments == 9
        assert health.debate_failed is True
        assert health.critic_failed is True
        assert health.counter_proposal_failed is True
        assert len(health.failures) > 0
        assert any("All 9" in f for f in health.failures)

    def test_no_assessments_fails(self) -> None:
        """Empty assessments list should fail health check."""
        result = SessionResult(
            decision=_make_decision(),
            assessments=[],
        )
        health = result.check_health()
        assert health.passed is False
        assert any("No ministry assessments" in f for f in health.failures)

    def test_majority_failed_blocks(self) -> None:
        """When more than half of assessments are fallbacks, should fail."""
        assessments = [_make_good_assessment("Finance")] + [
            _make_fallback_assessment(m) for m in [
                "Justice", "EU Integration", "Health",
                "Interior", "Education", "Economy", "Tourism", "Environment",
            ]
        ]
        result = SessionResult(
            decision=_make_decision(),
            assessments=assessments,
            debate=_make_good_debate(),
            critic_report=_make_good_critic(),
            counter_proposal=_make_good_counter_proposal(),
        )
        health = result.check_health()
        assert health.passed is False
        assert health.failed_assessments == 8

    def test_minority_failed_passes(self) -> None:
        """When fewer than half fail, health check should pass."""
        assessments = [
            _make_fallback_assessment("Finance"),
            _make_good_assessment("Justice"),
            _make_good_assessment("EU Integration"),
            _make_good_assessment("Health"),
            _make_good_assessment("Interior"),
        ]
        result = SessionResult(
            decision=_make_decision(),
            assessments=assessments,
            debate=_make_good_debate(),
            critic_report=_make_good_critic(),
            counter_proposal=_make_good_counter_proposal(),
        )
        health = result.check_health()
        assert health.passed is True
        assert health.failed_assessments == 1

    def test_exactly_half_failed_passes(self) -> None:
        """When exactly half fail (4/8), should still pass (4 <= 8//2 = 4)."""
        assessments = (
            [_make_fallback_assessment(f"Bad{i}") for i in range(4)]
            + [_make_good_assessment(f"Good{i}") for i in range(4)]
        )
        result = SessionResult(
            decision=_make_decision(),
            assessments=assessments,
            debate=_make_good_debate(),
            critic_report=_make_good_critic(),
            counter_proposal=_make_good_counter_proposal(),
        )
        health = result.check_health()
        assert health.passed is True
        assert health.failed_assessments == 4

    def test_component_failures_noted_but_dont_block(self) -> None:
        """Debate/critic/cp failures should be noted but not block on their own."""
        result = SessionResult(
            decision=_make_decision(),
            assessments=[_make_good_assessment("Finance")],
            debate=_make_fallback_debate(),
            critic_report=_make_fallback_critic(),
            counter_proposal=_make_fallback_counter_proposal(),
        )
        health = result.check_health()
        # Passes because assessments are healthy
        assert health.passed is True
        assert health.debate_failed is True
        assert health.critic_failed is True
        assert health.counter_proposal_failed is True
        # Failures are listed as warnings
        assert len(health.failures) == 3

    def test_health_check_returns_pydantic_model(self) -> None:
        """Health check result should be a proper Pydantic model."""
        result = SessionResult(decision=_make_decision(), assessments=[])
        health = result.check_health()
        assert isinstance(health, PipelineHealthCheck)
        # Should be serializable
        data = health.model_dump()
        restored = PipelineHealthCheck.model_validate(data)
        assert restored.passed == health.passed
