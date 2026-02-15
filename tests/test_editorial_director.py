"""Tests for Editorial Director review functionality."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Import from main_loop since that's where the model lives

main_loop_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(main_loop_path))

from main_loop import EditorialReview  # type: ignore  # noqa: E402


class TestEditorialReview:
    """Test the EditorialReview Pydantic model."""

    def test_valid_review_approved(self) -> None:
        """Test creating a valid approved review."""
        review = EditorialReview(
            approved=True,
            quality_score=8,
            strengths=["Clear reasoning", "Good structure"],
            issues=[],
            recommendations=["Consider adding a summary"],
            engagement_insights=["High engagement on social media"],
        )
        assert review.approved is True
        assert review.quality_score == 8
        assert len(review.strengths) == 2
        assert len(review.issues) == 0

    def test_valid_review_not_approved(self) -> None:
        """Test creating a valid not-approved review."""
        review = EditorialReview(
            approved=False,
            quality_score=4,
            strengths=["Thorough analysis"],
            issues=["Factual error on page 2", "Missing source citation"],
            recommendations=["Fix error", "Add citation"],
            engagement_insights=[],
        )
        assert review.approved is False
        assert review.quality_score == 4
        assert len(review.issues) == 2
        assert len(review.recommendations) == 2

    def test_quality_score_bounds(self) -> None:
        """Test quality_score must be 1-10."""
        # Valid bounds
        EditorialReview(approved=True, quality_score=1)
        EditorialReview(approved=True, quality_score=10)

        # Invalid: too low
        with pytest.raises(ValidationError):
            EditorialReview(approved=True, quality_score=0)

        # Invalid: too high
        with pytest.raises(ValidationError):
            EditorialReview(approved=True, quality_score=11)

    def test_default_empty_lists(self) -> None:
        """Test that list fields default to empty lists."""
        review = EditorialReview(approved=True, quality_score=7)
        assert review.strengths == []
        assert review.issues == []
        assert review.recommendations == []
        assert review.engagement_insights == []

    def test_json_serialization(self) -> None:
        """Test serialization to and from JSON."""
        original = EditorialReview(
            approved=True,
            quality_score=9,
            strengths=["Excellent"],
            issues=[],
            recommendations=["Minor polish"],
            engagement_insights=["Trending topic"],
        )

        # Serialize
        json_str = original.model_dump_json()
        data = json.loads(json_str)

        # Deserialize
        restored = EditorialReview.model_validate(data)

        assert restored.approved == original.approved
        assert restored.quality_score == original.quality_score
        assert restored.strengths == original.strengths
        assert restored.issues == original.issues
        assert restored.recommendations == original.recommendations
        assert restored.engagement_insights == original.engagement_insights

    def test_required_fields(self) -> None:
        """Test that approved and quality_score are required."""
        with pytest.raises(ValidationError):
            EditorialReview(approved=True)  # type: ignore  # missing quality_score

        with pytest.raises(ValidationError):
            EditorialReview(quality_score=5)  # type: ignore  # missing approved
