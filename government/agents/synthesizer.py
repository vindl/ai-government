"""Synthesizer agent — consolidates ministry counter-proposals into a unified alternative."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from government.agents.json_parsing import RETRY_PROMPT, extract_json
from government.config import SessionConfig
from government.models.assessment import Assessment, CounterProposal
from government.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)

MAX_RETRIES = 1


class SynthesizerAgent:
    """Consolidates per-ministry counter-proposals into a unified alternative."""

    def __init__(self, session_config: SessionConfig | None = None) -> None:
        self.config = session_config or SessionConfig()

    async def synthesize(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> CounterProposal:
        """Synthesize ministry counter-proposals into a unified counter-proposal."""
        prompt = self._build_prompt(decision, assessments)

        response_text = await self._call_model(prompt, max_turns=1)

        data = extract_json(response_text)
        if data is not None:
            return self._build_proposal(data, decision.id)

        # Retry once with an explicit JSON-only follow-up.
        for attempt in range(MAX_RETRIES):
            log.warning(
                "SynthesizerAgent: no valid JSON in response for %s (attempt %d), retrying",
                decision.id,
                attempt + 1,
            )
            retry_text = await self._call_model(
                f"{prompt}\n\n{RETRY_PROMPT}", max_turns=1
            )
            data = extract_json(retry_text)
            if data is not None:
                return self._build_proposal(data, decision.id)

        log.error(
            "SynthesizerAgent: all retries exhausted for %s, returning fallback",
            decision.id,
        )
        return self._fallback(response_text, decision.id)

    async def _call_model(self, prompt: str, *, max_turns: int = 1) -> str:
        """Call Claude Code SDK and collect text response."""
        response_text = ""
        async for message in claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
                model=self.config.model,
                max_turns=max_turns,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
        return response_text

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
    def _build_proposal(data: dict[str, object], decision_id: str) -> CounterProposal:
        """Construct a ``CounterProposal`` from parsed JSON *data*."""
        data.setdefault("decision_id", decision_id)
        return CounterProposal(**data)

    @staticmethod
    def _fallback(response_text: str, decision_id: str) -> CounterProposal:
        summary = response_text[:500] if response_text else "Synthesis not generated."
        return CounterProposal(
            decision_id=decision_id,
            title="Counter-proposal in preparation",
            executive_summary=summary,
            detailed_proposal="Synthesis of ministry counter-proposals failed.",
            ministry_contributions=["Response parsing failed"],
        )

    # Keep legacy name for backwards compatibility with tests.
    def _parse_response(self, response_text: str, decision_id: str) -> CounterProposal:
        data = extract_json(response_text)
        if data is not None:
            return self._build_proposal(data, decision_id)
        return self._fallback(response_text, decision_id)
