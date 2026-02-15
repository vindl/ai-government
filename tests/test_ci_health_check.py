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
    _commit_output_data,
    _find_latest_completed_run,
    check_ci_health,
    create_ci_failure_issue,
    is_ci_passing,
)

# ---------------------------------------------------------------------------
# _find_latest_completed_run()
# ---------------------------------------------------------------------------


class TestFindLatestCompletedRun:
    def test_returns_first_completed_run(self) -> None:
        runs = [
            {"databaseId": 3, "status": "in_progress", "conclusion": None},
            {"databaseId": 2, "status": "completed", "conclusion": "failure"},
            {"databaseId": 1, "status": "completed", "conclusion": "success"},
        ]
        result = _find_latest_completed_run(runs)
        assert result is not None
        assert result["databaseId"] == 2

    def test_returns_none_when_all_in_progress(self) -> None:
        runs = [
            {"databaseId": 3, "status": "in_progress", "conclusion": None},
            {"databaseId": 2, "status": "in_progress", "conclusion": None},
        ]
        assert _find_latest_completed_run(runs) is None

    def test_returns_none_for_empty_list(self) -> None:
        assert _find_latest_completed_run([]) is None

    def test_returns_first_when_first_is_completed(self) -> None:
        runs = [
            {"databaseId": 5, "status": "completed", "conclusion": "success"},
            {"databaseId": 4, "status": "completed", "conclusion": "failure"},
        ]
        result = _find_latest_completed_run(runs)
        assert result is not None
        assert result["databaseId"] == 5


# ---------------------------------------------------------------------------
# is_ci_passing()
# ---------------------------------------------------------------------------


class TestIsCiPassing:
    def test_returns_true_when_latest_completed_succeeds(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{
                "databaseId": 1,
                "conclusion": "success",
                "status": "completed",
            }])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is True

    def test_returns_false_when_latest_completed_failed(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{
                "databaseId": 1,
                "conclusion": "failure",
                "status": "completed",
            }])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is False

    def test_skips_in_progress_and_checks_completed(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The race condition scenario: latest is in-progress, but prior completed run failed."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([
                {"databaseId": 3, "conclusion": None, "status": "in_progress"},
                {"databaseId": 2, "conclusion": "failure", "status": "completed"},
            ])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is False

    def test_returns_true_when_all_in_progress(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Optimistically allow pushes when no completed runs exist."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([
                {"databaseId": 2, "conclusion": None, "status": "in_progress"},
                {"databaseId": 1, "conclusion": None, "status": "in_progress"},
            ])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is True

    def test_returns_true_on_gh_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """On error, optimistically allow (don't block the loop)."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "gh: command not found"
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is True

    def test_returns_true_when_no_runs(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)
        assert is_ci_passing() is True


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

    def test_returns_zero_when_all_runs_in_progress(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that check_ci_health returns 0 when ALL runs are in-progress."""
        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if "run" in args and "list" in args:
                result.stdout = json.dumps([
                    {"databaseId": 124, "conclusion": None, "status": "in_progress"},
                    {"databaseId": 123, "conclusion": None, "status": "in_progress"},
                ])
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        issues_created = check_ci_health()
        assert issues_created == 0

    def test_detects_failure_behind_in_progress_run(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Race condition fix: detect failure even when newest run is in-progress."""
        run_id = "777"

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            result = MagicMock()
            result.returncode = 0

            if "run" in args and "list" in args:
                # Latest run is in-progress, but prior completed run failed
                result.stdout = json.dumps([
                    {"databaseId": 888, "conclusion": None, "status": "in_progress"},
                    {"databaseId": int(run_id), "conclusion": "failure", "status": "completed"},
                ])
            elif "run" in args and "view" in args:
                result.stdout = "Test failure logs"
            elif "issue" in args and "list" in args:
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


# ---------------------------------------------------------------------------
# _commit_output_data() — push gating
# ---------------------------------------------------------------------------


class TestCommitOutputDataPushGating:
    def test_skips_push_when_ci_failing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """When CI is failing, commit locally but don't push."""
        # Create a fake data dir with changes
        data_dir = tmp_path / "output" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "test.json").write_text("{}")

        monkeypatch.setattr("main_loop.PROJECT_ROOT", tmp_path)

        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "diff" in args:
                result.stdout = "output/data/test.json"
            elif "ls-files" in args:
                result.stdout = ""
            elif "run" in args and "list" in args:
                # CI is failing
                result.stdout = json.dumps([{
                    "databaseId": 1,
                    "conclusion": "failure",
                    "status": "completed",
                }])
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        _commit_output_data()

        # Should have committed but NOT pushed
        commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
        push_calls = [c for c in calls if c[:2] == ["git", "push"]]
        assert len(commit_calls) == 1
        assert len(push_calls) == 0

    def test_pushes_when_ci_passing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """When CI is passing, commit and push normally."""
        data_dir = tmp_path / "output" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "test.json").write_text("{}")

        monkeypatch.setattr("main_loop.PROJECT_ROOT", tmp_path)

        calls: list[list[str]] = []

        def mock_run_gh(args: list[str], *, check: bool = True) -> MagicMock:
            calls.append(args)
            result = MagicMock()
            result.returncode = 0
            if "diff" in args:
                result.stdout = "output/data/test.json"
            elif "ls-files" in args:
                result.stdout = ""
            elif "run" in args and "list" in args:
                # CI is passing
                result.stdout = json.dumps([{
                    "databaseId": 1,
                    "conclusion": "success",
                    "status": "completed",
                }])
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        monkeypatch.setattr("main_loop._run_gh", mock_run_gh)

        _commit_output_data()

        # Should have committed AND pushed
        commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
        push_calls = [c for c in calls if c[:2] == ["git", "push"]]
        assert len(commit_calls) == 1
        assert len(push_calls) == 1
