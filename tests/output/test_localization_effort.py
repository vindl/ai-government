"""Tests for localization effort parameter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from government.output.localization import _translate_fields

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from claude_agent_sdk import ClaudeAgentOptions


async def _empty_stream() -> AsyncIterator[Any]:
    """Yield nothing — simulates an SDK query that returns no messages."""
    return
    yield  # make this a proper async generator


class TestTranslateFieldsEffort:
    """_translate_fields should pass effort='low' to ClaudeAgentOptions."""

    @pytest.mark.anyio
    async def test_effort_low_is_passed(self) -> None:
        """The SDK query should receive effort='low'."""
        captured_opts: list[ClaudeAgentOptions] = []

        def fake_query(
            *, prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[Any]:
            captured_opts.append(options)
            return _empty_stream()

        with patch(
            "government.output.localization.claude_agent_sdk.query",
            side_effect=fake_query,
        ):
            result = await _translate_fields(
                {"headline": "Good news"}, "claude-sonnet-4-5-20250929"
            )

        # Should fall back to originals since no response was generated
        assert result == {"headline": "Good news"}
        # Verify effort was set
        assert len(captured_opts) == 1
        assert captured_opts[0].effort == "low"

    @pytest.mark.anyio
    async def test_empty_fields_skip_sdk_call(self) -> None:
        """Empty fields should not trigger an SDK call."""
        with patch(
            "government.output.localization.claude_agent_sdk.query",
            new_callable=AsyncMock,
        ) as mock_query:
            result = await _translate_fields(
                {"headline": "", "summary": ""}, "claude-sonnet-4-5-20250929"
            )

        assert result == {"headline": "", "summary": ""}
        mock_query.assert_not_called()
