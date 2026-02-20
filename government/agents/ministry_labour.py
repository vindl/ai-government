"""Ministry of Labour and Social Welfare agent."""

from claude_agent_sdk import ThinkingConfig

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_labour import (
    LABOUR_FOCUS_AREAS,
    LABOUR_SYSTEM_PROMPT,
)


def create_labour_agent(
    session_config: SessionConfig | None = None,
    *,
    thinking: ThinkingConfig | None = None,
) -> GovernmentAgent:
    """Create the Ministry of Labour and Social Welfare agent."""
    config = MinistryConfig(
        name="Labour and Social Welfare",
        slug="labour",
        focus_areas=LABOUR_FOCUS_AREAS,
        system_prompt=LABOUR_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config, thinking=thinking)
