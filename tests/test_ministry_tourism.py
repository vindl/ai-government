"""Tests for the Tourism ministry agent, prompt, and MinistryType enum."""

from government.agents.ministry_tourism import create_tourism_agent
from government.models.enums import MinistryType
from government.prompts.ministry_tourism import (
    TOURISM_EXPERTISE,
    TOURISM_FOCUS_AREAS,
    TOURISM_SYSTEM_PROMPT,
)


class TestTourismPrompt:
    """Tests for the tourism prompt content."""

    def test_prompt_references_eu_chapter_27(self) -> None:
        assert "Chapter 27" in TOURISM_EXPERTISE

    def test_prompt_mentions_environment_and_climate_change(self) -> None:
        assert "Environment and Climate Change" in TOURISM_EXPERTISE

    def test_prompt_mentions_natura_2000(self) -> None:
        assert "Natura 2000" in TOURISM_EXPERTISE

    def test_prompt_mentions_eia(self) -> None:
        assert "EIA" in TOURISM_EXPERTISE

    def test_prompt_mentions_waste_management(self) -> None:
        assert "Waste management" in TOURISM_EXPERTISE

    def test_prompt_mentions_kotor_unesco(self) -> None:
        assert "Kotor" in TOURISM_EXPERTISE
        assert "UNESCO" in TOURISM_EXPERTISE

    def test_prompt_mentions_national_parks(self) -> None:
        assert "Durmitor" in TOURISM_EXPERTISE
        assert "Skadar Lake" in TOURISM_EXPERTISE

    def test_prompt_mentions_northern_region(self) -> None:
        assert "Northern region" in TOURISM_EXPERTISE or "northern" in TOURISM_EXPERTISE.lower()

    def test_prompt_mentions_sustainable_development(self) -> None:
        assert "Sustainable development" in TOURISM_EXPERTISE

    def test_prompt_mentions_spatial_planning(self) -> None:
        assert "Spatial planning" in TOURISM_EXPERTISE

    def test_system_prompt_built_for_correct_ministry(self) -> None:
        assert "Ministry of Tourism, Ecology, Sustainable Development" in TOURISM_SYSTEM_PROMPT

    def test_focus_areas_include_environment(self) -> None:
        joined = " ".join(TOURISM_FOCUS_AREAS)
        assert "environmental protection" in joined

    def test_focus_areas_include_chapter_27(self) -> None:
        joined = " ".join(TOURISM_FOCUS_AREAS)
        assert "Chapter 27" in joined

    def test_focus_areas_include_sustainable_development(self) -> None:
        joined = " ".join(TOURISM_FOCUS_AREAS)
        assert "sustainable development" in joined

    def test_focus_areas_include_northern_region(self) -> None:
        joined = " ".join(TOURISM_FOCUS_AREAS)
        assert "northern region" in joined


class TestTourismAgent:
    """Tests for the tourism agent creation."""

    def test_create_agent_returns_government_agent(self) -> None:
        from government.agents.base import GovernmentAgent

        agent = create_tourism_agent()
        assert isinstance(agent, GovernmentAgent)

    def test_agent_slug_is_tourism(self) -> None:
        agent = create_tourism_agent()
        assert agent.ministry.slug == "tourism"

    def test_agent_name_includes_ecology(self) -> None:
        agent = create_tourism_agent()
        assert "Ecology" in agent.ministry.name

    def test_agent_name_includes_sustainable_development(self) -> None:
        agent = create_tourism_agent()
        assert "Sustainable Development" in agent.ministry.name

    def test_agent_focus_areas_match_prompt(self) -> None:
        agent = create_tourism_agent()
        assert agent.ministry.focus_areas == TOURISM_FOCUS_AREAS


class TestMinistryTypeEnum:
    """Tests for the MinistryType enum."""

    def test_tourism_ecology_member_exists(self) -> None:
        assert MinistryType.TOURISM_ECOLOGY == "tourism"

    def test_all_ministries_present(self) -> None:
        expected = {
            "finance", "justice", "eu", "health", "interior",
            "education", "economy", "tourism", "environment", "labour",
        }
        actual = {m.value for m in MinistryType}
        assert actual == expected

    def test_enum_is_str(self) -> None:
        assert isinstance(MinistryType.TOURISM_ECOLOGY, str)

    def test_enum_importable_from_models(self) -> None:
        from government.models import MinistryType as ModelsMinistryType

        assert ModelsMinistryType is MinistryType
