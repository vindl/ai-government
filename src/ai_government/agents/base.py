"""Base government agent class and ministry configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from ai_government.config import SessionConfig
from ai_government.models.assessment import Assessment

if TYPE_CHECKING:
    from ai_government.models.decision import GovernmentDecision


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

    async def analyze(self, decision: GovernmentDecision) -> Assessment:
        """Analyze a government decision and return an assessment."""
        prompt = self._build_prompt(decision)

        response_text = ""
        async for message in claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=self.ministry.system_prompt,
                model=self.config.model,
                max_turns=1,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text

        return self._parse_response(response_text, decision.id)

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
            f"Focus on: {', '.join(self.ministry.focus_areas)}\n\n"
            f"Respond with a JSON object matching this schema:\n"
            f'{{"ministry": "{self.ministry.name}", '
            f'"decision_id": "{decision.id}", '
            f'"verdict": "strongly_positive|positive|neutral|negative|strongly_negative", '
            f'"score": 1-10, "summary": "...", "reasoning": "...", '
            f'"key_concerns": ["..."], "recommendations": ["..."], '
            f'"counter_proposal": {{"title": "...", "summary": "...", '
            f'"key_changes": ["..."], "expected_benefits": ["..."], '
            f'"estimated_feasibility": "..."}}}}'
        )

    def _parse_response(self, response_text: str, decision_id: str) -> Assessment:
        """Parse the agent's response into an Assessment."""
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
            data = json.loads(json_str)
            return Assessment(**data)
        except (ValueError, json.JSONDecodeError):
            name = self.ministry.name
            reasoning = response_text[:500] if response_text else "No response received."
            return Assessment(
                ministry=name,
                decision_id=decision_id,
                verdict="neutral",
                score=5,
                summary=f"Assessment by {name} could not be fully parsed.",
                reasoning=reasoning,
                key_concerns=["Response parsing failed"],
                recommendations=["Re-run assessment"],
            )
