"""Tests for news scout helper functions in main_loop.py."""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    NewsScoutState,
    _generate_decision_id,
    _parse_json_array,
    should_fetch_news,
)

# ---------------------------------------------------------------------------
# NewsScoutState model
# ---------------------------------------------------------------------------


class TestNewsScoutState:
    def test_create_default(self) -> None:
        state = NewsScoutState()
        assert state.last_fetch_date == ""

    def test_create_with_date(self) -> None:
        state = NewsScoutState(last_fetch_date="2026-02-14")
        assert state.last_fetch_date == "2026-02-14"

    def test_json_roundtrip(self) -> None:
        state = NewsScoutState(last_fetch_date="2026-02-14")
        raw = state.model_dump_json()
        restored = NewsScoutState.model_validate_json(raw)
        assert restored.last_fetch_date == "2026-02-14"


# ---------------------------------------------------------------------------
# should_fetch_news()
# ---------------------------------------------------------------------------


class TestShouldFetchNews:
    def test_returns_true_when_no_state_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_false_when_fetched_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        today = _dt.date.today().isoformat()
        state_path.write_text(NewsScoutState(last_fetch_date=today).model_dump_json())
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is False

    def test_returns_true_when_fetched_yesterday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state_path.write_text(NewsScoutState(last_fetch_date=yesterday).model_dump_json())
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_true_on_corrupt_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text("not json")
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_false_when_backlog_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 3)
        assert should_fetch_news() is False

    def test_returns_false_when_backlog_over_max(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 5)
        assert should_fetch_news() is False


# ---------------------------------------------------------------------------
# _generate_decision_id()
# ---------------------------------------------------------------------------


class TestGenerateDecisionId:
    def test_deterministic(self) -> None:
        d = _dt.date(2026, 2, 14)
        id1 = _generate_decision_id("Test title", d)
        id2 = _generate_decision_id("Test title", d)
        assert id1 == id2

    def test_format(self) -> None:
        d = _dt.date(2026, 2, 14)
        result = _generate_decision_id("Vlada usvojila budžet", d)
        assert result.startswith("news-2026-02-14-")
        # 8 hex chars after the date prefix (news-YYYY-MM-DD-XXXXXXXX)
        suffix = result.rsplit("-", 1)[-1]
        assert len(suffix) == 8

    def test_different_titles_different_ids(self) -> None:
        d = _dt.date(2026, 2, 14)
        id1 = _generate_decision_id("Title A", d)
        id2 = _generate_decision_id("Title B", d)
        assert id1 != id2

    def test_different_dates_different_ids(self) -> None:
        id1 = _generate_decision_id("Same title", _dt.date(2026, 2, 14))
        id2 = _generate_decision_id("Same title", _dt.date(2026, 2, 15))
        assert id1 != id2


# ---------------------------------------------------------------------------
# _parse_json_array() — used by news scout output parsing
# ---------------------------------------------------------------------------


class TestParseJsonArray:
    def test_parses_clean_json(self) -> None:
        raw = json.dumps([{"title": "T", "summary": "S"}])
        result = _parse_json_array(raw)
        assert len(result) == 1
        assert result[0]["title"] == "T"

    def test_extracts_json_from_surrounding_text(self) -> None:
        text = 'Here are the results:\n[{"title": "X"}]\nDone.'
        result = _parse_json_array(text)
        assert len(result) == 1

    def test_returns_empty_on_no_json(self) -> None:
        assert _parse_json_array("no json here") == []

    def test_returns_empty_on_empty_string(self) -> None:
        assert _parse_json_array("") == []


# ---------------------------------------------------------------------------
# Decision JSON embedding in issue body
# ---------------------------------------------------------------------------


class TestDecisionJsonEmbedding:
    """Test that we can embed and extract GovernmentDecision JSON from issue bodies."""

    def test_roundtrip(self) -> None:
        from ai_government.models.decision import GovernmentDecision

        decision = GovernmentDecision(
            id="news-2026-02-14-abc12345",
            title="Test odluka",
            summary="Kratak opis odluke",
            full_text="Puni tekst",
            date=_dt.date(2026, 2, 14),
            source_url="https://vijesti.me/test",
            category="fiscal",
            tags=["budzet"],
        )

        # Simulate what create_analysis_issue() does
        decision_json = decision.model_dump_json(indent=2)
        body = (
            f"**Decision ID**: {decision.id}\n"
            f"**Date**: {decision.date}\n"
            f"**Category**: {decision.category}\n\n"
            f"> {decision.summary}\n\n"
            f"Run full AI cabinet analysis on this decision.\n\n"
            f"<details><summary>Decision JSON</summary>\n\n"
            f"```json\n{decision_json}\n```\n</details>"
        )

        # Simulate what step_execute_analysis() does to parse it back
        json_match = re.search(r"```json\n(.*?)\n```", body, re.DOTALL)
        assert json_match is not None
        restored = GovernmentDecision.model_validate_json(json_match.group(1))
        assert restored.id == decision.id
        assert restored.title == decision.title
        assert restored.category == decision.category
        assert restored.date == decision.date
