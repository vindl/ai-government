"""Ministry of Economy agent."""

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_economy import (
    ECONOMY_FOCUS_AREAS,
    ECONOMY_SYSTEM_PROMPT,
)


def create_economy_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Economy agent."""
    config = MinistryConfig(
        name="Economy",
        slug="economy",
        focus_areas=ECONOMY_FOCUS_AREAS,
        system_prompt=ECONOMY_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
