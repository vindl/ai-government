"""Tests for gap observation flow (PM → Directors via GitHub issues)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Add scripts to path so we can import from main_loop
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from main_loop import (  # noqa: E402
    LABEL_BACKLOG,
    LABEL_GAP_CONTENT,
    LABEL_GAP_TECHNICAL,
    _prefetch_director_context,
    _prefetch_strategic_context,
)


def make_issue(
    number: int,
    title: str,
    *,
    labels: list[str] | None = None,
    body: str = "",
    created_at: str = "2026-02-15T00:00:00Z",
) -> dict[str, Any]:
    """Helper to create a mock issue dict."""
    label_objs = [{"name": label} for label in (labels or [])]
    return {
        "number": number,
        "title": title,
        "body": body,
        "createdAt": created_at,
        "labels": label_objs,
    }


# ---------------------------------------------------------------------------
# list_backlog_issues: gap issues are excluded
# ---------------------------------------------------------------------------


def test_list_backlog_excludes_gap_content_issues() -> None:
    """Issues labeled gap:content should be filtered from the backlog."""
    issues = [
        make_issue(1, "Normal task", labels=[LABEL_BACKLOG]),
        make_issue(2, "Content gap", labels=[LABEL_BACKLOG, LABEL_GAP_CONTENT]),
        make_issue(3, "Another task", labels=[LABEL_BACKLOG]),
    ]

    gap_labels = {LABEL_GAP_CONTENT, LABEL_GAP_TECHNICAL}
    filtered = [
        i for i in issues
        if not any(
            lbl.get("name") in gap_labels
            for lbl in i.get("labels", [])
        )
    ]

    assert len(filtered) == 2
    assert all(i["number"] != 2 for i in filtered)


def test_list_backlog_excludes_gap_technical_issues() -> None:
    """Issues labeled gap:technical should be filtered from the backlog."""
    issues = [
        make_issue(1, "Normal task", labels=[LABEL_BACKLOG]),
        make_issue(2, "Tech gap", labels=[LABEL_BACKLOG, LABEL_GAP_TECHNICAL]),
    ]

    gap_labels = {LABEL_GAP_CONTENT, LABEL_GAP_TECHNICAL}
    filtered = [
        i for i in issues
        if not any(
            lbl.get("name") in gap_labels
            for lbl in i.get("labels", [])
        )
    ]

    assert len(filtered) == 1
    assert filtered[0]["number"] == 1


def test_list_backlog_keeps_normal_issues() -> None:
    """Normal backlog issues without gap labels should pass through."""
    issues = [
        make_issue(1, "Task A", labels=[LABEL_BACKLOG]),
        make_issue(2, "Task B", labels=[LABEL_BACKLOG, "director-suggestion"]),
    ]

    gap_labels = {LABEL_GAP_CONTENT, LABEL_GAP_TECHNICAL}
    filtered = [
        i for i in issues
        if not any(
            lbl.get("name") in gap_labels
            for lbl in i.get("labels", [])
        )
    ]

    assert len(filtered) == 2


# ---------------------------------------------------------------------------
# _prefetch_director_context: includes gap:technical issues
# ---------------------------------------------------------------------------


def _mock_run_gh_with_gaps(
    gap_label: str,
    gap_issues: list[dict[str, Any]],
) -> Any:
    """Create a _run_gh mock that returns gap issues for the right label query."""

    def _mock(args: list[str], *, check: bool = True) -> Any:
        m = MagicMock()
        m.returncode = 0

        # Check if this is the gap issue query
        if "--label" in args and gap_label in args:
            m.stdout = json.dumps(gap_issues)
        elif "run" in args and "list" in args:
            # CI runs
            m.stdout = "[]"
        elif "issue" in args and "list" in args:
            # Generic issue list
            m.stdout = "[]"
        elif "pr" in args and "list" in args:
            # PR list
            m.stdout = "[]"
        else:
            m.stdout = "[]"

        return m

    return _mock


def test_director_context_includes_technical_gaps() -> None:
    """Director context should include open gap:technical issues."""
    gap_issues = [
        {
            "number": 42,
            "title": "CI failures go unnoticed",
            "body": "CI failures are not detected between director reviews.",
            "createdAt": "2026-02-14T00:00:00Z",
        },
    ]

    mock_fn = _mock_run_gh_with_gaps(LABEL_GAP_TECHNICAL, gap_issues)

    with patch("main_loop._run_gh", side_effect=mock_fn), \
         patch("main_loop.load_telemetry", return_value=[]):
        context = _prefetch_director_context(last_n_cycles=5)

    assert "Technical Gap Observations" in context
    assert "#42" in context
    assert "CI failures go unnoticed" in context


def test_director_context_omits_section_when_no_gaps() -> None:
    """Director context should not have a gap section when no gap issues exist."""
    mock_fn = _mock_run_gh_with_gaps(LABEL_GAP_TECHNICAL, [])

    with patch("main_loop._run_gh", side_effect=mock_fn), \
         patch("main_loop.load_telemetry", return_value=[]):
        context = _prefetch_director_context(last_n_cycles=5)

    assert "Technical Gap Observations" not in context


# ---------------------------------------------------------------------------
# _prefetch_strategic_context: includes gap:content issues
# ---------------------------------------------------------------------------


def test_strategic_context_includes_content_gaps() -> None:
    """Strategic director context should include open gap:content issues."""
    gap_issues = [
        {
            "number": 99,
            "title": "No coverage of EU accession implications",
            "body": "Analyses consistently miss EU accession context.",
            "createdAt": "2026-02-13T00:00:00Z",
        },
    ]

    mock_fn = _mock_run_gh_with_gaps(LABEL_GAP_CONTENT, gap_issues)

    with patch("main_loop._run_gh", side_effect=mock_fn), \
         patch("main_loop.load_telemetry", return_value=[]):
        context = _prefetch_strategic_context(last_n_cycles=5)

    assert "Content Gap Observations" in context
    assert "#99" in context
    assert "No coverage of EU accession implications" in context


def test_strategic_context_omits_section_when_no_gaps() -> None:
    """Strategic context should not have a gap section when no gap issues exist."""
    mock_fn = _mock_run_gh_with_gaps(LABEL_GAP_CONTENT, [])

    with patch("main_loop._run_gh", side_effect=mock_fn), \
         patch("main_loop.load_telemetry", return_value=[]):
        context = _prefetch_strategic_context(last_n_cycles=5)

    assert "Content Gap Observations" not in context


# ---------------------------------------------------------------------------
# Label constants: gap labels are defined and distinct
# ---------------------------------------------------------------------------


def test_gap_labels_are_distinct() -> None:
    """gap:content and gap:technical labels must be different."""
    assert LABEL_GAP_CONTENT != LABEL_GAP_TECHNICAL


def test_gap_labels_have_correct_prefix() -> None:
    """Both gap labels should start with 'gap:'."""
    assert LABEL_GAP_CONTENT.startswith("gap:")
    assert LABEL_GAP_TECHNICAL.startswith("gap:")
