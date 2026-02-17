"""Base government agent class and ministry configuration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from government.config import SessionConfig
from government.models.assessment import Assessment

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)


def _output_format_for(model_cls: type[Any]) -> dict[str, Any]:
    """Build an ``output_format`` dict accepted by the SDK from a Pydantic model."""
    return {"type": "json_schema", "schema": model_cls.model_json_schema()}


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

        structured: dict[str, Any] | None = None
        async for message in claude_agent_sdk.query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=self.ministry.system_prompt,
                model=self.config.model,
                max_turns=1,
                output_format=_output_format_for(Assessment),
                effort=effort,
            ),
        ):
            if isinstance(message, ResultMessage) and message.structured_output is not None:
                structured = message.structured_output

        return self._parse_response(structured, decision.id)

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
