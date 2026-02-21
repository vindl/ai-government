"""Parliament debate simulation agent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ThinkingConfig

from government.agents.base import (
    collect_structured_or_text,
    output_format_for,
    parse_structured_or_text,
)
from government.agents.json_parsing import retry_prompt
from government.config import SessionConfig
from government.models.assessment import Assessment, ParliamentDebate
from government.prompts.parliament import PARLIAMENT_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)


class ParliamentAgent:
    """Synthesizes all ministry assessments into a parliamentary debate."""

    default_effort: Literal["low", "medium", "high", "max"] = "high"

    def __init__(
        self,
        session_config: SessionConfig | None = None,
        *,
        thinking: ThinkingConfig | None = None,
    ) -> None:
        self.config = session_config or SessionConfig()
        self.thinking = thinking

    async def debate(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
        *,
        effort: Literal["low", "medium", "high", "max"] | None = None,
    ) -> ParliamentDebate:
        """Run a parliamentary debate on the decision given all ministry assessments."""
        prompt = self._build_prompt(decision, assessments)

        structured = await self._call_model(prompt, effort=effort)

        if structured is not None:
            return self._build_debate(structured, decision.id)

        log.error(
            "ParliamentAgent: no structured output for %s, returning fallback",
            decision.id,
        )
        return self._fallback(decision.id)

    async def _call_model(
        self,
        prompt: str,
        *,
        effort: Literal["low", "medium", "high", "max"] | None = None,
    ) -> dict[str, Any] | None:
        """Call Claude Code SDK and return structured output dict.

        Retries once with a follow-up prompt if the first response
        does not contain valid JSON.
        """
        opts = ClaudeAgentOptions(
            system_prompt={"type": "preset", "preset": "claude_code", "append": PARLIAMENT_SYSTEM_PROMPT},
            model=self.config.model,
            max_turns=100,
            allowed_tools=["WebSearch", "WebFetch"],
            permission_mode="bypassPermissions",
            effort=effort or self.default_effort,
            thinking=self.thinking,
            output_format=output_format_for(ParliamentDebate),
        )
        state: dict[str, Any] = {}
        async for message in claude_agent_sdk.query(prompt=prompt, options=opts):
            collect_structured_or_text(message, state)
        result = parse_structured_or_text(state)
        if result is not None:
            return result

        # Retry with original context + explicit JSON-only instruction
        log.warning("ParliamentAgent: first response had no valid JSON, retrying")
        state = {}
        async for message in claude_agent_sdk.query(
            prompt=retry_prompt(prompt), options=opts,
        ):
            collect_structured_or_text(message, state)
        return parse_structured_or_text(state)

    def _build_prompt(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> str:
        assessments_text = "\n\n".join(
            f"## Ministry of {a.ministry}\n"
            f"Verdict: {a.verdict.value} (Score: {a.score}/10)\n"
            f"Summary: {a.summary}\n"
            f"Key concerns: {', '.join(a.key_concerns)}\n"
            f"Recommendations: {', '.join(a.recommendations)}"
            for a in assessments
        )

        return (
            f"# Decision Under Debate\n"
            f"Title: {decision.title}\n"
            f"Date: {decision.date}\n"
            f"Summary: {decision.summary}\n\n"
            f"# Ministry Assessments\n{assessments_text}\n\n"
            f"Synthesize these assessments into a parliamentary debate."
        )

    @staticmethod
    def _build_debate(data: dict[str, Any], decision_id: str) -> ParliamentDebate:
        """Construct a ``ParliamentDebate`` from parsed data."""
        data.setdefault("decision_id", decision_id)
        return ParliamentDebate(**data)

    @staticmethod
    def _fallback(decision_id: str) -> ParliamentDebate:
        return ParliamentDebate(
            decision_id=decision_id,
            consensus_summary="Debate could not be fully parsed.",
            disagreements=[],
            overall_verdict="neutral",
            debate_transcript="No debate generated.",
        )

    # Keep legacy name for backwards compatibility with tests.
    def _parse_response(self, response_text: str, decision_id: str) -> ParliamentDebate:
        from government.agents.json_parsing import extract_json

        data = extract_json(response_text)
        if data is not None:
            return self._build_debate(data, decision_id)
        return self._fallback(decision_id)
