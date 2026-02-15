"""Tests for analysis rate limiting in main_loop.py."""

from __future__ import annotations

import datetime as _dt
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    AnalysisState,
    _load_analysis_state,
    _record_analysis_completion,
    _save_analysis_state,
    analysis_wait_seconds,
    should_run_analysis,
)

# ---------------------------------------------------------------------------
# AnalysisState model
# ---------------------------------------------------------------------------


class TestAnalysisState:
    def test_create_default(self) -> None:
        state = AnalysisState()
        assert state.analyses_completed_today == 0
        assert state.last_analysis_date == ""
        assert state.last_analysis_completed_at == ""

    def test_create_with_data(self) -> None:
        state = AnalysisState(
            analyses_completed_today=2,
            last_analysis_date="2026-02-14",
            last_analysis_completed_at="2026-02-14T10:30:00+00:00",
        )
        assert state.analyses_completed_today == 2
        assert state.last_analysis_date == "2026-02-14"
        assert state.last_analysis_completed_at == "2026-02-14T10:30:00+00:00"

    def test_json_roundtrip(self) -> None:
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date="2026-02-14",
            last_analysis_completed_at="2026-02-14T15:00:00+00:00",
        )
        raw = state.model_dump_json()
        restored = AnalysisState.model_validate_json(raw)
        assert restored.analyses_completed_today == 1
        assert restored.last_analysis_date == "2026-02-14"
        assert restored.last_analysis_completed_at == "2026-02-14T15:00:00+00:00"


# ---------------------------------------------------------------------------
# _load_analysis_state() and _save_analysis_state()
# ---------------------------------------------------------------------------


class TestAnalysisStatePersistence:
    def test_load_returns_empty_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", tmp_path / "nonexistent.json")
        state = _load_analysis_state()
        assert state.analyses_completed_today == 0
        assert state.last_analysis_date == ""

    def test_load_returns_empty_on_corrupt_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text("not json")
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)
        state = _load_analysis_state()
        assert state.analyses_completed_today == 0

    def test_save_and_load_roundtrip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        state = AnalysisState(
            analyses_completed_today=2,
            last_analysis_date="2026-02-14",
            last_analysis_completed_at="2026-02-14T10:00:00+00:00",
        )
        _save_analysis_state(state)

        loaded = _load_analysis_state()
        assert loaded.analyses_completed_today == 2
        assert loaded.last_analysis_date == "2026-02-14"
        assert loaded.last_analysis_completed_at == "2026-02-14T10:00:00+00:00"


# ---------------------------------------------------------------------------
# _record_analysis_completion()
# ---------------------------------------------------------------------------


class TestRecordAnalysisCompletion:
    def test_first_completion_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        _record_analysis_completion()

        state = _load_analysis_state()
        assert state.analyses_completed_today == 1
        assert state.last_analysis_date == _dt.date.today().isoformat()
        assert state.last_analysis_completed_at != ""
        # Check timestamp is recent (within last minute)
        ts = datetime.fromisoformat(state.last_analysis_completed_at)
        assert (datetime.now(UTC) - ts).total_seconds() < 60

    def test_second_completion_same_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Record first completion
        _record_analysis_completion()
        state1 = _load_analysis_state()
        assert state1.analyses_completed_today == 1

        # Record second completion
        _record_analysis_completion()
        state2 = _load_analysis_state()
        assert state2.analyses_completed_today == 2
        assert state2.last_analysis_date == _dt.date.today().isoformat()

    def test_resets_counter_on_new_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Set up state from yesterday
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        old_state = AnalysisState(
            analyses_completed_today=3,
            last_analysis_date=yesterday,
            last_analysis_completed_at=f"{yesterday}T15:00:00+00:00",
        )
        _save_analysis_state(old_state)

        # Record completion today
        _record_analysis_completion()

        state = _load_analysis_state()
        assert state.analyses_completed_today == 1
        assert state.last_analysis_date == _dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# should_run_analysis()
# ---------------------------------------------------------------------------


class TestShouldRunAnalysis:
    def test_returns_true_when_no_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", tmp_path / "nonexistent.json")
        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is True

    def test_returns_true_on_new_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # State from yesterday
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state = AnalysisState(
            analyses_completed_today=3,
            last_analysis_date=yesterday,
            last_analysis_completed_at=f"{yesterday}T15:00:00+00:00",
        )
        _save_analysis_state(state)

        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is True

    def test_returns_false_when_daily_cap_reached(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Already completed 3 analyses today
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=3,
            last_analysis_date=today,
            last_analysis_completed_at=f"{today}T10:00:00+00:00",
        )
        _save_analysis_state(state)

        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is False

    def test_returns_false_when_gap_too_small(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Last analysis was 2 hours ago
        now = datetime.now(UTC)
        two_hours_ago = now - timedelta(hours=2)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=two_hours_ago.isoformat(),
        )
        _save_analysis_state(state)

        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is False

    def test_returns_true_when_gap_sufficient(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Last analysis was 6 hours ago
        now = datetime.now(UTC)
        six_hours_ago = now - timedelta(hours=6)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=six_hours_ago.isoformat(),
        )
        _save_analysis_state(state)

        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is True

    def test_returns_true_when_first_analysis_of_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Today with 0 completed analyses
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=0,
            last_analysis_date=today,
            last_analysis_completed_at="",
        )
        _save_analysis_state(state)

        assert should_run_analysis(max_per_day=3, min_gap_hours=5) is True

    def test_respects_custom_max_per_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # 2 analyses completed today
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=2,
            last_analysis_date=today,
            last_analysis_completed_at=f"{today}T08:00:00+00:00",
        )
        _save_analysis_state(state)

        # With max 3/day, should be allowed
        assert should_run_analysis(max_per_day=3, min_gap_hours=0) is True
        # With max 2/day, should be blocked
        assert should_run_analysis(max_per_day=2, min_gap_hours=0) is False

    def test_respects_custom_min_gap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        # Last analysis was 2 hours ago
        now = datetime.now(UTC)
        two_hours_ago = now - timedelta(hours=2)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=two_hours_ago.isoformat(),
        )
        _save_analysis_state(state)

        # With 5h gap, should be blocked
        assert should_run_analysis(max_per_day=10, min_gap_hours=5) is False
        # With 1h gap, should be allowed
        assert should_run_analysis(max_per_day=10, min_gap_hours=1) is True


# ---------------------------------------------------------------------------
# analysis_wait_seconds()
# ---------------------------------------------------------------------------


class TestAnalysisWaitSeconds:
    def test_returns_zero_when_no_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", tmp_path / "nonexistent.json")
        assert analysis_wait_seconds(min_gap_hours=5) == 0

    def test_returns_zero_on_new_day(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state = AnalysisState(
            analyses_completed_today=3,
            last_analysis_date=yesterday,
            last_analysis_completed_at=f"{yesterday}T15:00:00+00:00",
        )
        _save_analysis_state(state)

        assert analysis_wait_seconds(min_gap_hours=5) == 0

    def test_returns_remaining_seconds_when_gap_not_met(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        now = datetime.now(UTC)
        two_hours_ago = now - timedelta(hours=2)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=two_hours_ago.isoformat(),
        )
        _save_analysis_state(state)

        wait = analysis_wait_seconds(min_gap_hours=5)
        # Should be ~3 hours = ~10800 seconds (allow some tolerance)
        assert 10700 < wait < 10900

    def test_returns_zero_when_gap_exceeded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        now = datetime.now(UTC)
        six_hours_ago = now - timedelta(hours=6)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=six_hours_ago.isoformat(),
        )
        _save_analysis_state(state)

        assert analysis_wait_seconds(min_gap_hours=5) == 0

    def test_returns_zero_when_no_gap_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("main_loop.ANALYSIS_STATE_PATH", state_path)

        now = datetime.now(UTC)
        one_minute_ago = now - timedelta(minutes=1)
        today = _dt.date.today().isoformat()
        state = AnalysisState(
            analyses_completed_today=1,
            last_analysis_date=today,
            last_analysis_completed_at=one_minute_ago.isoformat(),
        )
        _save_analysis_state(state)

        assert analysis_wait_seconds(min_gap_hours=0) == 0
