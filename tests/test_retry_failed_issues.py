"""Tests for retry_failed_issues() and related functionality in main_loop.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    LABEL_BACKLOG,
    LABEL_FAILED,
    _get_failure_count,
    retry_failed_issues,
)

# ---------------------------------------------------------------------------
# _get_failure_count()
# ---------------------------------------------------------------------------


class TestGetFailureCount:
    def test_returns_zero_when_no_comments(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"comments": []})
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(1) == 0

    def test_returns_zero_when_no_failure_marker(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"comments": [
                {"body": "Some unrelated comment"},
            ]})
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(42) == 0

    def test_parses_single_failure(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"comments": [
                {"body": "Execution failed: timeout\n\nFailure count: 1/2"},
            ]})
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(10) == 1

    def test_returns_max_across_multiple_failures(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"comments": [
                {"body": "Execution failed: timeout\n\nFailure count: 1/2"},
                {"body": "Re-queuing for retry (attempt 2/2)."},
                {"body": "Execution failed: crash\n\nFailure count: 2/2"},
            ]})
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(10) == 2

    def test_handles_gh_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(999) == 0

    def test_handles_invalid_json(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "not json"
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert _get_failure_count(1) == 0


# ---------------------------------------------------------------------------
# retry_failed_issues()
# ---------------------------------------------------------------------------


class TestRetryFailedIssues:
    def test_requeues_issue_below_retry_limit(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An issue with 1 failure (below MAX_FAILED_RETRIES) should be re-queued."""
        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "issue" in args and "list" in args:
                result.stdout = json.dumps([
                    {"number": 312, "title": "Labor law analysis"},
                ])
            elif "issue" in args and "view" in args:
                result.stdout = json.dumps({"comments": [
                    {"body": "Execution failed: timeout\n\nFailure count: 1/2"},
                ]})
            else:
                result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._gh_comment", lambda *a, **kw: None)

        retried = retry_failed_issues()
        assert retried == 1

        # Check that label swap happened
        edit_calls = [c for c in calls if "edit" in c]
        assert len(edit_calls) == 1
        assert "--remove-label" in edit_calls[0]
        assert LABEL_FAILED in edit_calls[0]
        assert "--add-label" in edit_calls[0]
        assert LABEL_BACKLOG in edit_calls[0]

    def test_closes_issue_at_max_retries(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An issue that has reached MAX_FAILED_RETRIES should be closed."""
        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "issue" in args and "list" in args:
                result.stdout = json.dumps([
                    {"number": 312, "title": "Labor law analysis"},
                ])
            elif "issue" in args and "view" in args:
                result.stdout = json.dumps({"comments": [
                    {"body": "Execution failed: timeout\n\nFailure count: 1/2"},
                    {"body": "Execution failed: crash\n\nFailure count: 2/2"},
                ]})
            else:
                result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._gh_comment", lambda *a, **kw: None)

        retried = retry_failed_issues()
        assert retried == 0

        # Check that the issue was closed
        close_calls = [c for c in calls if "close" in c]
        assert len(close_calls) == 1
        assert "312" in close_calls[0]

    def test_returns_zero_when_no_failed_issues(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([])
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert retry_failed_issues() == 0

    def test_handles_gh_list_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert retry_failed_issues() == 0

    def test_requeues_issue_with_zero_prior_failures(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An issue with no prior failure count comments (legacy) should be re-queued."""
        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "issue" in args and "list" in args:
                result.stdout = json.dumps([
                    {"number": 100, "title": "Old failed issue"},
                ])
            elif "issue" in args and "view" in args:
                # No failure count marker in comments (legacy issue)
                result.stdout = json.dumps({"comments": [
                    {"body": "Execution failed: some error"},
                ]})
            else:
                result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._gh_comment", lambda *a, **kw: None)

        retried = retry_failed_issues()
        assert retried == 1

    def test_mixed_issues_some_retried_some_closed(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Multiple failed issues: one retryable, one at max retries."""
        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "issue" in args and "list" in args:
                result.stdout = json.dumps([
                    {"number": 10, "title": "Retryable"},
                    {"number": 20, "title": "Exhausted"},
                ])
            elif "issue" in args and "view" in args:
                issue_num = args[args.index("view") + 1]
                if issue_num == "10":
                    result.stdout = json.dumps({"comments": [
                        {"body": "Failure count: 1/2"},
                    ]})
                else:
                    result.stdout = json.dumps({"comments": [
                        {"body": "Failure count: 2/2"},
                    ]})
            else:
                result.stdout = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._gh_comment", lambda *a, **kw: None)

        retried = retry_failed_issues()
        assert retried == 1

        # Issue 20 should be closed
        close_calls = [c for c in calls if "close" in c]
        assert len(close_calls) == 1
        assert "20" in close_calls[0]

        # Issue 10 should have label swap
        edit_calls = [c for c in calls if "edit" in c]
        assert len(edit_calls) == 1
        assert "10" in edit_calls[0]
