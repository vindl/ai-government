"""Tests for InfrastructureError in pr_workflow."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from pr_workflow import InfrastructureError, _sdk_options  # noqa: E402


def test_infrastructure_error_is_exception() -> None:
    """InfrastructureError is an Exception subclass."""
    assert issubclass(InfrastructureError, Exception)
    exc = InfrastructureError("test")
    assert isinstance(exc, Exception)


def test_sdk_options_failure_does_not_silently_return() -> None:
    """When _sdk_options itself raises, the error propagates (not caught)."""
    with patch("pr_workflow.ClaudeAgentOptions", side_effect=TypeError("bad kwarg")), \
         pytest.raises(TypeError, match="bad kwarg"):
            _sdk_options(
                system_prompt="test",
                model="claude-sonnet-4-6",
                max_turns=1,
                allowed_tools=["Read"],
            )


@pytest.mark.anyio
async def test_run_coder_raises_infrastructure_error_on_sdk_failure() -> None:
    """run_coder raises InfrastructureError when _sdk_options fails."""
    from pr_workflow import run_coder  # noqa: E402

    with patch("pr_workflow._sdk_options", side_effect=TypeError("bad kwarg")), \
         pytest.raises(InfrastructureError, match="_sdk_options failed"):
        await run_coder("do something", model="claude-sonnet-4-6", branch="test")


@pytest.mark.anyio
async def test_run_reviewer_raises_infrastructure_error_on_sdk_failure() -> None:
    """run_reviewer raises InfrastructureError when _sdk_options fails."""
    from pr_workflow import run_reviewer  # noqa: E402

    with patch("pr_workflow._build_reviewer_prompt", return_value="review this"), \
         patch("pr_workflow._sdk_options", side_effect=TypeError("bad kwarg")), \
         pytest.raises(InfrastructureError, match="_sdk_options failed"):
        await run_reviewer(123, model="claude-sonnet-4-6")


@pytest.mark.anyio
async def test_run_coder_happy_path_no_infrastructure_error() -> None:
    """run_coder does NOT raise InfrastructureError on normal agent failure."""
    from pr_workflow import run_coder  # noqa: E402

    mock_stream = AsyncMock()
    mock_stream.__aiter__ = lambda self: self
    mock_stream.__anext__ = AsyncMock(side_effect=StopAsyncIteration)

    with (
        patch("pr_workflow._sdk_options") as mock_opts,
        patch("pr_workflow.claude_agent_sdk.query", return_value=mock_stream),
    ):
        mock_opts.return_value = "opts"
        output, had_error = await run_coder(
            "do something", model="claude-sonnet-4-6", branch="test",
        )
    assert not had_error
