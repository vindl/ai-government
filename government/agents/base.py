"""Base government agent class and ministry configuration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from government.agents.json_parsing import extract_json
from government.config import SessionConfig
from government.models.assessment import Assessment

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)


def collect_structured_or_text(
    message: claude_agent_sdk.Message,
    state: dict[str, Any],
) -> None:
    """Collect structured output from a message, falling back to result text.

    Mutates *state* in-place — sets ``structured`` to the first non-None
    structured output, and ``result_text`` to the last ResultMessage text.
    """
    if isinstance(message, ResultMessage):
        if message.is_error:
            log.error(
                "SDK ResultMessage is_error=True, subtype=%s, result=%s",
                message.subtype,
                (message.result or "")[:500],
            )
        log.debug(
            "ResultMessage: is_error=%s, has_structured=%s, has_result=%s",
            message.is_error,
            message.structured_output is not None,
            bool(message.result),
        )
        if message.structured_output is not None:
            state["structured"] = message.structured_output
        if message.result:
            state["result_text"] = message.result


def parse_structured_or_text(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured output if available, else try to extract JSON from text."""
    if state.get("structured") is not None:
        return state["structured"]  # type: ignore[no-any-return]
    text = state.get("result_text", "")
    if text:
        parsed = extract_json(text)
        if parsed is not None:
            log.debug("Parsed JSON from result text")
            return parsed
    return None


@dataclass(frozen=True)
class MinistryConfig:
    """Configuration for a specific ministry agent."""

    name: str
    slug: str
    focus_areas: list[str]
    system_prompt: str


class GovernmentAgent:
    """Base class for all government ministry agents.

    Each agent receives a GovernmentDecision and produces an Assessment
    by running a Claude Code SDK subprocess with a ministry-specific prompt.
    """

    def __init__(
        self,
        ministry_config: MinistryConfig,
        session_config: SessionConfig | None = None,
    ) -> None:
        self.ministry = ministry_config
        self.config = session_config or SessionConfig()

    async def analyze(
        self,
        decision: GovernmentDecision,
        *,
        effort: Literal["low", "medium", "high", "max"] | None = None,
    ) -> Assessment:
        """Analyze a government decision and return an assessment."""
        prompt = self._build_prompt(decision)

        state: dict[str, Any] = {}
        async for message in claude_agent_sdk.query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=self.ministry.system_prompt,
                model=self.config.model,
                max_turns=1,
                effort=effort,
            ),
        ):
            collect_structured_or_text(message, state)

        return self._parse_response(parse_structured_or_text(state), decision.id)

    def _build_prompt(self, decision: GovernmentDecision) -> str:
        """Build the analysis prompt for the agent."""
        full_text_line = f"Full text: {decision.full_text}\n" if decision.full_text else ""
        return (
            f"Analyze the following Montenegrin government decision "
            f"from the perspective of the Ministry of {self.ministry.name}.\n\n"
            f"Decision: {decision.title}\n"
            f"Date: {decision.date}\n"
            f"Summary: {decision.summary}\n"
            f"{full_text_line}\n"
            f"Focus on: {', '.join(self.ministry.focus_areas)}"
        )

    def _parse_response(
        self, data: dict[str, Any] | None, decision_id: str
    ) -> Assessment:
        """Build an Assessment from the structured output dict."""
        if data is not None:
            data.setdefault("decision_id", decision_id)
            return Assessment(**data)

        name = self.ministry.name
        log.warning("GovernmentAgent(%s): no structured output received", name)
        return Assessment(
            ministry=name,
            decision_id=decision_id,
            verdict="neutral",
            score=5,
            summary=f"Assessment by {name} could not be fully parsed.",
            reasoning="No response received.",
            key_concerns=["Response parsing failed"],
            recommendations=["Re-run assessment"],
        )
