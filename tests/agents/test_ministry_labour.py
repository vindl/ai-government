"""Tests for the Ministry of Labour and Social Welfare agent."""

from government.agents.ministry_labour import create_labour_agent
from government.prompts.ministry_labour import (
    LABOUR_EXPERTISE,
    LABOUR_FOCUS_AREAS,
    LABOUR_SYSTEM_PROMPT,
)


class TestLabourPrompt:
    def test_focus_areas_non_empty(self) -> None:
        assert len(LABOUR_FOCUS_AREAS) > 0

    def test_prompt_references_chapter_19(self) -> None:
        assert "Chapter 19" in LABOUR_EXPERTISE

    def test_prompt_references_zavod(self) -> None:
        assert "Zavod za zapošljavanje" in LABOUR_EXPERTISE

    def test_prompt_references_fond_pio(self) -> None:
        assert "Fond PIO" in LABOUR_EXPERTISE

    def test_prompt_references_centar_za_socijalni_rad(self) -> None:
        assert "Centri za socijalni rad" in LABOUR_EXPERTISE

    def test_prompt_references_ilo(self) -> None:
        assert "ILO" in LABOUR_EXPERTISE

    def test_system_prompt_built(self) -> None:
        assert "Labour and Social Welfare" in LABOUR_SYSTEM_PROMPT
        assert "workers' rights" in LABOUR_SYSTEM_PROMPT


class TestLabourAgent:
    def test_create_agent(self) -> None:
        agent = create_labour_agent()
        assert agent.ministry.name == "Labour and Social Welfare"
        assert agent.ministry.slug == "labour"

    def test_create_agent_with_config(self) -> None:
        from government.config import SessionConfig

        config = SessionConfig()
        agent = create_labour_agent(session_config=config)
        assert agent.ministry.name == "Labour and Social Welfare"

    def test_focus_areas_match(self) -> None:
        agent = create_labour_agent()
        assert agent.ministry.focus_areas == LABOUR_FOCUS_AREAS
