"""Tests that DEFAULT_MODEL is set to claude-opus-4-6 in scripts.

This prevents regressions where the model accidentally gets changed back
to a cheaper/faster model when production should always use Opus 4.6.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import both scripts to check their DEFAULT_MODEL constants
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import DEFAULT_MODEL as MAIN_LOOP_DEFAULT_MODEL  # noqa: E402
from pr_workflow import DEFAULT_MODEL as PR_WORKFLOW_DEFAULT_MODEL  # noqa: E402


def test_main_loop_default_model_is_opus() -> None:
    """Test that main_loop.DEFAULT_MODEL is claude-opus-4-6.

    The main loop should always use Opus 4.6 for production analysis.
    If this test fails, it means someone changed the model and it needs
    to be changed back.
    """
    assert MAIN_LOOP_DEFAULT_MODEL == "claude-opus-4-6", (
        f"main_loop.DEFAULT_MODEL must be claude-opus-4-6, got {MAIN_LOOP_DEFAULT_MODEL}. "
        "This is a production requirement — change it back."
    )


def test_pr_workflow_default_model_is_opus() -> None:
    """Test that pr_workflow.DEFAULT_MODEL is claude-opus-4-6.

    The PR workflow (coder/reviewer agents) should also use Opus 4.6
    for production quality code review and implementation.
    If this test fails, it means someone changed the model and it needs
    to be changed back.
    """
    assert PR_WORKFLOW_DEFAULT_MODEL == "claude-opus-4-6", (
        f"pr_workflow.DEFAULT_MODEL must be claude-opus-4-6, got {PR_WORKFLOW_DEFAULT_MODEL}. "
        "This is a production requirement — change it back."
    )
