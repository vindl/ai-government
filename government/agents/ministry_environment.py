"""Ministry of Environment agent."""

from claude_agent_sdk import ThinkingConfig

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_environment import (
    ENVIRONMENT_FOCUS_AREAS,
    ENVIRONMENT_SYSTEM_PROMPT,
)


def create_environment_agent(
    session_config: SessionConfig | None = None,
    *,
    thinking: ThinkingConfig | None = None,
) -> GovernmentAgent:
    """Create the Ministry of Environment agent."""
    config = MinistryConfig(
        name="Environment",
        slug="environment",
        focus_areas=ENVIRONMENT_FOCUS_AREAS,
        system_prompt=ENVIRONMENT_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config, thinking=thinking)
