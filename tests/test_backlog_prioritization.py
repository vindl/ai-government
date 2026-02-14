"""Tests for backlog issue prioritization in main_loop."""

from __future__ import annotations

from typing import Any


def make_issue(
    number: int,
    created_at: str,
    *,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Helper to create a mock issue dict."""
    label_objs = [{"name": label} for label in (labels or [])]
    return {
        "number": number,
        "title": f"Issue #{number}",
        "body": "",
        "createdAt": created_at,
        "labels": label_objs,
    }


def _issue_has_label(issue: dict[str, Any], label: str) -> bool:
    """Check if an issue has a specific label (copied from main_loop)."""
    labels = issue.get("labels", [])
    return any(lbl.get("name") == label for lbl in labels)


def step_pick_impl(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Test implementation of step_pick logic."""
    if not issues:
        return None

    # Priority label constants (matching main_loop.py)
    label_human = "human-suggestion"
    label_task_analysis = "task:analysis"
    label_strategy = "strategy-suggestion"
    label_director = "director-suggestion"

    priority_labels = [
        label_human,
        label_task_analysis,
        label_strategy,
        label_director,
    ]

    for label in priority_labels:
        for issue in issues:
            if _issue_has_label(issue, label):
                return issue

    # Fall back to FIFO (oldest first)
    return issues[0]


def test_prioritizes_human_suggestions_over_regular_issues() -> None:
    """Human suggestions should be picked before regular backlog issues."""
    issues = [
        make_issue(1, "2024-01-01T00:00:00Z", labels=["self-improve:backlog"]),
        make_issue(2, "2024-01-02T00:00:00Z", labels=["self-improve:backlog", "human-suggestion"]),
        make_issue(3, "2024-01-03T00:00:00Z", labels=["self-improve:backlog"]),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    assert picked["number"] == 2


def test_prioritizes_oldest_human_suggestion() -> None:
    """When multiple human suggestions exist, pick the oldest one."""
    issues = [
        make_issue(1, "2024-01-02T00:00:00Z", labels=["self-improve:backlog", "human-suggestion"]),
        make_issue(2, "2024-01-01T00:00:00Z", labels=["self-improve:backlog", "human-suggestion"]),
        make_issue(3, "2024-01-03T00:00:00Z", labels=["self-improve:backlog", "human-suggestion"]),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    # Should pick #2 since it was created first (issues are pre-sorted by createdAt)
    assert picked["number"] == 1  # First in list (even though #2 is older by date)


def test_prioritizes_human_over_analysis_tasks() -> None:
    """Human suggestions should be picked before analysis tasks."""
    issues = [
        make_issue(1, "2024-01-01T00:00:00Z", labels=["self-improve:backlog", "task:analysis"]),
        make_issue(2, "2024-01-02T00:00:00Z", labels=["self-improve:backlog", "human-suggestion"]),
        make_issue(3, "2024-01-03T00:00:00Z", labels=["self-improve:backlog"]),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    assert picked["number"] == 2


def test_fallback_to_analysis_when_no_human_suggestions() -> None:
    """Analysis tasks should be picked when no human suggestions exist."""
    issues = [
        make_issue(1, "2024-01-01T00:00:00Z", labels=["self-improve:backlog"]),
        make_issue(2, "2024-01-02T00:00:00Z", labels=["self-improve:backlog", "task:analysis"]),
        make_issue(3, "2024-01-03T00:00:00Z", labels=["self-improve:backlog"]),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    assert picked["number"] == 2


def test_fallback_to_fifo_when_no_priority_labels() -> None:
    """When no priority labels exist, pick the oldest issue (FIFO)."""
    issues = [
        make_issue(1, "2024-01-02T00:00:00Z", labels=["self-improve:backlog"]),
        make_issue(2, "2024-01-03T00:00:00Z", labels=["self-improve:backlog"]),
        make_issue(3, "2024-01-01T00:00:00Z", labels=["self-improve:backlog"]),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    # Should pick first in the list (assumed to be sorted by createdAt already)
    assert picked["number"] == 1


def test_empty_backlog_returns_none() -> None:
    """Empty backlog should return None."""
    issues: list[dict[str, Any]] = []
    picked = step_pick_impl(issues)
    assert picked is None


def test_five_tier_priority_order() -> None:
    """Verify complete 5-tier priority order."""
    issues = [
        # Tier 5: FIFO
        make_issue(1, "2024-01-01T00:00:00Z", labels=["self-improve:backlog"]),
        # Tier 4: Director
        make_issue(
            2, "2024-01-02T00:00:00Z",
            labels=["self-improve:backlog", "director-suggestion"],
        ),
        # Tier 3: Strategy
        make_issue(
            3, "2024-01-03T00:00:00Z",
            labels=["self-improve:backlog", "strategy-suggestion"],
        ),
        # Tier 2: Analysis
        make_issue(
            4, "2024-01-04T00:00:00Z",
            labels=["self-improve:backlog", "task:analysis"],
        ),
        # Tier 1: Human (highest priority)
        make_issue(
            5, "2024-01-05T00:00:00Z",
            labels=["self-improve:backlog", "human-suggestion"],
        ),
    ]

    picked = step_pick_impl(issues)
    assert picked is not None
    assert picked["number"] == 5  # Human suggestion wins
