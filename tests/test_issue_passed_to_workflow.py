"""Tests that step_execute_code_change passes the issue number to run_workflow."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import step_execute_code_change  # noqa: E402


def _fake_run_gh(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Stub for _run_gh that always succeeds."""
    return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")


FAKE_ISSUE: dict[str, object] = {
    "number": 163,
    "title": "Fix something",
    "body": "Detailed description",
    "labels": [],
}


@pytest.mark.anyio
async def test_run_workflow_receives_issue_number() -> None:
    """run_workflow must be called with issue=<issue_number>."""
    mock_workflow = AsyncMock()

    with (
        patch("main_loop._run_gh", side_effect=_fake_run_gh),
        patch("main_loop.mark_issue_in_progress"),
        patch("main_loop.mark_issue_done"),
        patch("pr_workflow.run_workflow", mock_workflow),
    ):
        # We need to patch the import inside step_execute_code_change.
        # Since it does `from pr_workflow import run_workflow`, we patch
        # at the pr_workflow module level so the import picks it up.
        result = await step_execute_code_change(
            FAKE_ISSUE,  # type: ignore[arg-type]
            model="opus",
            max_pr_rounds=1,
        )

    assert result is True
    mock_workflow.assert_called_once()
    call_kwargs = mock_workflow.call_args
    assert call_kwargs.kwargs.get("issue") == 163


@pytest.mark.anyio
async def test_run_workflow_not_called_in_dry_run() -> None:
    """In dry-run mode, run_workflow should not be invoked at all."""
    mock_workflow = AsyncMock()

    with (
        patch("main_loop._run_gh", side_effect=_fake_run_gh),
        patch("main_loop.mark_issue_in_progress"),
    ):
        result = await step_execute_code_change(
            FAKE_ISSUE,  # type: ignore[arg-type]
            model="opus",
            max_pr_rounds=1,
            dry_run=True,
        )

    assert result is True
    mock_workflow.assert_not_called()
