"""Synthesizer agent — consolidates ministry counter-proposals into a unified alternative."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from government.config import SessionConfig
from government.models.assessment import Assessment, CounterProposal
from government.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision


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

        response_text = ""
        async for message in claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
                model=self.config.model,
                max_turns=1,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text

        return self._parse_response(response_text, decision.id)

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

    def _parse_response(self, response_text: str, decision_id: str) -> CounterProposal:
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            data = json.loads(response_text[start:end])
            return CounterProposal(**data)
        except (ValueError, json.JSONDecodeError):
            summary = response_text[:500] if response_text else "Synthesis not generated."
            return CounterProposal(
                decision_id=decision_id,
                title="Counter-proposal in preparation",
                executive_summary=summary,
                detailed_proposal="Synthesis of ministry counter-proposals failed.",
                ministry_contributions=["Response parsing failed"],
            )
