"""Tests for PM prompt constraints."""

from __future__ import annotations

from pathlib import Path


def _read_pm_prompt() -> str:
    """Read the PM CLAUDE.md prompt file."""
    pm_prompt_path = Path(__file__).parent.parent / "theseus" / "pm" / "CLAUDE.md"
    return pm_prompt_path.read_text()


def test_pm_prompt_forbids_proposing_new_agents() -> None:
    """PM prompt must explicitly forbid proposing new agents.

    Regression test for issue #139: the PM proposed a new Infrastructure
    ministry agent, but agent staffing is the Strategic Director's job.
    """
    content = _read_pm_prompt()
    assert "Do NOT propose new agents" in content


def test_pm_prompt_has_do_not_section() -> None:
    """PM prompt must have a 'What You Do NOT Do' section."""
    content = _read_pm_prompt()
    assert "## What You Do NOT Do" in content


def test_pm_prompt_forbids_coding_and_reviewing() -> None:
    """PM prompt must forbid coding and code review."""
    content = _read_pm_prompt()
    assert "Do NOT write code" in content
    assert "Do NOT review code" in content
