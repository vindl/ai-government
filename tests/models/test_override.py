"""Tests for HumanOverride and HumanSuggestion models."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_government.models.override import HumanOverride, HumanSuggestion


def test_override_creation() -> None:
    """Test creating a HumanOverride instance."""
    override = HumanOverride(
        timestamp=datetime(2026, 2, 14, 12, 30, tzinfo=UTC),
        issue_number=123,
        pr_number=None,
        override_type="comment",
        actor="vindl",
        issue_title="Implement transparency report",
        ai_verdict="Rejected by AI triage",
        human_action="Moved to backlog via override",
        rationale="Important for constitutional compliance",
    )

    assert override.issue_number == 123
    assert override.pr_number is None
    assert override.override_type == "comment"
    assert override.actor == "vindl"
    assert override.rationale == "Important for constitutional compliance"


def test_override_with_pr() -> None:
    """Test override with PR number."""
    override = HumanOverride(
        timestamp=datetime(2026, 2, 14, 12, 30, tzinfo=UTC),
        issue_number=123,
        pr_number=456,
        override_type="pr_comment",
        actor="vindl",
        issue_title="Fix critical bug",
        ai_verdict="Changes requested by reviewer",
        human_action="Approved and merged",
        rationale="Security fix needed urgently",
    )

    assert override.pr_number == 456
    assert override.override_type == "pr_comment"


def test_override_without_rationale() -> None:
    """Test override without rationale (optional field)."""
    override = HumanOverride(
        timestamp=datetime(2026, 2, 14, 12, 30, tzinfo=UTC),
        issue_number=789,
        override_type="reopened",
        actor="vindl",
        issue_title="Add new feature",
        ai_verdict="Rejected by AI triage",
        human_action="Reopened and moved to backlog",
    )

    assert override.rationale is None
    assert override.override_type == "reopened"


def test_override_json_roundtrip() -> None:
    """Test JSON serialization and deserialization."""
    original = HumanOverride(
        timestamp=datetime(2026, 2, 14, 12, 30, tzinfo=UTC),
        issue_number=123,
        pr_number=None,
        override_type="comment",
        actor="vindl",
        issue_title="Test issue",
        ai_verdict="AI rejected",
        human_action="Human overrode",
        rationale="Testing JSON roundtrip",
    )

    # Serialize to JSON
    json_data = original.model_dump(mode="json")

    # Deserialize back
    restored = HumanOverride.model_validate(json_data)

    assert restored.issue_number == original.issue_number
    assert restored.actor == original.actor
    assert restored.rationale == original.rationale
    assert restored.timestamp == original.timestamp


def test_suggestion_creation() -> None:
    """Test creating a HumanSuggestion instance."""
    suggestion = HumanSuggestion(
        timestamp=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
        issue_number=200,
        issue_title="Add new analytics feature",
        status="open",
        creator="vindl",
    )

    assert suggestion.issue_number == 200
    assert suggestion.issue_title == "Add new analytics feature"
    assert suggestion.status == "open"
    assert suggestion.creator == "vindl"


def test_suggestion_closed_status() -> None:
    """Test suggestion with closed status."""
    suggestion = HumanSuggestion(
        timestamp=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
        issue_number=201,
        issue_title="Fix navigation bug",
        status="closed",
        creator="maintainer",
    )

    assert suggestion.status == "closed"


def test_suggestion_json_roundtrip() -> None:
    """Test JSON serialization and deserialization for HumanSuggestion."""
    original = HumanSuggestion(
        timestamp=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
        issue_number=202,
        issue_title="Implement feature X",
        status="open",
        creator="contributor",
    )

    # Serialize to JSON
    json_data = original.model_dump(mode="json")

    # Deserialize back
    restored = HumanSuggestion.model_validate(json_data)

    assert restored.issue_number == original.issue_number
    assert restored.issue_title == original.issue_title
    assert restored.status == original.status
    assert restored.creator == original.creator
    assert restored.timestamp == original.timestamp
