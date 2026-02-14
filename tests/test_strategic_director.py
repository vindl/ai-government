"""Tests for Strategic Director agent integration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_strategic_director_output_schema() -> None:
    """StrategicDirectorOutput model validates correctly structured output."""
    # Import here to avoid module-level import issues
    import sys
    from pathlib import Path

    # Add scripts to path so we can import from main_loop
    scripts_path = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))

    from main_loop import StrategicDirectorOutput

    # Valid output
    valid = {
        "title": "Expand to Instagram for broader reach",
        "description": (
            "Public interest data shows Instagram has 2x the reach of X in Montenegro. "
            "File: src/ai_government/output/social_media_config.py. "
            "Add Instagram API integration."
        ),
    }
    output = StrategicDirectorOutput.model_validate(valid)
    assert output.title == "Expand to Instagram for broader reach"
    assert "Instagram" in output.description


def test_strategic_director_output_rejects_empty_title() -> None:
    """StrategicDirectorOutput rejects empty title."""
    import sys
    from pathlib import Path

    scripts_path = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))

    from main_loop import StrategicDirectorOutput

    invalid = {
        "title": "",
        "description": "Some description",
    }
    with pytest.raises(ValidationError):
        StrategicDirectorOutput.model_validate(invalid)


def test_strategic_director_output_rejects_empty_description() -> None:
    """StrategicDirectorOutput rejects empty description."""
    import sys
    from pathlib import Path

    scripts_path = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))

    from main_loop import StrategicDirectorOutput

    invalid = {
        "title": "Valid title",
        "description": "",
    }
    with pytest.raises(ValidationError):
        StrategicDirectorOutput.model_validate(invalid)


def test_strategic_director_output_title_length_limit() -> None:
    """StrategicDirectorOutput enforces 120 char title limit."""
    import sys
    from pathlib import Path

    scripts_path = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))

    from main_loop import StrategicDirectorOutput

    too_long = {
        "title": "x" * 121,  # Exceeds 120 char limit
        "description": "Some description",
    }
    with pytest.raises(ValidationError):
        StrategicDirectorOutput.model_validate(too_long)

    # Exactly 120 should be fine
    exactly_120 = {
        "title": "x" * 120,
        "description": "Some description",
    }
    output = StrategicDirectorOutput.model_validate(exactly_120)
    assert len(output.title) == 120
