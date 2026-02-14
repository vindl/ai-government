"""Ministry of Education agent."""

from ai_government.agents.base import GovernmentAgent, MinistryConfig
from ai_government.config import SessionConfig
from ai_government.prompts.ministry_education import (
    EDUCATION_FOCUS_AREAS,
    EDUCATION_SYSTEM_PROMPT,
)


def create_education_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Education agent."""
    config = MinistryConfig(
        name="Education",
        slug="education",
        focus_areas=EDUCATION_FOCUS_AREAS,
        system_prompt=EDUCATION_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
