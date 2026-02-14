"""Tests for assessment models including counter-proposals."""

from ai_government.models.assessment import (
    Assessment,
    CounterProposal,
    MinistryCounterProposal,
    Verdict,
)


class TestMinistryCounterProposal:
    def test_create(self) -> None:
        cp = MinistryCounterProposal(
            title="Alternative",
            summary="A different approach.",
            key_changes=["Change 1"],
            expected_benefits=["Benefit 1"],
            estimated_feasibility="High",
        )
        assert cp.title == "Alternative"
        assert len(cp.key_changes) == 1

    def test_json_roundtrip(self) -> None:
        cp = MinistryCounterProposal(
            title="Test",
            summary="Summary",
            key_changes=["A", "B"],
            expected_benefits=["X"],
            estimated_feasibility="Medium",
        )
        json_str = cp.model_dump_json()
        restored = MinistryCounterProposal.model_validate_json(json_str)
        assert restored == cp

    def test_minimal_creation(self) -> None:
        cp = MinistryCounterProposal(title="Minimal", summary="Just basics.")
        assert cp.key_changes == []
        assert cp.expected_benefits == []
        assert cp.estimated_feasibility == ""


class TestAssessmentWithCounterProposal:
    def test_backwards_compat(self) -> None:
        """Assessment without counter_proposal still works."""
        a = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good.",
            reasoning="Solid.",
        )
        assert a.counter_proposal is None

    def test_with_counter_proposal(self) -> None:
        cp = MinistryCounterProposal(title="Alt", summary="Different.")
        a = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good.",
            reasoning="Solid.",
            counter_proposal=cp,
        )
        assert a.counter_proposal is not None
        assert a.counter_proposal.title == "Alt"

    def test_json_roundtrip_with_counter_proposal(self) -> None:
        cp = MinistryCounterProposal(
            title="Alt",
            summary="Different.",
            key_changes=["Change"],
        )
        a = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good.",
            reasoning="Solid.",
            counter_proposal=cp,
        )
        json_str = a.model_dump_json()
        restored = Assessment.model_validate_json(json_str)
        assert restored.counter_proposal is not None
        assert restored.counter_proposal.title == "Alt"

    def test_json_roundtrip_without_counter_proposal(self) -> None:
        a = Assessment(
            ministry="Finance",
            decision_id="test-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good.",
            reasoning="Solid.",
        )
        json_str = a.model_dump_json()
        restored = Assessment.model_validate_json(json_str)
        assert restored.counter_proposal is None


class TestCounterProposal:
    def test_create(self) -> None:
        cp = CounterProposal(
            decision_id="test-001",
            title="Unified Alternative",
            executive_summary="We would do this instead.",
            detailed_proposal="Full details here.",
            ministry_contributions=["Finance: fiscal plan"],
            key_differences=["Phased approach"],
            implementation_steps=["Step 1", "Step 2"],
            risks_and_tradeoffs=["Slower rollout"],
        )
        assert cp.decision_id == "test-001"
        assert len(cp.implementation_steps) == 2

    def test_json_roundtrip(self) -> None:
        cp = CounterProposal(
            decision_id="test-001",
            title="Test",
            executive_summary="Summary.",
            detailed_proposal="Details.",
            key_differences=["Diff 1"],
        )
        json_str = cp.model_dump_json()
        restored = CounterProposal.model_validate_json(json_str)
        assert restored == cp

    def test_minimal_creation(self) -> None:
        cp = CounterProposal(
            decision_id="test-001",
            title="Minimal",
            executive_summary="Brief.",
            detailed_proposal="Short.",
        )
        assert cp.ministry_contributions == []
        assert cp.key_differences == []
        assert cp.implementation_steps == []
        assert cp.risks_and_tradeoffs == []
