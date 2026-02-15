"""Tests for CI health check functionality in main_loop.py."""

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
    LABEL_CI_FAILURE,
    LABEL_TASK_FIX,
    check_ci_health,
    create_ci_failure_issue,
)

# ---------------------------------------------------------------------------
# create_ci_failure_issue()
# ---------------------------------------------------------------------------


class TestCreateCiFailureIssue:
    def test_creates_issue_with_correct_labels(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that create_ci_failure_issue creates an issue with correct labels."""
        run_id = "12345678"
        failure_summary = "```\nTest failure output\n```"

        # Mock _run_gh to capture the gh issue create command
        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/owner/repo/issues/42"
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._get_repo_nwo", lambda: "owner/repo")

        issue_number = create_ci_failure_issue(run_id, failure_summary)

        assert issue_number == 42
        assert len(calls) == 1
        assert calls[0][0:2] == ["gh", "issue"]
        assert calls[0][2] == "create"
        assert f"{LABEL_CI_FAILURE},{LABEL_BACKLOG},{LABEL_TASK_FIX}" in calls[0]

    def test_includes_run_url_in_body(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that the issue body includes the run URL."""
        run_id = "87654321"
        failure_summary = "```\nLint error\n```"

        body_captured: list[str] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            # Find the --body argument
            if "--body" in args:
                body_idx = args.index("--body")
                body_captured.append(args[body_idx + 1])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/owner/repo/issues/99"
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._get_repo_nwo", lambda: "owner/repo")

        create_ci_failure_issue(run_id, failure_summary)

        assert len(body_captured) == 1
        body = body_captured[0]
        assert run_id in body
        assert f"https://github.com/owner/repo/actions/runs/{run_id}" in body
        assert failure_summary in body


# ---------------------------------------------------------------------------
# check_ci_health()
# ---------------------------------------------------------------------------


class TestCheckCiHealth:
    def test_returns_zero_when_ci_succeeds(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health returns 0 when CI passes."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "run" in args and "list" in args:
                result.stdout = json.dumps([{
                    "databaseId": 123,
                    "conclusion": "success",
                    "status": "completed",
                }])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_returns_zero_when_no_runs(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health returns 0 when no runs exist."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "run" in args and "list" in args:
                result.stdout = json.dumps([])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_returns_zero_when_run_in_progress(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health returns 0 when run is still in progress."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "run" in args and "list" in args:
                result.stdout = json.dumps([{
                    "databaseId": 123,
                    "conclusion": None,
                    "status": "in_progress",
                }])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_creates_issue_when_ci_fails(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health creates an issue when CI fails."""
        run_id = "999"

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0

            if "run" in args and "list" in args:
                result.stdout = json.dumps([{
                    "databaseId": int(run_id),
                    "conclusion": "failure",
                    "status": "completed",
                }])
            elif "run" in args and "view" in args:
                result.stdout = "Test failure logs"
            elif "issue" in args and "list" in args:
                # No existing issues
                result.stdout = json.dumps([])
            elif "issue" in args and "create" in args:
                result.stdout = "https://github.com/owner/repo/issues/50"
            else:
                result.stdout = ""

            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._get_repo_nwo", lambda: "owner/repo")

        issues_created = check_ci_health()
        assert issues_created == 1

    def test_returns_zero_when_issue_already_exists(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health is idempotent — doesn't create duplicate issues."""
        run_id = "999"

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0

            if "run" in args and "list" in args:
                result.stdout = json.dumps([{
                    "databaseId": int(run_id),
                    "conclusion": "failure",
                    "status": "completed",
                }])
            elif "issue" in args and "list" in args:
                # Existing issue with the same run ID in body
                result.stdout = json.dumps([{
                    "number": 42,
                    "title": "CI failure on main (run 999)",
                    "body": f"**Run ID**: {run_id}\n...",
                }])
            else:
                result.stdout = ""

            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_handles_gh_cli_errors_gracefully(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health returns 0 if gh cli fails."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "gh: command not found"
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_truncates_large_logs(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health truncates very large failure logs."""
        run_id = "888"
        large_log = "x" * 10000  # Large log output

        body_captured: list[str] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0

            if "run" in args and "list" in args:
                result.stdout = json.dumps([{
                    "databaseId": int(run_id),
                    "conclusion": "failure",
                    "status": "completed",
                }])
            elif "run" in args and "view" in args:
                result.stdout = large_log
            elif "issue" in args and "list" in args:
                result.stdout = json.dumps([])
            elif "issue" in args and "create" in args:
                # Capture the body
                if "--body" in args:
                    body_idx = args.index("--body")
                    body_captured.append(args[body_idx + 1])
                result.stdout = "https://github.com/owner/repo/issues/60"
            else:
                result.stdout = ""

            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        monkeypatch.setattr("main_loop._get_repo_nwo", lambda: "owner/repo")

        issues_created = check_ci_health()

        assert issues_created == 1
        assert len(body_captured) == 1
        body = body_captured[0]
        # Should be truncated
        assert "truncated" in body
        assert len(body) < len(large_log)
