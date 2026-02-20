"""Tests for transparency data loading and JSON export."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from government.models.override import HumanOverride, HumanSuggestion, PRMerge
from government.output.json_export import _build_transparency
from government.output.site_builder import (
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
    _save_test_overrides(sample_overrides, tmp_path)

    loaded = load_overrides_from_file(tmp_path)

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


def test_save_and_load_suggestions(
    tmp_path: Path, sample_suggestions: list[HumanSuggestion]
) -> None:
    """Test saving and loading suggestion records."""
    _save_test_suggestions(sample_suggestions, tmp_path)

    loaded = load_suggestions_from_file(tmp_path)

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


def test_save_and_load_pr_merges(tmp_path: Path, sample_pr_merges: list[PRMerge]) -> None:
    """Test saving and loading PR merge records."""
    _save_test_pr_merges(sample_pr_merges, tmp_path)

    loaded = load_pr_merges_from_file(tmp_path)

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


def test_build_transparency_json(
    sample_overrides: list[HumanOverride],
    sample_suggestions: list[HumanSuggestion],
    sample_pr_merges: list[PRMerge],
) -> None:
    """Test building transparency JSON payload with all types."""
    data = _build_transparency(sample_overrides, sample_suggestions, sample_pr_merges)

    assert data["total"] == 6
    assert len(data["interventions"]) == 6

    # Should be sorted by timestamp descending
    timestamps = [i["timestamp"] for i in data["interventions"]]
    assert timestamps == sorted(timestamps, reverse=True)

    # Check types are present
    types = {i["type"] for i in data["interventions"]}
    assert types == {"override", "suggestion", "pr_merge"}


def test_build_transparency_json_empty() -> None:
    """Test building transparency JSON with no data."""
    data = _build_transparency([], [], [])
    assert data["total"] == 0
    assert data["interventions"] == []


def test_build_transparency_json_overrides_only(
    sample_overrides: list[HumanOverride],
) -> None:
    """Test building transparency JSON with only overrides."""
    data = _build_transparency(sample_overrides, [], [])
    assert data["total"] == 2
    assert all(i["type"] == "override" for i in data["interventions"])
    assert data["interventions"][0]["issue_title"] == "Implement transparency report"
    assert data["interventions"][0]["actor"] == "vindl"


def test_build_transparency_json_pr_merges_only(
    sample_pr_merges: list[PRMerge],
) -> None:
    """Test building transparency JSON with only PR merges."""
    data = _build_transparency([], [], sample_pr_merges)
    assert data["total"] == 2
    assert all(i["type"] == "pr_merge" for i in data["interventions"])
    assert data["interventions"][0]["pr_title"] == "Add transparency report"


def _save_test_pr_merges(merges: list[PRMerge], output_dir: Path) -> None:
    """Helper to save PR merge records for tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pr_merges.json"
    data = [m.model_dump(mode="json") for m in merges]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _save_test_overrides(overrides: list[HumanOverride], output_dir: Path) -> None:
    """Helper to save override records for tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "overrides.json"
    data = [o.model_dump(mode="json") for o in overrides]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _save_test_suggestions(suggestions: list[HumanSuggestion], output_dir: Path) -> None:
    """Helper to save suggestion records for tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "suggestions.json"
    data = [s.model_dump(mode="json") for s in suggestions]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
