"""Ministry of Interior agent."""

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_interior import (
    INTERIOR_FOCUS_AREAS,
    INTERIOR_SYSTEM_PROMPT,
)


def create_interior_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Interior agent."""
    config = MinistryConfig(
        name="Interior",
        slug="interior",
        focus_areas=INTERIOR_FOCUS_AREAS,
        system_prompt=INTERIOR_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
