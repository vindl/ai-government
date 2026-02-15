"""Tests for transparency page in site builder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_government.models.override import HumanOverride, HumanSuggestion, PRMerge
from ai_government.output.site_builder import (
    SiteBuilder,
    load_overrides_from_file,
    load_pr_merges_from_file,
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


@pytest.fixture
def sample_pr_merges() -> list[PRMerge]:
    """Sample PR merge records for testing."""
    return [
        PRMerge(
            timestamp=datetime(2026, 2, 15, 14, 0, tzinfo=UTC),
            pr_number=50,
            pr_title="Add transparency report",
            actor="vindl",
            issue_number=42,
        ),
        PRMerge(
            timestamp=datetime(2026, 2, 14, 16, 0, tzinfo=UTC),
            pr_number=48,
            pr_title="Fix scoring bug",
            actor="admin",
            issue_number=None,
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
    """Test building transparency page with both overrides and suggestions in unified list."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency(sample_overrides, sample_suggestions)

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()

    # All entries in a single unified list
    assert "#123: Implement transparency report" in content
    assert "#200: Add new analytics feature" in content
    assert "#199: Improve error handling" in content

    # Both types are rendered with override-record class
    assert content.count("override-record") == 4  # 2 overrides + 2 suggestions


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

    # Should show suggestions in the unified list
    assert "#200: Add new analytics feature" in content
    assert "Human-directed task" in content


def test_save_and_load_pr_merges(tmp_path: Path, sample_pr_merges: list[PRMerge]) -> None:
    """Test saving and loading PR merge records."""
    save_path = Path(str(tmp_path))
    _save_test_pr_merges(sample_pr_merges, save_path)

    loaded = load_pr_merges_from_file(save_path)

    assert len(loaded) == 2
    assert loaded[0].pr_number == 50
    assert loaded[0].actor == "vindl"
    assert loaded[0].issue_number == 42
    assert loaded[1].pr_number == 48
    assert loaded[1].issue_number is None


def test_load_pr_merges_from_nonexistent_file(tmp_path: Path) -> None:
    """Test loading PR merges from nonexistent file returns empty list."""
    loaded = load_pr_merges_from_file(tmp_path / "nonexistent")
    assert loaded == []


def test_build_transparency_page_with_pr_merges(
    tmp_path: Path,
    sample_overrides: list[HumanOverride],
    sample_suggestions: list[HumanSuggestion],
    sample_pr_merges: list[PRMerge],
) -> None:
    """Test building transparency page with overrides, suggestions, and PR merges."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency(sample_overrides, sample_suggestions, sample_pr_merges)

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()

    # All entries in a single unified list
    assert "#123: Implement transparency report" in content
    assert "#200: Add new analytics feature" in content
    assert "PR #50: Add transparency report" in content
    assert "PR #48: Fix scoring bug" in content

    # PR merge type labels
    assert "PR spojen" in content
    assert "PR merged" in content

    # Merged by labels
    assert "Spojio:" in content
    assert "Merged by:" in content

    # Linked issue
    assert "issues/42" in content

    # All entries use override-record class (2 overrides + 2 suggestions + 2 PR merges)
    assert content.count("override-record") == 6


def test_build_transparency_page_pr_merges_only(
    tmp_path: Path, sample_pr_merges: list[PRMerge]
) -> None:
    """Test building transparency page with only PR merges."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir)
    builder._build_transparency([], [], sample_pr_merges)

    transparency_page = output_dir / "transparency" / "index.html"
    assert transparency_page.exists()

    content = transparency_page.read_text()

    assert "PR #50: Add transparency report" in content
    assert "PR merged" in content
    assert content.count("override-record") == 2


def _save_test_pr_merges(merges: list[PRMerge], output_dir: Path) -> None:
    """Helper to save PR merge records for tests."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pr_merges.json"
    data = [m.model_dump(mode="json") for m in merges]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
