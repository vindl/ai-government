"""Ministry of Finance agent."""

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_finance import (
    FINANCE_FOCUS_AREAS,
    FINANCE_SYSTEM_PROMPT,
)


def create_finance_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of Finance agent."""
    config = MinistryConfig(
        name="Finance",
        slug="finance",
        focus_areas=FINANCE_FOCUS_AREAS,
        system_prompt=FINANCE_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
