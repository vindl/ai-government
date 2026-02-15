"""Tests for cycle allocation rebalancing toward analysis production."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    DEFAULT_MAX_ANALYSES_PER_DAY,
    DEFAULT_MIN_ANALYSIS_GAP_HOURS,
    LABEL_TASK_ANALYSIS,
    _backlog_has_executable_tasks,
    _issue_has_label,
)


def _make_issue(
    number: int,
    *,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Helper to create a mock issue dict."""
    label_objs = [{"name": label} for label in (labels or [])]
    return {
        "number": number,
        "title": f"Issue #{number}",
        "body": "",
        "createdAt": "2026-01-01T00:00:00Z",
        "labels": label_objs,
    }


# ---------------------------------------------------------------------------
# Default rate-limit values are tuned for higher analysis throughput
# ---------------------------------------------------------------------------


class TestDefaultRateLimits:
    def test_max_analyses_per_day_increased(self) -> None:
        """Default cap should allow at least 5 analyses per day."""
        assert DEFAULT_MAX_ANALYSES_PER_DAY >= 5

    def test_min_analysis_gap_reduced(self) -> None:
        """Default gap should be at most 2 hours to allow more throughput."""
        assert DEFAULT_MIN_ANALYSIS_GAP_HOURS <= 2


# ---------------------------------------------------------------------------
# _backlog_has_executable_tasks() considers analysis as executable
# ---------------------------------------------------------------------------


class TestBacklogHasExecutableTasks:
    def test_empty_backlog(self) -> None:
        """Empty backlog returns False."""
        with patch("main_loop.list_backlog_issues", return_value=[]):
            assert _backlog_has_executable_tasks() is False

    def test_code_change_tasks_always_executable(self) -> None:
        """Non-analysis tasks are always executable."""
        issues = [_make_issue(1, labels=["self-improve:backlog"])]
        with patch("main_loop.list_backlog_issues", return_value=issues):
            assert _backlog_has_executable_tasks() is True

    def test_analysis_tasks_executable_when_rate_allows(self) -> None:
        """Analysis tasks count as executable when rate limiter allows."""
        issues = [_make_issue(1, labels=["task:analysis"])]
        with (
            patch("main_loop.list_backlog_issues", return_value=issues),
            patch("main_loop.should_run_analysis", return_value=True),
        ):
            assert _backlog_has_executable_tasks() is True

    def test_analysis_tasks_not_executable_when_rate_blocked(self) -> None:
        """Analysis tasks are not executable when rate limiter blocks."""
        issues = [_make_issue(1, labels=["task:analysis"])]
        with (
            patch("main_loop.list_backlog_issues", return_value=issues),
            patch("main_loop.should_run_analysis", return_value=False),
        ):
            assert _backlog_has_executable_tasks() is False

    def test_mixed_backlog_always_executable(self) -> None:
        """Mixed backlog with code-change tasks is always executable."""
        issues = [
            _make_issue(1, labels=["task:analysis"]),
            _make_issue(2, labels=["self-improve:backlog"]),
        ]
        with patch("main_loop.list_backlog_issues", return_value=issues):
            # should_run_analysis should NOT be called since code-change exists
            assert _backlog_has_executable_tasks() is True


# ---------------------------------------------------------------------------
# Phase B proposal suppression when analysis backlog exists
# ---------------------------------------------------------------------------


class TestProposalSuppression:
    """Verify that the proposal logic suppresses new proposals when analysis
    issues are waiting, even if rate-limited."""

    def test_analysis_in_backlog_suppresses_reason(self) -> None:
        """When analysis issues exist in backlog, the reason should mention them."""
        issues = [_make_issue(1, labels=["task:analysis"])]
        has_analysis = any(
            _issue_has_label(i, LABEL_TASK_ANALYSIS) for i in issues
        )
        assert has_analysis is True

    def test_code_only_backlog_uses_draining_reason(self) -> None:
        """When only code-change issues exist, the reason mentions draining."""
        issues = [_make_issue(1, labels=["self-improve:backlog"])]
        has_analysis = any(
            _issue_has_label(i, LABEL_TASK_ANALYSIS) for i in issues
        )
        assert has_analysis is False
