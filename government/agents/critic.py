"""Independent critic/auditor agent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock

from government.agents.json_parsing import RETRY_PROMPT, extract_json
from government.config import SessionConfig
from government.models.assessment import Assessment, CriticReport
from government.prompts.critic import CRITIC_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)

MAX_RETRIES = 1


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

        response_text = await self._call_model(prompt, max_turns=1)

        data = extract_json(response_text)
        if data is not None:
            return self._build_report(data, decision.id)

        # Retry once with an explicit JSON-only follow-up.
        for attempt in range(MAX_RETRIES):
            log.warning(
                "CriticAgent: no valid JSON in response for %s (attempt %d), retrying",
                decision.id,
                attempt + 1,
            )
            retry_text = await self._call_model(
                f"{prompt}\n\n{RETRY_PROMPT}", max_turns=1
            )
            data = extract_json(retry_text)
            if data is not None:
                return self._build_report(data, decision.id)

        log.error(
            "CriticAgent: all retries exhausted for %s, returning fallback",
            decision.id,
        )
        return self._fallback(response_text, decision.id)

    async def _call_model(self, prompt: str, *, max_turns: int = 1) -> str:
        """Call Claude Code SDK and collect text response."""
        response_text = ""
        async for message in claude_agent_sdk.query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=CRITIC_SYSTEM_PROMPT,
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

    @staticmethod
    def _build_report(data: dict[str, object], decision_id: str) -> CriticReport:
        """Construct a ``CriticReport`` from parsed JSON *data*."""
        data.setdefault("decision_id", decision_id)
        return CriticReport(**data)

    @staticmethod
    def _fallback(response_text: str, decision_id: str) -> CriticReport:
        analysis = response_text[:500] if response_text else "No review generated."
        return CriticReport(
            decision_id=decision_id,
            decision_score=5,
            assessment_quality_score=5,
            blind_spots=["Review could not be fully parsed"],
            overall_analysis=analysis,
            headline="Analiza u toku",
        )

    # Keep legacy name for backwards compatibility with tests.
    def _parse_response(self, response_text: str, decision_id: str) -> CriticReport:
        data = extract_json(response_text)
        if data is not None:
            return self._build_report(data, decision_id)
        return self._fallback(response_text, decision_id)
