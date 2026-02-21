"""Synthesizer agent — consolidates ministry counter-proposals into a unified alternative."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ThinkingConfig

from government.agents.base import (
    collect_structured_or_text,
    parse_structured_or_text,
)
from government.agents.json_parsing import retry_prompt
from government.config import SessionConfig
from government.models.assessment import Assessment, CounterProposal
from government.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)


class SynthesizerAgent:
    """Consolidates per-ministry counter-proposals into a unified alternative."""

    default_effort: Literal["low", "medium", "high", "max"] = "high"

    def __init__(
        self,
        session_config: SessionConfig | None = None,
        *,
        thinking: ThinkingConfig | None = None,
    ) -> None:
        self.config = session_config or SessionConfig()
        self.thinking = thinking

    async def synthesize(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
        *,
        effort: Literal["low", "medium", "high", "max"] | None = None,
    ) -> CounterProposal:
        """Synthesize ministry counter-proposals into a unified counter-proposal."""
        prompt = self._build_prompt(decision, assessments)

        structured = await self._call_model(prompt, effort=effort)

        if structured is not None:
            return self._build_proposal(structured, decision.id)

        log.error(
            "SynthesizerAgent: no structured output for %s, returning fallback",
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
            system_prompt={"type": "preset", "preset": "claude_code", "append": SYNTHESIZER_SYSTEM_PROMPT},
            model=self.config.model,
            max_turns=100,
            allowed_tools=["WebSearch", "WebFetch"],
            permission_mode="bypassPermissions",
            effort=effort or self.default_effort,
            thinking=self.thinking,
        )
        state: dict[str, Any] = {}
        async for message in claude_agent_sdk.query(prompt=prompt, options=opts):
            collect_structured_or_text(message, state)
        result = parse_structured_or_text(state)
        if result is not None:
            return result

        # Retry with original context + explicit JSON-only instruction
        log.warning("SynthesizerAgent: first response had no valid JSON, retrying")
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
        full_text_line = f"Full text: {decision.full_text}\n" if decision.full_text else ""

        assessments_text = ""
        for a in assessments:
            assessments_text += (
                f"\n## Ministry of {a.ministry}\n"
                f"Verdict: {a.verdict.value} (Score: {a.score}/10)\n"
                f"Summary: {a.summary}\n"
                f"Reasoning: {a.reasoning}\n"
                f"Key concerns: {', '.join(a.key_concerns)}\n"
                f"Recommendations: {', '.join(a.recommendations)}\n"
            )
            if a.counter_proposal:
                cp = a.counter_proposal
                assessments_text += (
                    f"\nCounter-proposal: {cp.title}\n"
                    f"Summary: {cp.summary}\n"
                    f"Key changes: {', '.join(cp.key_changes)}\n"
                    f"Expected benefits: {', '.join(cp.expected_benefits)}\n"
                    f"Feasibility: {cp.estimated_feasibility}\n"
                )

        return (
            f"# Decision\n"
            f"Title: {decision.title}\n"
            f"Date: {decision.date}\n"
            f"Summary: {decision.summary}\n"
            f"{full_text_line}\n"
            f"# Ministry Assessments and Counter-Proposals\n"
            f"{assessments_text}\n\n"
            f"Synthesize a unified counter-proposal from the ministry inputs above."
        )

    @staticmethod
    def _build_proposal(data: dict[str, Any], decision_id: str) -> CounterProposal:
        """Construct a ``CounterProposal`` from parsed data."""
        data.setdefault("decision_id", decision_id)
        return CounterProposal(**data)

    @staticmethod
    def _fallback(decision_id: str) -> CounterProposal:
        return CounterProposal(
            decision_id=decision_id,
            title="Counter-proposal in preparation",
            executive_summary="Synthesis not generated.",
            detailed_proposal="Synthesis of ministry counter-proposals failed.",
            ministry_contributions=["Response parsing failed"],
        )

    # Keep legacy name for backwards compatibility with tests.
    def _parse_response(self, response_text: str, decision_id: str) -> CounterProposal:
        from government.agents.json_parsing import extract_json

        data = extract_json(response_text)
        if data is not None:
            return self._build_proposal(data, decision_id)
        return self._fallback(decision_id)
