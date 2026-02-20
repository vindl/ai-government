"""Ministry of Health agent."""

from claude_agent_sdk import ThinkingConfig

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_health import (
    HEALTH_FOCUS_AREAS,
    HEALTH_SYSTEM_PROMPT,
)


def create_health_agent(
    session_config: SessionConfig | None = None,
    *,
    thinking: ThinkingConfig | None = None,
) -> GovernmentAgent:
    """Create the Ministry of Health agent."""
    config = MinistryConfig(
        name="Health",
        slug="health",
        focus_areas=HEALTH_FOCUS_AREAS,
        system_prompt=HEALTH_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config, thinking=thinking)
