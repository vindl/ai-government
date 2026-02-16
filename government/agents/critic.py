"""Independent critic/auditor agent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from government.config import SessionConfig
from government.models.assessment import Assessment, CriticReport
from government.prompts.critic import CRITIC_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision


class CriticAgent:
    """Independent auditor that scores the decision and all assessments."""

    def __init__(self, session_config: SessionConfig | None = None) -> None:
        self.config = session_config or SessionConfig()

    async def review(
        self,
        decision: GovernmentDecision,
        assessments: list[Assessment],
    ) -> CriticReport:
        """Produce an independent critic report on the decision and assessments."""
        prompt = self._build_prompt(decision, assessments)

        response_text = ""
        async for message in claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=CRITIC_SYSTEM_PROMPT,
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
            f"Reasoning: {a.reasoning}\n"
            f"Key concerns: {', '.join(a.key_concerns)}"
            for a in assessments
        )

        full_text_line = f"Full text: {decision.full_text}\n" if decision.full_text else ""
        return (
            f"# Decision to Review\n"
            f"Title: {decision.title}\n"
            f"Date: {decision.date}\n"
            f"Summary: {decision.summary}\n"
            f"{full_text_line}\n"
            f"# Ministry Assessments\n{assessments_text}\n\n"
            f"Provide your independent critic report."
        )

    def _parse_response(self, response_text: str, decision_id: str) -> CriticReport:
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            data = json.loads(response_text[start:end])
            return CriticReport(**data)
        except (ValueError, json.JSONDecodeError):
            analysis = response_text[:500] if response_text else "No review generated."
            return CriticReport(
                decision_id=decision_id,
                decision_score=5,
                assessment_quality_score=5,
                blind_spots=["Review could not be fully parsed"],
                overall_analysis=analysis,
                headline="Analiza u toku",
            )
