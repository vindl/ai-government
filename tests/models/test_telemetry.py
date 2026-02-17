"""Tests for CycleTelemetry model and JSONL I/O."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from government.models.telemetry import (
    CyclePhaseResult,
    CycleTelemetry,
    append_telemetry,
    load_telemetry,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestCyclePhaseResult:
    def test_create_defaults(self) -> None:
        phase = CyclePhaseResult(phase="A")
        assert phase.phase == "A"
        assert phase.success is True
        assert phase.duration_seconds == 0.0
        assert phase.detail == ""

    def test_create_full(self) -> None:
        phase = CyclePhaseResult(
            phase="C", success=False, duration_seconds=42.5, detail="PR workflow exited with code 1",
        )
        assert phase.success is False
        assert phase.duration_seconds == 42.5


class TestCycleTelemetry:
    def test_create_minimal(self) -> None:
        t = CycleTelemetry(cycle=1)
        assert t.cycle == 1
        assert t.finished_at is None
        assert t.errors == []
        assert t.phases == []
        assert t.cycle_yielded is False

    def test_create_full(self) -> None:
        now = datetime.now(UTC)
        t = CycleTelemetry(
            cycle=5,
            started_at=now,
            finished_at=now,
            duration_seconds=120.0,
            decisions_found=3,
            analysis_issues_created=2,
            proposals_made=1,
            proposals_accepted=1,
            proposals_rejected=0,
            human_suggestions_ingested=1,
            picked_issue_number=42,
            picked_issue_type="code-change",
            execution_success=True,
            director_ran=True,
            director_issues_filed=1,
            cycle_yielded=True,
            human_overrides=0,
            tweet_posted=True,
            phases=[CyclePhaseResult(phase="A", duration_seconds=10.0)],
            errors=[],
            dry_run=False,
        )
        assert t.cycle == 5
        assert t.cycle_yielded is True
        assert len(t.phases) == 1

    def test_json_roundtrip(self) -> None:
        t = CycleTelemetry(
            cycle=3,
            decisions_found=1,
            errors=["something broke"],
            phases=[CyclePhaseResult(phase="B", success=False, detail="debate failed")],
        )
        json_str = t.model_dump_json()
        restored = CycleTelemetry.model_validate_json(json_str)
        assert restored.cycle == t.cycle
        assert restored.errors == t.errors
        assert len(restored.phases) == 1
        assert restored.phases[0].success is False


class TestTelemetryIO:
    def test_append_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"

        e1 = CycleTelemetry(cycle=1, decisions_found=2)
        e2 = CycleTelemetry(cycle=2, proposals_made=3)

        append_telemetry(path, e1)
        append_telemetry(path, e2)

        entries = load_telemetry(path)
        assert len(entries) == 2
        assert entries[0].cycle == 1
        assert entries[0].decisions_found == 2
        assert entries[1].cycle == 2
        assert entries[1].proposals_made == 3

    def test_load_last_n(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"

        for i in range(5):
            append_telemetry(path, CycleTelemetry(cycle=i + 1))

        last_two = load_telemetry(path, last_n=2)
        assert len(last_two) == 2
        assert last_two[0].cycle == 4
        assert last_two[1].cycle == 5

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        path = tmp_path / "does_not_exist.jsonl"
        assert load_telemetry(path) == []

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "telemetry.jsonl"
        append_telemetry(path, CycleTelemetry(cycle=1))
        assert path.exists()
        entries = load_telemetry(path)
        assert len(entries) == 1

    def test_rolling_window_prunes_old_entries(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        old_time = datetime.now(UTC) - timedelta(days=10)
        recent_time = datetime.now(UTC) - timedelta(days=1)

        old_entry = CycleTelemetry(cycle=1, started_at=old_time)
        recent_entry = CycleTelemetry(cycle=2, started_at=recent_time)

        # Seed with old + recent entries
        append_telemetry(path, old_entry, max_age_days=30)
        append_telemetry(path, recent_entry, max_age_days=30)

        entries = load_telemetry(path)
        assert len(entries) == 2

        # Now append with a 5-day window — the 10-day-old entry should be pruned
        new_entry = CycleTelemetry(cycle=3)
        append_telemetry(path, new_entry, max_age_days=5)

        entries = load_telemetry(path)
        assert len(entries) == 2
        assert entries[0].cycle == 2
        assert entries[1].cycle == 3

    def test_rolling_window_keeps_unparseable_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        # Write a malformed line directly
        path.write_text("not valid json\n")

        # Append a real entry — the malformed line should be preserved
        append_telemetry(path, CycleTelemetry(cycle=1), max_age_days=30)

        raw_lines = path.read_text().strip().splitlines()
        assert len(raw_lines) == 2
        assert raw_lines[0] == "not valid json"

    def test_rolling_window_prunes_all_old(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        old_time = datetime.now(UTC) - timedelta(days=60)

        for i in range(3):
            entry = CycleTelemetry(cycle=i + 1, started_at=old_time)
            # Use a large window so they aren't pruned during seeding
            append_telemetry(path, entry, max_age_days=90)

        entries = load_telemetry(path)
        assert len(entries) == 3

        # Now append with a tight window — all old entries should be pruned
        new_entry = CycleTelemetry(cycle=4)
        append_telemetry(path, new_entry, max_age_days=30)

        entries = load_telemetry(path)
        assert len(entries) == 1
        assert entries[0].cycle == 4
