"""Ministry of Tourism, Ecology, Sustainable Development and Northern Region Development."""

from claude_agent_sdk import ThinkingConfig

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_tourism import (
    TOURISM_FOCUS_AREAS,
    TOURISM_SYSTEM_PROMPT,
)


def create_tourism_agent(
    session_config: SessionConfig | None = None,
    *,
    thinking: ThinkingConfig | None = None,
) -> GovernmentAgent:
    """Create the Tourism, Ecology, Sustainable Development ministry agent."""
    config = MinistryConfig(
        name="Tourism, Ecology, Sustainable Development and Northern Region Development",
        slug="tourism",
        focus_areas=TOURISM_FOCUS_AREAS,
        system_prompt=TOURISM_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config, thinking=thinking)
