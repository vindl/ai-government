"""Tests for Research Scout helper functions in main_loop.py."""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    ResearchScoutOutput,
    ResearchScoutState,
    should_run_research_scout,
)

# ---------------------------------------------------------------------------
# ResearchScoutState model
# ---------------------------------------------------------------------------


class TestResearchScoutState:
    def test_create_default(self) -> None:
        state = ResearchScoutState()
        assert state.last_fetch_date == ""

    def test_create_with_date(self) -> None:
        state = ResearchScoutState(last_fetch_date="2026-02-14")
        assert state.last_fetch_date == "2026-02-14"

    def test_json_roundtrip(self) -> None:
        state = ResearchScoutState(last_fetch_date="2026-02-14")
        raw = state.model_dump_json()
        restored = ResearchScoutState.model_validate_json(raw)
        assert restored.last_fetch_date == "2026-02-14"


# ---------------------------------------------------------------------------
# should_run_research_scout()
# ---------------------------------------------------------------------------


class TestShouldRunResearchScout:
    def test_returns_true_when_no_state_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.RESEARCH_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        assert should_run_research_scout() is True

    def test_returns_false_when_scanned_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        today = _dt.date.today().isoformat()
        state_path.write_text(ResearchScoutState(last_fetch_date=today).model_dump_json())
        monkeypatch.setattr("main_loop.RESEARCH_SCOUT_STATE_PATH", state_path)
        assert should_run_research_scout() is False

    def test_returns_true_when_scanned_yesterday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state_path.write_text(ResearchScoutState(last_fetch_date=yesterday).model_dump_json())
        monkeypatch.setattr("main_loop.RESEARCH_SCOUT_STATE_PATH", state_path)
        assert should_run_research_scout() is True

    def test_returns_true_on_corrupt_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text("not json")
        monkeypatch.setattr("main_loop.RESEARCH_SCOUT_STATE_PATH", state_path)
        assert should_run_research_scout() is True

    def test_custom_interval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With interval_days=3, a scan from 1 day ago should NOT trigger."""
        state_path = tmp_path / "state.json"
        one_day_ago = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state_path.write_text(ResearchScoutState(last_fetch_date=one_day_ago).model_dump_json())
        monkeypatch.setattr("main_loop.RESEARCH_SCOUT_STATE_PATH", state_path)
        assert should_run_research_scout(interval_days=3) is False


# ---------------------------------------------------------------------------
# ResearchScoutOutput model
# ---------------------------------------------------------------------------


class TestResearchScoutOutput:
    def test_valid_output(self) -> None:
        out = ResearchScoutOutput(
            title="Upgrade to Claude Opus 4.7",
            description="New model with improved tool use. Update DEFAULT_MODEL.",
        )
        assert out.title == "Upgrade to Claude Opus 4.7"
        assert "improved tool use" in out.description

    def test_empty_title_rejected(self) -> None:
        import pytest
        with pytest.raises(Exception):  # noqa: B017
            ResearchScoutOutput(title="", description="Some description")

    def test_empty_description_rejected(self) -> None:
        import pytest
        with pytest.raises(Exception):  # noqa: B017
            ResearchScoutOutput(title="Valid title", description="")

    def test_title_length_limit(self) -> None:
        import pytest
        with pytest.raises(Exception):  # noqa: B017
            ResearchScoutOutput(title="x" * 121, description="Some description")
