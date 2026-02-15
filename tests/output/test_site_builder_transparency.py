"""Tests for transparency page in site builder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_government.models.override import HumanOverride, HumanSuggestion
from ai_government.output.site_builder import (
    SiteBuilder,
    load_overrides_from_file,
    load_suggestions_from_file,
)


@pytest.fixture
def sample_overrides() -> list[HumanOverride]:
    """Sample override records for testing."""
    return [
        HumanOverride(
            timestamp=datetime(2026, 2, 14, 12, 30, tzinfo=UTC),
            issue_number=123,
            pr_number=None,
            override_type="comment",
            actor="vindl",
            issue_title="Implement transparency report",
            ai_verdict="Rejected by AI triage",
            human_action="Moved to backlog via override",
            rationale="Important for constitutional compliance",
        ),
        HumanOverride(
            timestamp=datetime(2026, 2, 13, 10, 15, tzinfo=UTC),
            issue_number=100,
            override_type="reopened",
            actor="admin",
            issue_title="Fix critical bug",
            ai_verdict="Rejected by AI triage",
            human_action="Reopened and moved to backlog",
        ),
    ]


@pytest.fixture
def sample_suggestions() -> list[HumanSuggestion]:
    """Sample human suggestion records for testing."""
    return [
        HumanSuggestion(
            timestamp=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
            issue_number=200,
            issue_title="Add new analytics feature",
            status="open",
            creator="vindl",
        ),
        HumanSuggestion(
            timestamp=datetime(2026, 2, 14, 9, 0, tzinfo=UTC),
            issue_number=199,
            issue_title="Improve error handling",
            status="closed",
            creator="contributor",
        ),
    ]


def test_save_and_load_overrides(tmp_path: Path, sample_overrides: list[HumanOverride]) -> None:
    """Test saving and loading override records."""
    # Save
    save_path = Path(str(tmp_path))
    _save_test_overrides(sample_overrides, save_path)

    # Load
    loaded = load_overrides_from_file(save_path)

    assert len(loaded) == 2
    assert loaded[0].issue_number == 123
    assert loaded[0].actor == "vindl"
    assert loaded[0].rationale == "Important for constitutional compliance"
    assert loaded[1].issue_number == 100
    assert loaded[1].rationale is None


def test_load_overrides_from_nonexistent_file(tmp_path: Path) -> None:
    """Test loading from nonexistent file returns empty list."""
    loaded = load_overrides_from_file(tmp_path / "nonexistent")
    assert loaded == []


def test_build_transparency_page(tmp_path: Path, sample_overrides: list[HumanOverride]) -> None:
    """Test building transparency page."""
    output_dir = tmp_path / "site"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Save overrides
    _save_test_overrides(sample_overrides, data_dir)

    # Build site with transparency page
    builder = SiteBuilder(output_dir)
    builder._build_transparency(sample_overrides, [])

    # Check output exists
    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    # Check content
    content = transparency_page.read_text()
    assert "Human Influence Transparency Report" in content
    assert "#123: Implement transparency report" in content
    assert "#100: Fix critical bug" in content
    assert "vindl" in content
    assert "admin" in content
    assert "Important for constitutional compliance" in content


def test_build_transparency_page_empty(tmp_path: Path) -> None:
    """Test building transparency page with no overrides or suggestions."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency([], [])

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()
    assert "No human interventions have been recorded yet" in content


def test_save_and_load_suggestions(
    tmp_path: Path, sample_suggestions: list[HumanSuggestion]
) -> None:
    """Test saving and loading suggestion records."""
    # Save
    save_path = Path(str(tmp_path))
    _save_test_suggestions(sample_suggestions, save_path)

    # Load
    loaded = load_suggestions_from_file(save_path)

    assert len(loaded) == 2
    assert loaded[0].issue_number == 200
    assert loaded[0].creator == "vindl"
    assert loaded[0].status == "open"
    assert loaded[1].issue_number == 199
    assert loaded[1].status == "closed"


def test_load_suggestions_from_nonexistent_file(tmp_path: Path) -> None:
    """Test loading suggestions from nonexistent file returns empty list."""
    loaded = load_suggestions_from_file(tmp_path / "nonexistent")
    assert loaded == []


def test_build_transparency_page_with_suggestions(
    tmp_path: Path,
    sample_overrides: list[HumanOverride],
    sample_suggestions: list[HumanSuggestion],
) -> None:
    """Test building transparency page with both overrides and suggestions."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency(sample_overrides, sample_suggestions)

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()

    # Check for override section
    assert "AI Decision Overrides" in content
    assert "#123: Implement transparency report" in content

    # Check for suggestion section
    assert "Human-Directed Tasks" in content
    assert "#200: Add new analytics feature" in content
    assert "#199: Improve error handling" in content
    assert "status-open" in content
    assert "status-closed" in content


def test_build_transparency_page_suggestions_only(
    tmp_path: Path, sample_suggestions: list[HumanSuggestion]
) -> None:
    """Test building transparency page with only suggestions, no overrides."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency([], sample_suggestions)

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()

    # Should show suggestions section
    assert "Human-Directed Tasks" in content
    assert "#200: Add new analytics feature" in content

    # Should not show override section (empty)
    assert "AI Decision Overrides" not in content


def _save_test_overrides(overrides: list[HumanOverride], output_dir: Path) -> None:
    """Helper to save override records for tests."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "overrides.json"
    data = [o.model_dump(mode="json") for o in overrides]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _save_test_suggestions(suggestions: list[HumanSuggestion], output_dir: Path) -> None:
    """Helper to save suggestion records for tests."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "suggestions.json"
    data = [s.model_dump(mode="json") for s in suggestions]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
