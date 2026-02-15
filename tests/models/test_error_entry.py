"""Tests for ErrorEntry model and JSONL I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_government.models.telemetry import (
    ErrorEntry,
    append_error,
    load_errors,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestErrorEntry:
    def test_create_defaults(self) -> None:
        entry = ErrorEntry(step="step_execute_code_change")
        assert entry.step == "step_execute_code_change"
        assert entry.issue_number is None
        assert entry.pr_number is None
        assert entry.error_type == ""
        assert entry.message == ""
        assert entry.traceback == ""
        assert entry.timestamp is not None

    def test_create_full(self) -> None:
        entry = ErrorEntry(
            step="step_execute_code_change",
            issue_number=163,
            pr_number=166,
            error_type="CalledProcessError",
            message="gh pr merge failed with GraphQL error",
            traceback="Traceback (most recent call last):\n  ...",
        )
        assert entry.issue_number == 163
        assert entry.pr_number == 166
        assert entry.error_type == "CalledProcessError"

    def test_from_exception(self) -> None:
        try:
            raise ValueError("test error message")
        except ValueError as exc:
            entry = ErrorEntry.from_exception(
                "step_execute_analysis",
                exc,
                issue_number=42,
            )

        assert entry.step == "step_execute_analysis"
        assert entry.error_type == "ValueError"
        assert entry.message == "test error message"
        assert entry.issue_number == 42
        assert entry.pr_number is None
        assert "ValueError: test error message" in entry.traceback

    def test_from_exception_with_pr(self) -> None:
        exc = RuntimeError("merge failed")
        entry = ErrorEntry.from_exception(
            "step_execute_code_change",
            exc,
            issue_number=100,
            pr_number=200,
        )
        assert entry.pr_number == 200
        assert entry.error_type == "RuntimeError"

    def test_json_roundtrip(self) -> None:
        entry = ErrorEntry(
            step="step_director",
            issue_number=10,
            error_type="TimeoutError",
            message="agent timed out",
        )
        json_str = entry.model_dump_json()
        restored = ErrorEntry.model_validate_json(json_str)
        assert restored.step == entry.step
        assert restored.issue_number == entry.issue_number
        assert restored.error_type == entry.error_type
        assert restored.message == entry.message


class TestErrorIO:
    def test_append_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "errors.jsonl"

        e1 = ErrorEntry(step="step_a", error_type="ValueError", message="bad value")
        e2 = ErrorEntry(step="step_b", error_type="RuntimeError", message="timeout")

        append_error(path, e1)
        append_error(path, e2)

        entries = load_errors(path)
        assert len(entries) == 2
        assert entries[0].step == "step_a"
        assert entries[1].step == "step_b"

    def test_load_last_n(self, tmp_path: Path) -> None:
        path = tmp_path / "errors.jsonl"

        for i in range(5):
            append_error(path, ErrorEntry(step=f"step_{i}", message=f"err {i}"))

        last_two = load_errors(path, last_n=2)
        assert len(last_two) == 2
        assert last_two[0].step == "step_3"
        assert last_two[1].step == "step_4"

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        path = tmp_path / "does_not_exist.jsonl"
        assert load_errors(path) == []

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "errors.jsonl"
        append_error(path, ErrorEntry(step="step_x"))
        assert path.exists()
        entries = load_errors(path)
        assert len(entries) == 1
