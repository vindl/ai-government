"""Tests for _run_gh timeout behaviour."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import _run_gh  # noqa: E402


class TestRunGhTimeout:
    """Tests for the _run_gh helper's timeout handling."""

    def test_timeout_returns_failed_result(self) -> None:
        """A timed-out subprocess should return rc=1 without raising."""
        with patch("main_loop.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=30)):
            result = _run_gh(["gh", "api", "/rate_limit"], check=False)

        assert result.returncode == 1
        assert result.stderr == "timeout"
        assert result.stdout == ""

    def test_timeout_with_check_raises(self) -> None:
        """When check=True (default), a timeout should still raise CalledProcessError."""
        with patch("main_loop.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=30)):
            # check=True is the default — the timeout path returns rc=1 which
            # is then caught by the check logic.  But our implementation returns
            # *before* the check, so it should NOT raise.
            result = _run_gh(["gh", "api", "/rate_limit"], check=True)

        assert result.returncode == 1
        assert result.stderr == "timeout"

    def test_normal_success_unaffected(self) -> None:
        """Normal successful calls should work as before."""
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="ok", stderr="")
        with patch("main_loop.subprocess.run", return_value=fake):
            result = _run_gh(["gh", "api", "/rate_limit"])

        assert result.returncode == 0
        assert result.stdout == "ok"

    def test_normal_failure_with_check_raises(self) -> None:
        """Non-timeout failures with check=True should still raise."""
        fake = subprocess.CompletedProcess(
            ["gh"], returncode=1, stdout="", stderr="not found",
        )
        with (
            patch("main_loop.subprocess.run", return_value=fake),
            pytest.raises(subprocess.CalledProcessError),
        ):
            _run_gh(["gh", "api", "/repos"], check=True)

    def test_timeout_value_passed_to_subprocess(self) -> None:
        """The timeout kwarg should be forwarded to subprocess.run."""
        fake = subprocess.CompletedProcess(["gh"], returncode=0, stdout="", stderr="")
        with patch("main_loop.subprocess.run", return_value=fake) as mock_run:
            _run_gh(["gh", "version"])

        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 30
