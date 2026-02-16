"""Integration tests for _sdk_options in both scripts.

These call the real ClaudeAgentOptions constructor (no mocks) to catch
bad kwargs at CI time — exactly what broke in PR #209.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import main_loop  # noqa: E402
import pr_workflow  # noqa: E402
from claude_agent_sdk import ClaudeAgentOptions  # noqa: E402, F401


def test_main_loop_sdk_options_with_tools() -> None:
    """main_loop._sdk_options with allowed_tools returns valid options."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-5-20250929",
        max_turns=1,
        allowed_tools=["Read"],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_main_loop_sdk_options_without_tools() -> None:
    """main_loop._sdk_options with empty tools returns valid options."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-5-20250929",
        max_turns=1,
        allowed_tools=[],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_pr_workflow_sdk_options_with_tools() -> None:
    """pr_workflow._sdk_options with allowed_tools returns valid options."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-5-20250929",
        max_turns=1,
        allowed_tools=["Bash", "Read"],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_pr_workflow_sdk_options_without_tools() -> None:
    """pr_workflow._sdk_options with empty tools returns valid options."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-5-20250929",
        max_turns=1,
        allowed_tools=[],
    )
    assert isinstance(opts, ClaudeAgentOptions)
