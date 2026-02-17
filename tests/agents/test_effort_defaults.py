"""Tests for default effort levels on agent classes."""

from __future__ import annotations

from government.agents.base import GovernmentAgent, MinistryConfig
from government.agents.critic import CriticAgent
from government.agents.parliament import ParliamentAgent
from government.agents.synthesizer import SynthesizerAgent


class TestDefaultEffortLevels:
    """Each agent class should declare a sensible default_effort."""

    def test_government_agent_default_effort(self) -> None:
        assert GovernmentAgent.default_effort == "medium"

    def test_critic_agent_default_effort(self) -> None:
        assert CriticAgent.default_effort == "high"

    def test_parliament_agent_default_effort(self) -> None:
        assert ParliamentAgent.default_effort == "high"

    def test_synthesizer_agent_default_effort(self) -> None:
        assert SynthesizerAgent.default_effort == "high"

    def test_government_agent_instance_effort(self) -> None:
        config = MinistryConfig(
            name="Test",
            slug="test",
            focus_areas=["testing"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(config)
        assert agent.default_effort == "medium"

    def test_critic_agent_instance_effort(self) -> None:
        agent = CriticAgent()
        assert agent.default_effort == "high"

    def test_parliament_agent_instance_effort(self) -> None:
        agent = ParliamentAgent()
        assert agent.default_effort == "high"

    def test_synthesizer_agent_instance_effort(self) -> None:
        agent = SynthesizerAgent()
        assert agent.default_effort == "high"
