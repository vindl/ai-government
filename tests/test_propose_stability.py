"""Tests for propose step stability improvements.

Tests three layers of defense against transient SDK crashes:
1. Error pattern detector skips transient SDK errors (no spurious issues)
2. Propose step degrades gracefully on transient SDK failure (0 proposals, not phase failure)
3. Exponential backoff covers longer outage windows
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from main_loop import (  # noqa: E402
    ConductorAction,
    CycleTelemetry,
    _check_error_patterns,
    _dispatch_action,
)


def _write_telemetry(path: Path, entries: list[CycleTelemetry]) -> None:
    """Write telemetry entries as JSONL."""
    with path.open("w") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")


def _gh_result(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# ---------------------------------------------------------------------------
# Error pattern detector: transient SDK errors are filtered out
# ---------------------------------------------------------------------------


class TestErrorPatternSkipsTransient:
    def test_transient_errors_not_filed(self, tmp_path: Path) -> None:
        """Error pattern detector should NOT file issues for transient SDK errors."""
        tpath = tmp_path / "telemetry.jsonl"
        entries = [
            CycleTelemetry(
                cycle=i,
                errors=["propose: Command failed with exit code 1 (exit code: 1)"],
            )
            for i in range(5)
        ]
        _write_telemetry(tpath, entries)

        with (
            patch("main_loop.TELEMETRY_PATH", tpath),
            patch("main_loop.create_director_issue") as mock_create,
        ):
            _check_error_patterns()

        # Should NOT file an issue for transient SDK errors
        mock_create.assert_not_called()

    def test_non_transient_errors_still_filed(self, tmp_path: Path) -> None:
        """Error pattern detector should still file issues for non-transient errors."""
        tpath = tmp_path / "telemetry.jsonl"
        entries = [
            CycleTelemetry(
                cycle=i,
                errors=["propose: TypeError: bad argument"],
            )
            for i in range(5)
        ]
        _write_telemetry(tpath, entries)

        with (
            patch("main_loop.TELEMETRY_PATH", tpath),
            patch("main_loop._run_gh", return_value=_gh_result("[]")),
            patch("main_loop.create_director_issue", return_value=999) as mock_create,
        ):
            _check_error_patterns()

        # Should file an issue for non-transient errors
        mock_create.assert_called_once()
        title = mock_create.call_args[0][0]
        assert "TypeError" in title

    def test_mixed_errors_only_files_non_transient(self, tmp_path: Path) -> None:
        """When both transient and non-transient errors exist, only file for non-transient."""
        tpath = tmp_path / "telemetry.jsonl"
        entries = [
            CycleTelemetry(
                cycle=i,
                errors=[
                    "propose: Command failed with exit code 1 (exit code: 1)",
                    "debate: KeyError: 'missing_field'",
                ],
            )
            for i in range(5)
        ]
        _write_telemetry(tpath, entries)

        with (
            patch("main_loop.TELEMETRY_PATH", tpath),
            patch("main_loop._run_gh", return_value=_gh_result("[]")),
            patch("main_loop.create_director_issue", return_value=999) as mock_create,
        ):
            _check_error_patterns()

        # Should file for KeyError, not for exit code 1
        mock_create.assert_called_once()
        title = mock_create.call_args[0][0]
        assert "KeyError" in title
        assert "exit code" not in title


# ---------------------------------------------------------------------------
# Propose step: graceful degradation on transient SDK failure
# ---------------------------------------------------------------------------


class TestProposeGracefulDegradation:
    @pytest.mark.anyio
    async def test_transient_error_yields_zero_proposals(self) -> None:
        """When step_propose fails with transient error, the phase succeeds with 0 proposals."""
        pending: list[dict[str, Any]] = []
        action = ConductorAction(action="propose", reason="time to propose")
        telemetry = CycleTelemetry(cycle=1)

        transient_exc = Exception("Command failed with exit code 1 (exit code: 1)")

        with (
            patch("main_loop.list_backlog_issues", return_value=[]),
            patch("main_loop.step_propose", new_callable=AsyncMock, side_effect=transient_exc),
            patch("main_loop.list_human_suggestions", return_value=[]),
        ):
            result = await _dispatch_action(
                action,
                telemetry=telemetry,
                model="test",
                max_pr_rounds=1,
                dry_run=False,
                productive_cycles=0,
                pending_proposals=pending,
            )

        # Phase should succeed (not crash the dispatch)
        assert result is None
        assert len(pending) == 0
        assert telemetry.proposals_made == 0
        # No errors recorded in telemetry for transient failures
        assert len(telemetry.errors) == 0
        # Phase detail reflects the graceful degradation
        propose_phase = next(p for p in telemetry.phases if p.phase == "propose")
        assert propose_phase.success is True
        assert "0 proposals" in propose_phase.detail

    @pytest.mark.anyio
    async def test_non_transient_error_still_raises(self) -> None:
        """Non-transient errors in step_propose should still fail the phase."""
        pending: list[dict[str, Any]] = []
        action = ConductorAction(action="propose", reason="time to propose")
        telemetry = CycleTelemetry(cycle=1)

        non_transient_exc = TypeError("bad argument")

        with (
            patch("main_loop.list_backlog_issues", return_value=[]),
            patch("main_loop.step_propose", new_callable=AsyncMock, side_effect=non_transient_exc),
            patch("main_loop.list_human_suggestions", return_value=[]),
        ):
            await _dispatch_action(
                action,
                telemetry=telemetry,
                model="test",
                max_pr_rounds=1,
                dry_run=False,
                productive_cycles=0,
                pending_proposals=pending,
            )

        # Phase should be marked as failed
        propose_phase = next(p for p in telemetry.phases if p.phase == "propose")
        assert propose_phase.success is False
        assert len(telemetry.errors) == 1

    @pytest.mark.anyio
    async def test_human_suggestions_proceed_after_transient_failure(self) -> None:
        """Human suggestions should still be ingested even when step_propose fails transiently."""
        pending: list[dict[str, Any]] = []
        action = ConductorAction(action="propose", reason="time to propose")
        telemetry = CycleTelemetry(cycle=1)

        transient_exc = Exception("Command failed with exit code 1 (exit code: 1)")

        human_issue = {
            "number": 42,
            "title": "Add feature X",
            "author": {"login": "vindl"},
        }

        with (
            patch("main_loop.list_backlog_issues", return_value=[]),
            patch("main_loop.step_propose", new_callable=AsyncMock, side_effect=transient_exc),
            patch("main_loop.list_human_suggestions", return_value=[human_issue]),
            patch("main_loop._is_privileged_user", return_value=True),
            patch("main_loop._run_gh", return_value=_gh_result("")),
            patch("main_loop.accept_issue") as mock_accept,
        ):
            await _dispatch_action(
                action,
                telemetry=telemetry,
                model="test",
                max_pr_rounds=1,
                dry_run=False,
                productive_cycles=0,
                pending_proposals=pending,
            )

        # Human suggestion should have been accepted despite propose failure
        mock_accept.assert_called_once_with(42)
        assert telemetry.human_suggestions_ingested == 1
