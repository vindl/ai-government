"""Tests for _run_sdk_with_retry in main_loop.

Verifies that transient SDK errors (exit code 1, timeout) are retried
with backoff, while non-transient errors propagate immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    _is_sdk_transient_error,
    _run_sdk_with_retry,
    _sdk_options,
)


def _make_opts() -> object:
    """Build minimal SDK options for testing."""
    return _sdk_options(
        system_prompt="test",
        model="test-model",
        max_turns=1,
        allowed_tools=[],
    )


class TestIsSDKTransientError:
    def test_exit_code_1_is_transient(self) -> None:
        exc = Exception("Command failed with exit code 1 (exit code: 1)")
        assert _is_sdk_transient_error(exc) is True

    def test_timeout_error_is_transient(self) -> None:
        exc = TimeoutError("timed out")
        assert _is_sdk_transient_error(exc) is True

    def test_generic_error_is_not_transient(self) -> None:
        exc = ValueError("invalid JSON")
        assert _is_sdk_transient_error(exc) is False


class TestRunSDKWithRetry:
    @pytest.mark.anyio
    async def test_succeeds_on_first_attempt(self) -> None:
        """No retries needed when the first attempt works."""
        opts = _make_opts()
        mock_stream = AsyncMock()

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch("main_loop._collect_agent_output", new_callable=AsyncMock, return_value="ok"),
        ):
            result = await _run_sdk_with_retry("test prompt", opts, retries=2, base_delay=0)

        assert result == "ok"

    @pytest.mark.anyio
    async def test_retries_on_transient_error(self) -> None:
        """Retries transient errors and succeeds on subsequent attempt."""
        opts = _make_opts()
        transient_exc = Exception("Command failed with exit code 1 (exit code: 1)")
        mock_stream = AsyncMock()

        call_count = 0

        async def fake_collect(stream: object, *, timeout_seconds: float = 600) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise transient_exc
            return "ok after retry"

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch("main_loop._collect_agent_output", side_effect=fake_collect),
            patch("main_loop.anyio.sleep", new_callable=AsyncMock),
        ):
            result = await _run_sdk_with_retry("test prompt", opts, retries=2, base_delay=0)

        assert result == "ok after retry"
        assert call_count == 2

    @pytest.mark.anyio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        """Raises the last exception after all retries are exhausted."""
        opts = _make_opts()
        transient_exc = Exception("Command failed with exit code 1 (exit code: 1)")
        mock_stream = AsyncMock()

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch(
                "main_loop._collect_agent_output",
                new_callable=AsyncMock,
                side_effect=transient_exc,
            ),
            patch("main_loop.anyio.sleep", new_callable=AsyncMock),
            pytest.raises(Exception, match="exit code 1"),
        ):
            await _run_sdk_with_retry("test prompt", opts, retries=2, base_delay=0)

    @pytest.mark.anyio
    async def test_non_transient_error_not_retried(self) -> None:
        """Non-transient errors propagate immediately without retry."""
        opts = _make_opts()
        non_transient_exc = ValueError("invalid JSON in response")
        mock_stream = AsyncMock()

        collect_mock = AsyncMock(side_effect=non_transient_exc)

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch("main_loop._collect_agent_output", collect_mock),
            pytest.raises(ValueError, match="invalid JSON"),
        ):
            await _run_sdk_with_retry("test prompt", opts, retries=2, base_delay=0)

        # Should only be called once — no retries for non-transient errors
        assert collect_mock.call_count == 1

    @pytest.mark.anyio
    async def test_backoff_delay_increases_exponentially(self) -> None:
        """Verify that delay increases exponentially with each retry."""
        opts = _make_opts()
        transient_exc = Exception("Command failed with exit code 1")
        mock_stream = AsyncMock()

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch(
                "main_loop._collect_agent_output",
                new_callable=AsyncMock,
                side_effect=transient_exc,
            ),
            patch("main_loop.anyio.sleep", side_effect=fake_sleep),
            pytest.raises(Exception, match="exit code 1"),
        ):
            await _run_sdk_with_retry("test prompt", opts, retries=3, base_delay=5)

        # exponential: 5*2^0=5, 5*2^1=10, 5*2^2=20, attempt 3 gives up (no sleep)
        assert sleep_calls == [5, 10, 20]

    @pytest.mark.anyio
    async def test_timeout_error_is_retried(self) -> None:
        """TimeoutError (from anyio.fail_after) should also be retried."""
        opts = _make_opts()
        mock_stream = AsyncMock()

        call_count = 0

        async def fake_collect(stream: object, *, timeout_seconds: float = 600) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timed out")
            return "ok"

        with (
            patch("main_loop.claude_agent_sdk.query", return_value=mock_stream),
            patch("main_loop._collect_agent_output", side_effect=fake_collect),
            patch("main_loop.anyio.sleep", new_callable=AsyncMock),
        ):
            result = await _run_sdk_with_retry("test prompt", opts, retries=1, base_delay=0)

        assert result == "ok"
        assert call_count == 2
