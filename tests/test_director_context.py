"""Tests for enriched director context helpers in main_loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Add scripts to path so we can import from main_loop
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from government.models.telemetry import CyclePhaseResult, CycleTelemetry  # noqa: E402
from main_loop import (  # noqa: E402
    _build_agent_performance_section,
    _build_ci_results_section,
    _build_error_distribution_section,
    _build_skipped_news_section,
)

# ---------------------------------------------------------------------------
# _build_error_distribution_section
# ---------------------------------------------------------------------------


def test_error_distribution_no_errors() -> None:
    """Returns 'No errors' message when entries have no errors."""
    entries = [
        CycleTelemetry(cycle=1, errors=[]),
        CycleTelemetry(cycle=2, errors=[]),
    ]
    result = _build_error_distribution_section(entries)
    assert "No errors" in result


def test_error_distribution_counts_patterns() -> None:
    """Groups errors by first-line pattern and counts occurrences."""
    entries = [
        CycleTelemetry(cycle=1, errors=[
            "ValueError: bad input\nTraceback...",
            "TimeoutError: agent timed out",
        ]),
        CycleTelemetry(cycle=2, errors=[
            "ValueError: bad input\nDifferent traceback",
            "TimeoutError: agent timed out",
        ]),
        CycleTelemetry(cycle=3, errors=[
            "ValueError: bad input",
        ]),
    ]
    result = _build_error_distribution_section(entries)
    assert "ValueError: bad input" in result
    assert "3x" in result
    assert "TimeoutError: agent timed out" in result
    assert "2x" in result


def test_error_distribution_empty_entries() -> None:
    """Returns 'No errors' for empty entry list."""
    result = _build_error_distribution_section([])
    assert "No errors" in result


# ---------------------------------------------------------------------------
# _build_agent_performance_section
# ---------------------------------------------------------------------------


def test_agent_performance_no_phases() -> None:
    """Returns 'No phase-level data' when no phases recorded."""
    entries = [CycleTelemetry(cycle=1, phases=[])]
    result = _build_agent_performance_section(entries)
    assert "No phase-level data" in result


def test_agent_performance_computes_stats() -> None:
    """Computes run count, failure rate, avg/max duration per phase."""
    entries = [
        CycleTelemetry(cycle=1, phases=[
            CyclePhaseResult(phase="A", success=True, duration_seconds=10.0),
            CyclePhaseResult(phase="B", success=True, duration_seconds=20.0),
        ]),
        CycleTelemetry(cycle=2, phases=[
            CyclePhaseResult(phase="A", success=False, duration_seconds=30.0),
            CyclePhaseResult(phase="B", success=True, duration_seconds=5.0),
        ]),
    ]
    result = _build_agent_performance_section(entries)
    assert "Phase A" in result
    assert "Phase B" in result
    # Phase A: 2 runs, 1 failure (50%), avg 20.0s, max 30.0s
    assert "2 runs" in result
    assert "1 failures" in result
    assert "50%" in result
    # Phase B: 2 runs, 0 failures
    assert "0 failures" in result


# ---------------------------------------------------------------------------
# _build_ci_results_section
# ---------------------------------------------------------------------------


def _mock_run_gh_ci(args: list[str], *, check: bool = True) -> Any:
    """Mock _run_gh that returns CI run data."""
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    if "run" in args and "list" in args:
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {"conclusion": "success", "event": "push", "name": "CI",
             "createdAt": "2026-02-15T10:00:00Z", "headBranch": "main"},
            {"conclusion": "failure", "event": "push", "name": "CI",
             "createdAt": "2026-02-14T10:00:00Z", "headBranch": "main"},
            {"conclusion": "success", "event": "push", "name": "CI",
             "createdAt": "2026-02-13T10:00:00Z", "headBranch": "main"},
        ])
    else:
        mock_result.returncode = 1
        mock_result.stdout = ""
    return mock_result


def test_ci_results_parses_runs() -> None:
    """Parses CI runs and shows conclusion summary."""
    with patch("main_loop._run_gh", side_effect=_mock_run_gh_ci):
        result = _build_ci_results_section()
    assert "success: 2" in result
    assert "failure: 1" in result
    assert "CI" in result


def test_ci_results_handles_gh_failure() -> None:
    """Returns fallback message when gh command fails."""
    from unittest.mock import MagicMock

    def _fail(args: list[str], *, check: bool = True) -> Any:
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    with patch("main_loop._run_gh", side_effect=_fail):
        result = _build_ci_results_section()
    assert "No CI data" in result


def test_ci_results_handles_empty_runs() -> None:
    """Returns message when no CI runs found."""
    from unittest.mock import MagicMock

    def _empty(args: list[str], *, check: bool = True) -> Any:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]"
        return m

    with patch("main_loop._run_gh", side_effect=_empty):
        result = _build_ci_results_section()
    assert "No CI runs found" in result


# ---------------------------------------------------------------------------
# _build_skipped_news_section
# ---------------------------------------------------------------------------


def test_skipped_news_parses_rejected_issues() -> None:
    """Parses rejected issues and lists them."""
    from unittest.mock import MagicMock

    def _mock(args: list[str], *, check: bool = True) -> Any:
        m = MagicMock()
        m.returncode = 0
        m.stdout = json.dumps([
            {"title": "Infrastructure spending cut", "closedAt": "2026-02-10T00:00:00Z"},
            {"title": "Minor tax adjustment", "closedAt": "2026-02-09T00:00:00Z"},
        ])
        return m

    with patch("main_loop._run_gh", side_effect=_mock):
        result = _build_skipped_news_section()
    assert "Infrastructure spending cut" in result
    assert "Minor tax adjustment" in result
    assert "2026-02-10" in result


def test_skipped_news_handles_none() -> None:
    """Returns fallback when no rejected issues exist."""
    from unittest.mock import MagicMock

    def _empty(args: list[str], *, check: bool = True) -> Any:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "[]"
        return m

    with patch("main_loop._run_gh", side_effect=_empty):
        result = _build_skipped_news_section()
    assert "No rejected issues" in result


# ---------------------------------------------------------------------------
# _build_agent_roster_section (integration: uses real agent factories)
# ---------------------------------------------------------------------------


def test_agent_roster_lists_all_ministries() -> None:
    """Agent roster section lists all 7 ministry agents."""
    from main_loop import _build_agent_roster_section

    result = _build_agent_roster_section()
    assert "Finance" in result
    assert "Justice" in result
    assert "EU Integration" in result
    assert "Health" in result
    assert "Interior" in result
    assert "Education" in result
    assert "Economy" in result
    assert "Agent Roster" in result
