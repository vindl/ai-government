"""Ministry of Tourism agent."""

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_tourism import (
    TOURISM_FOCUS_AREAS,
    TOURISM_SYSTEM_PROMPT,
)


def create_tourism_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Tourism agent."""
    config = MinistryConfig(
        name="Tourism",
        slug="tourism",
        focus_areas=TOURISM_FOCUS_AREAS,
        system_prompt=TOURISM_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
