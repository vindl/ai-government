"""Ministry of EU Integration agent."""

from claude_agent_sdk import ThinkingConfig

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.prompts.ministry_eu import EU_FOCUS_AREAS, EU_SYSTEM_PROMPT


def create_eu_agent(
    session_config: SessionConfig | None = None,
    *,
    thinking: ThinkingConfig | None = None,
) -> GovernmentAgent:
    """Create the Ministry of EU Integration agent."""
    config = MinistryConfig(
        name="EU Integration",
        slug="eu",
        focus_areas=EU_FOCUS_AREAS,
        system_prompt=EU_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config, thinking=thinking)
