"""Ministry of Justice agent."""

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_justice import (
    JUSTICE_FOCUS_AREAS,
    JUSTICE_SYSTEM_PROMPT,
)


def create_justice_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Justice agent."""
    config = MinistryConfig(
        name="Justice",
        slug="justice",
        focus_areas=JUSTICE_FOCUS_AREAS,
        system_prompt=JUSTICE_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
