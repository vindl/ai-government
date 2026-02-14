"""Ministry of EU Integration agent."""

from ai_government.agents.base import GovernmentAgent, MinistryConfig
from ai_government.config import SessionConfig
from ai_government.prompts.ministry_eu import EU_FOCUS_AREAS, EU_SYSTEM_PROMPT


def create_eu_agent(session_config: SessionConfig | None = None) -> GovernmentAgent:
    """Create the Ministry of EU Integration agent."""
    config = MinistryConfig(
        name="EU Integration",
        slug="eu",
        focus_areas=EU_FOCUS_AREAS,
        system_prompt=EU_SYSTEM_PROMPT,
    )
    return GovernmentAgent(config, session_config)
