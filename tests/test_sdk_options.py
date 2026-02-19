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
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Read"],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_main_loop_sdk_options_without_tools() -> None:
    """main_loop._sdk_options with empty tools returns valid options."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_pr_workflow_sdk_options_with_tools() -> None:
    """pr_workflow._sdk_options with allowed_tools returns valid options."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Bash", "Read"],
    )
    assert isinstance(opts, ClaudeAgentOptions)


def test_pr_workflow_sdk_options_without_tools() -> None:
    """pr_workflow._sdk_options with empty tools returns valid options."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert isinstance(opts, ClaudeAgentOptions)


# ---------------------------------------------------------------------------
# effort parameter tests
# ---------------------------------------------------------------------------


def test_main_loop_sdk_options_effort_with_tools() -> None:
    """main_loop._sdk_options passes effort to ClaudeAgentOptions (tools branch)."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Read"],
        effort="low",
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.effort == "low"


def test_main_loop_sdk_options_effort_without_tools() -> None:
    """main_loop._sdk_options passes effort to ClaudeAgentOptions (no-tools branch)."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
        effort="high",
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.effort == "high"


def test_main_loop_sdk_options_effort_none_by_default() -> None:
    """effort defaults to None when not specified."""
    opts = main_loop._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert opts.effort is None


def test_main_loop_sdk_options_effort_all_levels() -> None:
    """All valid effort levels are accepted."""
    for level in ("low", "medium", "high", "max"):
        opts = main_loop._sdk_options(
            system_prompt="test prompt",
            model="claude-sonnet-4-6",
            max_turns=1,
            allowed_tools=[],
            effort=level,  # type: ignore[arg-type]
        )
        assert opts.effort == level


def test_pr_workflow_sdk_options_effort_with_tools() -> None:
    """pr_workflow._sdk_options passes effort to ClaudeAgentOptions (tools branch)."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Bash", "Read"],
        effort="high",
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.effort == "high"


def test_pr_workflow_sdk_options_effort_without_tools() -> None:
    """pr_workflow._sdk_options passes effort to ClaudeAgentOptions (no-tools branch)."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
        effort="medium",
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.effort == "medium"


def test_pr_workflow_sdk_options_effort_none_by_default() -> None:
    """pr_workflow effort defaults to None when not specified."""
    opts = pr_workflow._sdk_options(
        system_prompt="test prompt",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert opts.effort is None
