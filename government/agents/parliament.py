"""Parliament debate simulation agent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from government.config import SessionConfig
from government.models.assessment import Assessment, ParliamentDebate
from government.prompts.parliament import PARLIAMENT_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision


class ParliamentAgent:
    """Synthesizes all ministry assessments into a parliamentary debate."""

    def __init__(self, session_config: SessionConfig | None = None) -> None:
        self.config = session_config or SessionConfig()

    async def debate(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> ParliamentDebate:
        """Run a parliamentary debate on the decision given all ministry assessments."""
        prompt = self._build_prompt(decision, assessments)

        response_text = ""
        async for message in claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=PARLIAMENT_SYSTEM_PROMPT,
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

    def _parse_response(self, response_text: str, decision_id: str) -> ParliamentDebate:
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            data = json.loads(response_text[start:end])
            return ParliamentDebate(**data)
        except (ValueError, json.JSONDecodeError):
            transcript = response_text[:1000] if response_text else "No debate generated."
            return ParliamentDebate(
                decision_id=decision_id,
                consensus_summary="Debate could not be fully parsed.",
                disagreements=[],
                overall_verdict="neutral",
                debate_transcript=transcript,
            )
