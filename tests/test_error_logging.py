"""Tests for structured error logging (_log_error) in main_loop."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts to path so we can import from main_loop
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from government.models.telemetry import load_errors  # noqa: E402
from main_loop import _log_error  # noqa: E402


def test_log_error_creates_file(tmp_path: Path) -> None:
    """_log_error creates the errors.jsonl file and appends an entry."""
    errors_path = tmp_path / "errors.jsonl"
    with patch("main_loop.ERRORS_PATH", errors_path):
        _log_error("step_execute_code_change", RuntimeError("merge failed"))

    entries = load_errors(errors_path)
    assert len(entries) == 1
    assert entries[0].step == "step_execute_code_change"
    assert entries[0].error_type == "RuntimeError"
    assert entries[0].message == "merge failed"
    assert entries[0].issue_number is None


def test_log_error_with_issue_and_pr(tmp_path: Path) -> None:
    """_log_error persists issue_number and pr_number."""
    errors_path = tmp_path / "errors.jsonl"
    with patch("main_loop.ERRORS_PATH", errors_path):
        _log_error(
            "step_execute_code_change",
            ValueError("bad data"),
            issue_number=163,
            pr_number=166,
        )

    entries = load_errors(errors_path)
    assert len(entries) == 1
    assert entries[0].issue_number == 163
    assert entries[0].pr_number == 166


def test_log_error_appends_multiple(tmp_path: Path) -> None:
    """Multiple _log_error calls append to the same file."""
    errors_path = tmp_path / "errors.jsonl"
    with patch("main_loop.ERRORS_PATH", errors_path):
        _log_error("step_a", RuntimeError("err 1"))
        _log_error("step_b", ValueError("err 2"), issue_number=10)

    entries = load_errors(errors_path)
    assert len(entries) == 2
    assert entries[0].step == "step_a"
    assert entries[1].step == "step_b"


def test_log_error_includes_traceback(tmp_path: Path) -> None:
    """_log_error captures the traceback from the exception."""
    errors_path = tmp_path / "errors.jsonl"
    try:
        raise TypeError("type mismatch")
    except TypeError as exc:
        with patch("main_loop.ERRORS_PATH", errors_path):
            _log_error("step_execute_analysis", exc, issue_number=42)

    entries = load_errors(errors_path)
    assert len(entries) == 1
    assert "TypeError: type mismatch" in entries[0].traceback
    assert "test_log_error_includes_traceback" in entries[0].traceback


def test_log_error_never_raises(tmp_path: Path) -> None:
    """_log_error swallows its own errors (never breaks the main loop)."""
    # Force append_error to fail by making ERRORS_PATH point to a read-only location
    with patch("main_loop.ERRORS_PATH", Path("/dev/null/impossible/path")):
        # Should not raise
        _log_error("step_x", RuntimeError("test"))
