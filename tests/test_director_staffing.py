"""Tests for director staffing authority in prompt files."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECT_DIRECTOR_PROMPT = REPO_ROOT / "dev-fleet" / "director" / "CLAUDE.md"
STRATEGIC_DIRECTOR_PROMPT = (
    REPO_ROOT / "dev-fleet" / "strategic-director" / "CLAUDE.md"
)


def _read_prompt(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# Project Director staffing authority
# ---------------------------------------------------------------------------


class TestProjectDirectorStaffing:
    """Project Director has technical/operational staffing authority."""

    def test_has_staffing_section(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "## Agent Staffing (Technical/Operational Roles)" in prompt

    def test_covers_ci_deploy(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "CI/deploy monitoring agents" in prompt

    def test_covers_code_quality(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "Code quality / test coverage agents" in prompt

    def test_covers_security(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "Security review agents" in prompt

    def test_covers_performance(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "Performance monitoring agents" in prompt

    def test_boundary_no_content_roles(self) -> None:
        """Project Director must not propose content/external roles."""
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "Do NOT propose content/external-facing agent roles" in prompt

    def test_relationship_table_shows_staffing(self) -> None:
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "technical/operational roles" in prompt
        assert "Relationship to Strategic Director" in prompt

    def test_resource_discipline_three_options(self) -> None:
        """Project Director should consider non-agent solutions first."""
        prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        assert "Can it be solved without any agent?" in prompt
        assert "ongoing cost" in prompt


# ---------------------------------------------------------------------------
# Strategic Director staffing authority
# ---------------------------------------------------------------------------


class TestStrategicDirectorStaffing:
    """Strategic Director has content/external staffing authority."""

    def test_has_staffing_section(self) -> None:
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "## Agent Staffing (Content/External Roles)" in prompt

    def test_covers_ministry_agents(self) -> None:
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "New ministry agents" in prompt

    def test_covers_engagement(self) -> None:
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "Engagement / social media agents" in prompt

    def test_covers_public_facing(self) -> None:
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "Public-facing capability agents" in prompt

    def test_boundary_no_technical_roles(self) -> None:
        """Strategic Director must not propose technical/operational roles."""
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "Do NOT propose technical/operational agent roles" in prompt

    def test_relationship_table_shows_staffing(self) -> None:
        prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)
        assert "content/external roles" in prompt
        assert "Relationship to Project Director" in prompt


# ---------------------------------------------------------------------------
# Cross-prompt consistency
# ---------------------------------------------------------------------------


class TestStaffingConsistency:
    """Both prompts agree on the staffing split."""

    def test_relationship_tables_match(self) -> None:
        """Both prompts contain the same relationship table rows."""
        pd_prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        sd_prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)

        # Both should have the same agent staffing row
        staffing_row = (
            "Yes — technical/operational roles (CI, security, code quality, performance)"
        )
        assert staffing_row in pd_prompt
        assert staffing_row in sd_prompt

        content_row = (
            "Yes — content/external roles (ministries, engagement, public-facing)"
        )
        assert content_row in pd_prompt
        assert content_row in sd_prompt

    def test_bootstrap_language_in_both(self) -> None:
        """Both prompts reference the complementary bootstrap pattern."""
        pd_prompt = _read_prompt(PROJECT_DIRECTOR_PROMPT)
        sd_prompt = _read_prompt(STRATEGIC_DIRECTOR_PROMPT)

        assert "engineering gaps" in pd_prompt
        assert "market-facing gaps" in pd_prompt
        assert "engineering gaps" in sd_prompt
        assert "market-facing gaps" in sd_prompt
