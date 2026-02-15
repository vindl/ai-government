"""Tests for ghost merge handling and local main sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from pr_workflow import (  # noqa: E402
    _merge_pr_safe,
    sync_local_main,
)


def _fake_run_gh_ok(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Stub _run_gh that always succeeds."""
    return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")


class TestSyncLocalMain:
    """Tests for sync_local_main()."""

    def test_runs_checkout_fetch_reset(self) -> None:
        """sync_local_main should checkout main, fetch, and hard reset."""
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("pr_workflow._run_gh", side_effect=_capture):
            sync_local_main()

        assert calls == [
            ["git", "checkout", "main"],
            ["git", "fetch", "origin", "main"],
            ["git", "reset", "--hard", "origin/main"],
        ]


class TestMergePrSafe:
    """Tests for _merge_pr_safe() ghost merge handling."""

    def test_successful_merge_syncs_main(self) -> None:
        """On a clean merge, local main should still be synced."""
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("pr_workflow._run_gh", side_effect=_capture):
            _merge_pr_safe(42)

        # merge_pr calls _run_gh once, then sync_local_main calls it 3 times
        assert calls[0] == ["gh", "pr", "merge", "42", "--squash", "--delete-branch"]
        assert calls[1:] == [
            ["git", "checkout", "main"],
            ["git", "fetch", "origin", "main"],
            ["git", "reset", "--hard", "origin/main"],
        ]

    def test_ghost_merge_detected_and_continues(self) -> None:
        """When merge errors but PR is actually MERGED, should not raise."""
        call_log: list[list[str]] = []

        def _side_effect(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            call_log.append(cmd)
            # merge_pr → _run_gh raises
            if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "merge":
                raise subprocess.CalledProcessError(1, cmd, "", "GraphQL error")
            # pr view → state is MERGED
            if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="MERGED", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("pr_workflow._run_gh", side_effect=_side_effect):
            # Should NOT raise
            _merge_pr_safe(99)

        # Should have checked PR state
        view_calls = [c for c in call_log if c[:3] == ["gh", "pr", "view"]]
        assert len(view_calls) == 1
        # Should have synced main (finally block)
        assert call_log[-3:] == [
            ["git", "checkout", "main"],
            ["git", "fetch", "origin", "main"],
            ["git", "reset", "--hard", "origin/main"],
        ]

    def test_genuine_failure_closes_pr_and_raises(self) -> None:
        """When merge fails and PR is NOT merged, should close PR and re-raise."""
        call_log: list[list[str]] = []

        def _side_effect(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            call_log.append(cmd)
            if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "merge":
                raise subprocess.CalledProcessError(1, cmd, "", "merge conflict")
            if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="OPEN", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with (
            patch("pr_workflow._run_gh", side_effect=_side_effect),
            pytest.raises(subprocess.CalledProcessError),
        ):
            _merge_pr_safe(77)

        # Should have tried to close the PR
        close_calls = [c for c in call_log if c[:3] == ["gh", "pr", "close"]]
        assert len(close_calls) == 1
        assert close_calls[0] == ["gh", "pr", "close", "77"]
        # Should still have synced main (finally block runs even on raise)
        assert call_log[-3:] == [
            ["git", "checkout", "main"],
            ["git", "fetch", "origin", "main"],
            ["git", "reset", "--hard", "origin/main"],
        ]

    def test_finally_runs_even_on_unexpected_error(self) -> None:
        """The finally block should sync main even on unexpected exceptions."""
        call_log: list[list[str]] = []

        def _side_effect(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
            call_log.append(cmd)
            if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "merge":
                raise RuntimeError("unexpected network issue")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with (
            patch("pr_workflow._run_gh", side_effect=_side_effect),
            pytest.raises(RuntimeError, match="unexpected network issue"),
        ):
            _merge_pr_safe(55)

        # finally block should still sync main
        assert call_log[-3:] == [
            ["git", "checkout", "main"],
            ["git", "fetch", "origin", "main"],
            ["git", "reset", "--hard", "origin/main"],
        ]
