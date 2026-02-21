"""Tests for extended thinking support across agents and SDK helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ThinkingConfig

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import main_loop  # noqa: E402
import pr_workflow  # noqa: E402
from government.agents.base import GovernmentAgent, MinistryConfig  # noqa: E402
from government.agents.critic import CriticAgent  # noqa: E402
from government.agents.parliament import ParliamentAgent  # noqa: E402
from government.agents.synthesizer import SynthesizerAgent  # noqa: E402
from government.orchestrator import Orchestrator  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DUMMY_MINISTRY = MinistryConfig(
    name="Test",
    slug="test",
    focus_areas=["testing"],
    system_prompt="You are a test agent.",
)

_ADAPTIVE: ThinkingConfig = {"type": "adaptive"}
_ENABLED: ThinkingConfig = {"type": "enabled", "budget_tokens": 5000}
_DISABLED: ThinkingConfig = {"type": "disabled"}


# ---------------------------------------------------------------------------
# GovernmentAgent
# ---------------------------------------------------------------------------


def test_government_agent_thinking_none_by_default() -> None:
    agent = GovernmentAgent(_DUMMY_MINISTRY)
    assert agent.thinking is None


def test_government_agent_thinking_adaptive() -> None:
    agent = GovernmentAgent(_DUMMY_MINISTRY, thinking=_ADAPTIVE)
    assert agent.thinking == {"type": "adaptive"}


def test_government_agent_thinking_enabled() -> None:
    agent = GovernmentAgent(_DUMMY_MINISTRY, thinking=_ENABLED)
    assert agent.thinking == {"type": "enabled", "budget_tokens": 5000}


def test_government_agent_thinking_disabled() -> None:
    agent = GovernmentAgent(_DUMMY_MINISTRY, thinking=_DISABLED)
    assert agent.thinking == {"type": "disabled"}


# ---------------------------------------------------------------------------
# ParliamentAgent
# ---------------------------------------------------------------------------


def test_parliament_agent_thinking_none_by_default() -> None:
    agent = ParliamentAgent()
    assert agent.thinking is None


def test_parliament_agent_thinking_set() -> None:
    agent = ParliamentAgent(thinking=_ENABLED)
    assert agent.thinking == _ENABLED


# ---------------------------------------------------------------------------
# CriticAgent
# ---------------------------------------------------------------------------


def test_critic_agent_thinking_none_by_default() -> None:
    agent = CriticAgent()
    assert agent.thinking is None


def test_critic_agent_thinking_set() -> None:
    agent = CriticAgent(thinking=_ADAPTIVE)
    assert agent.thinking == _ADAPTIVE


# ---------------------------------------------------------------------------
# SynthesizerAgent
# ---------------------------------------------------------------------------


def test_synthesizer_agent_thinking_none_by_default() -> None:
    agent = SynthesizerAgent()
    assert agent.thinking is None


def test_synthesizer_agent_thinking_set() -> None:
    agent = SynthesizerAgent(thinking=_ENABLED)
    assert agent.thinking == _ENABLED


# ---------------------------------------------------------------------------
# Orchestrator defaults
# ---------------------------------------------------------------------------


def test_orchestrator_default_thinking_configs() -> None:
    """Orchestrator uses enabled thinking for all agents."""
    orch = Orchestrator()
    for agent in orch.ministry_agents:
        assert agent.thinking == {"type": "enabled", "budget_tokens": 10000}
    assert orch.parliament.thinking == {"type": "enabled", "budget_tokens": 20000}
    assert orch.critic.thinking == {"type": "enabled", "budget_tokens": 20000}
    assert orch.synthesizer.thinking == {"type": "enabled", "budget_tokens": 20000}


def test_orchestrator_custom_thinking_configs() -> None:
    """Orchestrator accepts custom thinking configs."""
    disabled: ThinkingConfig = {"type": "disabled"}
    adaptive: ThinkingConfig = {"type": "adaptive"}
    orch = Orchestrator(ministry_thinking=disabled, advanced_thinking=adaptive)
    for agent in orch.ministry_agents:
        assert agent.thinking == disabled
    assert orch.parliament.thinking == adaptive
    assert orch.critic.thinking == adaptive
    assert orch.synthesizer.thinking == adaptive


# ---------------------------------------------------------------------------
# _sdk_options (main_loop + pr_workflow)
# ---------------------------------------------------------------------------


def test_main_loop_sdk_options_thinking_none_by_default() -> None:
    opts = main_loop._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert opts.thinking is None


def test_main_loop_sdk_options_thinking_adaptive() -> None:
    opts = main_loop._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Read"],
        thinking={"type": "adaptive"},
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.thinking == {"type": "adaptive"}


def test_main_loop_sdk_options_thinking_enabled() -> None:
    opts = main_loop._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
        thinking={"type": "enabled", "budget_tokens": 8000},
    )
    assert opts.thinking == {"type": "enabled", "budget_tokens": 8000}


def test_main_loop_sdk_options_thinking_disabled() -> None:
    opts = main_loop._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Bash"],
        thinking={"type": "disabled"},
    )
    assert opts.thinking == {"type": "disabled"}


def test_pr_workflow_sdk_options_thinking_none_by_default() -> None:
    opts = pr_workflow._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=[],
    )
    assert opts.thinking is None


def test_pr_workflow_sdk_options_thinking_adaptive() -> None:
    opts = pr_workflow._sdk_options(
        system_prompt="test",
        model="claude-sonnet-4-6",
        max_turns=1,
        allowed_tools=["Read"],
        thinking={"type": "adaptive"},
    )
    assert isinstance(opts, ClaudeAgentOptions)
    assert opts.thinking == {"type": "adaptive"}


# ---------------------------------------------------------------------------
# Ministry factory functions pass thinking through
# ---------------------------------------------------------------------------


def test_ministry_factory_passes_thinking() -> None:
    """All ministry factory functions accept and pass through thinking."""
    from government.agents.ministry_finance import create_finance_agent

    agent = create_finance_agent(thinking=_ADAPTIVE)
    assert agent.thinking == _ADAPTIVE


def test_ministry_factory_thinking_none_by_default() -> None:
    """Ministry factory defaults to thinking=None when not specified."""
    from government.agents.ministry_finance import create_finance_agent

    agent = create_finance_agent()
    assert agent.thinking is None
