"""Tests for tweet_posted telemetry tracking in main_loop."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from government.models.telemetry import CycleTelemetry

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import step_execute_analysis  # noqa: E402


def _make_issue(number: int = 1, body: str = "") -> dict[str, object]:
    return {"number": number, "title": "Test analysis", "body": body}


def _fake_decision_body() -> str:
    """Return an issue body with an embedded decision JSON block."""
    return (
        "```json\n"
        '{"id": "test-1", "title": "Test", "date": "2025-01-01", '
        '"source_url": "https://example.com", "category": "test", '
        '"summary": "A test decision"}\n'
        "```"
    )


def _mock_session_result() -> MagicMock:
    """Create a mock SessionResult that passes health check."""
    result = MagicMock()
    result.decision.id = "test-1"
    health = MagicMock()
    health.passed = True
    health.failures = []
    result.check_health.return_value = health
    return result


# Patches needed to avoid real I/O in step_execute_analysis
_COMMON_PATCHES = [
    "main_loop.mark_issue_in_progress",
    "main_loop.mark_issue_done",
    "main_loop._run_gh",
    "main_loop._record_analysis_completion",
    "main_loop._commit_output_data",
    "main_loop.render_scorecard",
    "main_loop.save_result_json",
]


def _apply_common_patches(stack: contextlib.ExitStack, result: MagicMock) -> None:
    """Apply common patches via an ExitStack."""
    for p in _COMMON_PATCHES:
        stack.enter_context(patch(p, MagicMock()))
    stack.enter_context(patch("main_loop.step_editorial_review", new_callable=AsyncMock))
    mock_orch = MagicMock()
    mock_orch.run_session = AsyncMock(return_value=[result])
    stack.enter_context(patch("main_loop.Orchestrator", return_value=mock_orch))


@pytest.mark.anyio
async def test_tweet_posted_sets_telemetry_true() -> None:
    """When try_post_analysis returns True, telemetry.tweet_posted must be True."""
    telemetry = CycleTelemetry(cycle=1)
    assert telemetry.tweet_posted is False

    result = _mock_session_result()
    with contextlib.ExitStack() as stack:
        _apply_common_patches(stack, result)
        stack.enter_context(patch("main_loop.try_post_analysis", return_value=True))
        success = await step_execute_analysis(
            _make_issue(body=_fake_decision_body()),
            model="test-model",
            telemetry=telemetry,
        )

    assert success is True
    assert telemetry.tweet_posted is True


@pytest.mark.anyio
async def test_tweet_posted_stays_false_when_tweet_fails() -> None:
    """When try_post_analysis returns False, telemetry.tweet_posted stays False."""
    telemetry = CycleTelemetry(cycle=1)
    result = _mock_session_result()

    with contextlib.ExitStack() as stack:
        _apply_common_patches(stack, result)
        stack.enter_context(patch("main_loop.try_post_analysis", return_value=False))
        success = await step_execute_analysis(
            _make_issue(body=_fake_decision_body()),
            model="test-model",
            telemetry=telemetry,
        )

    assert success is True
    assert telemetry.tweet_posted is False


@pytest.mark.anyio
async def test_tweet_posted_stays_false_when_tweet_raises() -> None:
    """When try_post_analysis raises, telemetry.tweet_posted stays False."""
    telemetry = CycleTelemetry(cycle=1)
    result = _mock_session_result()

    with contextlib.ExitStack() as stack:
        _apply_common_patches(stack, result)
        stack.enter_context(
            patch("main_loop.try_post_analysis", side_effect=RuntimeError("API down"))
        )
        success = await step_execute_analysis(
            _make_issue(body=_fake_decision_body()),
            model="test-model",
            telemetry=telemetry,
        )

    assert success is True
    assert telemetry.tweet_posted is False


@pytest.mark.anyio
async def test_tweet_posted_no_telemetry_param() -> None:
    """When telemetry is None (backward compat), no error is raised."""
    result = _mock_session_result()

    with contextlib.ExitStack() as stack:
        _apply_common_patches(stack, result)
        stack.enter_context(patch("main_loop.try_post_analysis", return_value=True))
        success = await step_execute_analysis(
            _make_issue(body=_fake_decision_body()),
            model="test-model",
        )

    assert success is True
