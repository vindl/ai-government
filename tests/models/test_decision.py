"""Tests for GovernmentDecision model."""

import json
from datetime import date

import pytest
from government.models.decision import GovernmentDecision
from pydantic import ValidationError


class TestGovernmentDecision:
    def test_create_minimal(self) -> None:
        d = GovernmentDecision(
            id="test-001",
            title="Test Decision",
            summary="A test decision",
            date=date(2025, 12, 15),
        )
        assert d.id == "test-001"
        assert d.category == "general"
        assert d.tags == []
        assert d.full_text == ""
        assert d.source_url == ""

    def test_create_full(self) -> None:
        d = GovernmentDecision(
            id="test-002",
            title="Full Decision",
            summary="Full details",
            full_text="The complete text of the decision.",
            date=date(2025, 12, 20),
            source_url="https://gov.me/test",
            category="fiscal",
            tags=["tax", "budget"],
        )
        assert d.category == "fiscal"
        assert len(d.tags) == 2

    def test_json_roundtrip(self, sample_decision: GovernmentDecision) -> None:
        json_str = sample_decision.model_dump_json()
        restored = GovernmentDecision.model_validate_json(json_str)
        assert restored == sample_decision

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            GovernmentDecision(id="x", title="x")  # type: ignore[call-arg]

    def test_load_seed_data(self, seed_decisions: list[GovernmentDecision]) -> None:
        assert len(seed_decisions) == 3
        assert seed_decisions[0].id == "gov-2025-001"
        assert seed_decisions[0].category == "fiscal"
        assert seed_decisions[1].category == "legal"
        assert seed_decisions[2].category == "health"

    def test_seed_data_dates(self, seed_decisions: list[GovernmentDecision]) -> None:
        for d in seed_decisions:
            assert d.date.year >= 2025

    def test_from_dict(self) -> None:
        data = {
            "id": "dict-001",
            "title": "From Dict",
            "summary": "Created from dictionary",
            "date": "2025-12-15",
        }
        d = GovernmentDecision(**data)
        assert d.id == "dict-001"
        assert d.date == date(2025, 12, 15)

    @pytest.mark.parametrize(
        "category",
        [
            "fiscal",
            "legal",
            "eu",
            "health",
            "security",
            "education",
            "economy",
            "tourism",
            "environment",
            "general",
        ],
    )
    def test_all_categories(self, category: str) -> None:
        d = GovernmentDecision(
            id=f"cat-{category}",
            title=f"Test {category} decision",
            summary=f"A decision in the {category} category",
            date=date(2026, 1, 15),
            category=category,
        )
        assert d.category == category

    def test_seed_file_is_valid_json(self, seed_decisions_path: "Path") -> None:  # noqa: F821
        with open(seed_decisions_path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0
