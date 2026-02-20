"""Tests for bilingual data in JSON export.

The old Jinja2 chrome tests are replaced with JSON export tests since
the site is now a React SPA that consumes JSON data files.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from government.models.assessment import Assessment, CriticReport, Verdict
from government.models.decision import GovernmentDecision
from government.orchestrator import SessionResult
from government.output.json_export import export_json


def _make_result() -> SessionResult:
    """Minimal SessionResult for testing JSON export."""
    decision = GovernmentDecision(
        id="chrome-001",
        title="Test Decision",
        summary="A test decision.",
        date=date(2026, 2, 15),
        category="test",
        title_mne="Testna odluka",
        summary_mne="Testna odluka opis.",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="chrome-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Good decision.",
        reasoning="Sound reasoning.",
    )
    critic = CriticReport(
        decision_id="chrome-001",
        decision_score=7,
        assessment_quality_score=6,
        overall_analysis="Good.",
        headline="Test Headline",
        headline_mne="Testni naslov",
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        critic_report=critic,
    )


@pytest.fixture()
def export_dir(tmp_path: Path) -> Path:
    """Export JSON data and return the output directory."""
    output_dir = tmp_path / "data"
    data_dir = tmp_path / "source"
    data_dir.mkdir()

    # Write empty overrides/suggestions so transparency exports
    (data_dir / "overrides.json").write_text("[]")
    (data_dir / "suggestions.json").write_text("[]")

    export_json([_make_result()], data_dir, output_dir)
    return output_dir


class TestJsonExportStructure:
    """Verify JSON export creates all expected files."""

    def test_analyses_index_created(self, export_dir: Path) -> None:
        assert (export_dir / "analyses-index.json").exists()

    def test_individual_analysis_created(self, export_dir: Path) -> None:
        assert (export_dir / "analyses" / "chrome-001.json").exists()

    def test_transparency_created(self, export_dir: Path) -> None:
        assert (export_dir / "transparency.json").exists()

    def test_announcements_created(self, export_dir: Path) -> None:
        assert (export_dir / "announcements.json").exists()


class TestAnalysesIndex:
    """Verify analyses index JSON structure and content."""

    @pytest.fixture()
    def index(self, export_dir: Path) -> list:
        return json.loads((export_dir / "analyses-index.json").read_text())

    def test_has_one_entry(self, index: list) -> None:
        assert len(index) == 1

    def test_contains_en_title(self, index: list) -> None:
        assert index[0]["title"] == "Test Decision"

    def test_contains_mne_title(self, index: list) -> None:
        assert index[0]["title_mne"] == "Testna odluka"

    def test_contains_en_summary(self, index: list) -> None:
        assert index[0]["summary"] == "A test decision."

    def test_contains_mne_summary(self, index: list) -> None:
        assert index[0]["summary_mne"] == "Testna odluka opis."

    def test_contains_score(self, index: list) -> None:
        assert index[0]["decision_score"] == 7

    def test_contains_category(self, index: list) -> None:
        assert index[0]["category"] == "test"

    def test_verdict_label_empty_without_debate(self, index: list) -> None:
        # No debate = no overall_verdict = empty label
        assert index[0]["verdict_label"] == ""

    def test_verdict_label_mne_empty_without_debate(self, index: list) -> None:
        assert index[0]["verdict_label_mne"] == ""

    def test_contains_headline(self, index: list) -> None:
        assert index[0]["headline"] == "Test Headline"

    def test_contains_headline_mne(self, index: list) -> None:
        assert index[0]["headline_mne"] == "Testni naslov"


class TestIndividualAnalysis:
    """Verify individual analysis JSON structure and content."""

    @pytest.fixture()
    def analysis(self, export_dir: Path) -> dict:
        return json.loads((export_dir / "analyses" / "chrome-001.json").read_text())

    def test_has_decision(self, analysis: dict) -> None:
        assert analysis["decision"]["id"] == "chrome-001"

    def test_has_bilingual_decision(self, analysis: dict) -> None:
        assert analysis["decision"]["title"] == "Test Decision"
        assert analysis["decision"]["title_mne"] == "Testna odluka"

    def test_has_assessments(self, analysis: dict) -> None:
        assert len(analysis["assessments"]) == 1
        assert analysis["assessments"][0]["ministry"] == "Finance"

    def test_has_critic_report(self, analysis: dict) -> None:
        assert analysis["critic_report"]["decision_score"] == 7


class TestTransparencyExport:
    """Verify transparency JSON structure."""

    @pytest.fixture()
    def transparency(self, export_dir: Path) -> dict:
        return json.loads((export_dir / "transparency.json").read_text())

    def test_empty_interventions(self, transparency: dict) -> None:
        assert transparency["total"] == 0
        assert transparency["interventions"] == []
