"""Tests for load_results_from_dir resilience to non-SessionResult JSON files."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

from ai_government.models.assessment import Assessment, Verdict

if TYPE_CHECKING:
    from pathlib import Path
from ai_government.models.decision import GovernmentDecision
from ai_government.orchestrator import SessionResult
from ai_government.output.site_builder import load_results_from_dir


def _make_session_result(id: str = "d1") -> SessionResult:
    decision = GovernmentDecision(
        id=id,
        title="Test Decision",
        summary="A test decision",
        date=datetime.date(2026, 2, 10),
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id=id,
        score=5,
        verdict=Verdict.NEUTRAL,
        summary="Summary",
        reasoning="Reasoning",
    )
    return SessionResult(decision=decision, assessments=[assessment])


class TestLoadResultsFromDir:
    def test_loads_valid_session_results(self, tmp_path: Path) -> None:
        result = _make_session_result("d1")
        (tmp_path / "news-2026-02-10-abc123.json").write_text(
            result.model_dump_json(), encoding="utf-8"
        )
        loaded = load_results_from_dir(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].decision.id == "d1"

    def test_skips_non_session_result_list(self, tmp_path: Path) -> None:
        """A file containing a JSON list (e.g. suggestions.json) is skipped."""
        (tmp_path / "suggestions.json").write_text(
            json.dumps([{"timestamp": "2026-02-15", "creator": "vindl"}]),
            encoding="utf-8",
        )
        loaded = load_results_from_dir(tmp_path)
        assert loaded == []

    def test_skips_non_session_result_dict(self, tmp_path: Path) -> None:
        """A file containing a dict that isn't a SessionResult is skipped."""
        (tmp_path / "overrides.json").write_text(
            json.dumps({"some_key": "some_value"}),
            encoding="utf-8",
        )
        loaded = load_results_from_dir(tmp_path)
        assert loaded == []

    def test_loads_valid_and_skips_invalid(self, tmp_path: Path) -> None:
        """Valid SessionResult files load while invalid ones are skipped."""
        result = _make_session_result("d1")
        (tmp_path / "news-2026-02-10-abc123.json").write_text(
            result.model_dump_json(), encoding="utf-8"
        )
        (tmp_path / "suggestions.json").write_text(
            json.dumps([{"foo": "bar"}]), encoding="utf-8"
        )
        (tmp_path / "overrides.json").write_text(
            json.dumps([{"override": True}]), encoding="utf-8"
        )
        loaded = load_results_from_dir(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].decision.id == "d1"

    def test_empty_directory(self, tmp_path: Path) -> None:
        loaded = load_results_from_dir(tmp_path)
        assert loaded == []

    def test_multiple_valid_files_sorted(self, tmp_path: Path) -> None:
        r1 = _make_session_result("d1")
        r2 = _make_session_result("d2")
        (tmp_path / "a-first.json").write_text(
            r1.model_dump_json(), encoding="utf-8"
        )
        (tmp_path / "b-second.json").write_text(
            r2.model_dump_json(), encoding="utf-8"
        )
        loaded = load_results_from_dir(tmp_path)
        assert len(loaded) == 2
        assert loaded[0].decision.id == "d1"
        assert loaded[1].decision.id == "d2"
