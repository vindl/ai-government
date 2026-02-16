"""Independent critic/auditor agent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from government.agents.base import _output_format_for
from government.config import SessionConfig
from government.models.assessment import Assessment, CriticReport
from government.prompts.critic import CRITIC_SYSTEM_PROMPT

if TYPE_CHECKING:
    from government.models.decision import GovernmentDecision

log = logging.getLogger(__name__)


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

        structured = await self._call_model(prompt)

        if structured is not None:
            return self._build_report(structured, decision.id)

        log.error(
            "CriticAgent: no structured output for %s, returning fallback",
            decision.id,
        )
        return self._fallback(decision.id)

    async def _call_model(self, prompt: str) -> dict[str, Any] | None:
        """Call Claude Code SDK and return structured output dict."""
        structured: dict[str, Any] | None = None
        async for message in claude_agent_sdk.query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=CRITIC_SYSTEM_PROMPT,
                model=self.config.model,
                max_turns=1,
                output_format=_output_format_for(CriticReport),
            ),
        ):
            if isinstance(message, ResultMessage) and message.structured_output is not None:
                structured = message.structured_output
        return structured

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
    def _build_report(data: dict[str, Any], decision_id: str) -> CriticReport:
        """Construct a ``CriticReport`` from parsed data."""
        data.setdefault("decision_id", decision_id)
        return CriticReport(**data)

    @staticmethod
    def _fallback(decision_id: str) -> CriticReport:
        return CriticReport(
            decision_id=decision_id,
            decision_score=5,
            assessment_quality_score=5,
            blind_spots=["Review could not be fully parsed"],
            overall_analysis="No review generated.",
            headline="Analiza u toku",
        )

    # Keep legacy name for backwards compatibility with tests.
    def _parse_response(self, response_text: str, decision_id: str) -> CriticReport:
        from government.agents.json_parsing import extract_json

        data = extract_json(response_text)
        if data is not None:
            return self._build_report(data, decision_id)
        return self._fallback(decision_id)
