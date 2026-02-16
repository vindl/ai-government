"""Tests for base agent classes and configurations."""

import json
from datetime import date

from government.agents.base import GovernmentAgent, MinistryConfig
from government.config import SessionConfig
from government.models.assessment import Assessment, Verdict
from government.models.decision import GovernmentDecision


class TestMinistryConfig:
    def test_create_config(self) -> None:
        config = MinistryConfig(
            name="Test Ministry",
            slug="test",
            focus_areas=["testing", "quality"],
            system_prompt="You are a test ministry.",
        )
        assert config.name == "Test Ministry"
        assert config.slug == "test"
        assert len(config.focus_areas) == 2

    def test_config_is_frozen(self) -> None:
        config = MinistryConfig(
            name="Test",
            slug="test",
            focus_areas=[],
            system_prompt="prompt",
        )
        # dataclass(frozen=True) should prevent modification
        try:
            config.name = "Changed"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass


class TestSessionConfig:
    def test_defaults(self) -> None:
        config = SessionConfig()
        assert config.parallel_agents is True
        assert config.max_tokens_per_agent > 0
        assert config.max_tokens_per_session > 0


class TestGovernmentAgent:
    def test_build_prompt(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget", "taxes"],
            system_prompt="You are Finance.",
        )
        agent = GovernmentAgent(ministry_config)
        decision = GovernmentDecision(
            id="test-001",
            title="Test Decision",
            summary="A test.",
            date=date(2025, 12, 15),
        )
        prompt = agent._build_prompt(decision)
        assert "Ministry of Finance" in prompt
        assert "test-001" in prompt
        assert "Test Decision" in prompt
        assert "budget, taxes" in prompt

    def test_parse_valid_response(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        response = json.dumps({
            "ministry": "Finance",
            "decision_id": "test-001",
            "verdict": "positive",
            "score": 7,
            "summary": "Good decision.",
            "reasoning": "Solid fiscal reasoning.",
            "key_concerns": ["Budget impact"],
            "recommendations": ["Monitor spending"],
        })
        assessment = agent._parse_response(response, "test-001")
        assert isinstance(assessment, Assessment)
        assert assessment.verdict == Verdict.POSITIVE
        assert assessment.score == 7
        assert assessment.ministry == "Finance"

    def test_parse_invalid_response(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        assessment = agent._parse_response("This is not JSON at all.", "test-001")
        assert assessment.score == 5
        assert assessment.verdict == Verdict.NEUTRAL
        assert "parsing failed" in assessment.summary.lower() or "Finance" in assessment.summary

    def test_parse_response_with_surrounding_text(self) -> None:
        ministry_config = MinistryConfig(
            name="Justice",
            slug="justice",
            focus_areas=["law"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        response = (
            'Here is my analysis:\n\n'
            + json.dumps({
                "ministry": "Justice",
                "decision_id": "test-002",
                "verdict": "negative",
                "score": 3,
                "summary": "Problematic.",
                "reasoning": "Legal issues.",
                "key_concerns": [],
                "recommendations": [],
            })
            + '\n\nI hope this helps.'
        )
        assessment = agent._parse_response(response, "test-002")
        assert assessment.verdict == Verdict.NEGATIVE
        assert assessment.score == 3

    def test_parse_response_with_counter_proposal(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        response = json.dumps({
            "ministry": "Finance",
            "decision_id": "test-001",
            "verdict": "positive",
            "score": 7,
            "summary": "Good decision.",
            "reasoning": "Solid fiscal reasoning.",
            "key_concerns": ["Budget impact"],
            "recommendations": ["Monitor spending"],
            "counter_proposal": {
                "title": "Alternative approach",
                "summary": "We would do it differently.",
                "key_changes": ["Change 1"],
                "expected_benefits": ["Benefit 1"],
                "estimated_feasibility": "High",
            },
        })
        assessment = agent._parse_response(response, "test-001")
        assert assessment.counter_proposal is not None
        assert assessment.counter_proposal.title == "Alternative approach"
        assert len(assessment.counter_proposal.key_changes) == 1

    def test_parse_response_without_counter_proposal(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        response = json.dumps({
            "ministry": "Finance",
            "decision_id": "test-001",
            "verdict": "positive",
            "score": 7,
            "summary": "Good decision.",
            "reasoning": "Solid reasoning.",
            "key_concerns": [],
            "recommendations": [],
        })
        assessment = agent._parse_response(response, "test-001")
        assert assessment.counter_proposal is None

    def test_build_prompt_includes_counter_proposal_schema(self) -> None:
        ministry_config = MinistryConfig(
            name="Finance",
            slug="finance",
            focus_areas=["budget"],
            system_prompt="prompt",
        )
        agent = GovernmentAgent(ministry_config)
        decision = GovernmentDecision(
            id="test-001",
            title="Test",
            summary="A test.",
            date=date(2025, 12, 15),
        )
        prompt = agent._build_prompt(decision)
        assert "counter_proposal" in prompt
        assert "key_changes" in prompt

    def test_ministry_agent_factories(self) -> None:
        from government.agents.ministry_economy import create_economy_agent
        from government.agents.ministry_education import create_education_agent
        from government.agents.ministry_environment import create_environment_agent
        from government.agents.ministry_eu import create_eu_agent
        from government.agents.ministry_finance import create_finance_agent
        from government.agents.ministry_health import create_health_agent
        from government.agents.ministry_interior import create_interior_agent
        from government.agents.ministry_justice import create_justice_agent
        from government.agents.ministry_tourism import create_tourism_agent

        agents = [
            create_finance_agent(),
            create_justice_agent(),
            create_eu_agent(),
            create_health_agent(),
            create_interior_agent(),
            create_education_agent(),
            create_economy_agent(),
            create_tourism_agent(),
            create_environment_agent(),
        ]
        names = [a.ministry.name for a in agents]
        assert "Finance" in names
        assert "Justice" in names
        assert "EU Integration" in names
        assert "Health" in names
        assert "Interior" in names
        assert "Education" in names
        assert "Economy" in names
        assert "Tourism" in names
        assert "Environment" in names
