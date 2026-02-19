"""Tests for debate_transcript Montenegrin localization."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from government.models.assessment import (
    Assessment,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from government.orchestrator import SessionResult
from government.output.localization import localize_result

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from claude_agent_sdk import ClaudeAgentOptions


def _make_result_with_debate() -> SessionResult:
    """Create a SessionResult with a debate that has a transcript."""
    decision = GovernmentDecision(
        id="loc-001",
        title="Test Decision",
        summary="A test decision summary.",
        date=date(2026, 2, 19),
        category="fiscal",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="loc-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Positive assessment.",
        reasoning="Good reasoning.",
    )
    debate = ParliamentDebate(
        decision_id="loc-001",
        consensus_summary="Ministries agree on the approach.",
        disagreements=["Fiscal impact disputed"],
        overall_verdict=Verdict.POSITIVE,
        debate_transcript="Finance argues for spending controls. Justice supports.",
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
    )


class TestDebateTranscriptLocalization:
    """debate_transcript should be translated to Montenegrin by localize_result."""

    @pytest.mark.anyio
    async def test_debate_transcript_mne_populated(self) -> None:
        """localize_result should populate debate_transcript_mne."""
        result = _make_result_with_debate()
        assert result.debate is not None
        assert result.debate.debate_transcript_mne == ""

        # Track which field sets get translated
        call_payloads: list[dict[str, Any]] = []

        from claude_agent_sdk import AssistantMessage, TextBlock

        async def fake_query(
            *, prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[Any]:
            # Parse out the JSON from the prompt
            start = prompt.find("```json\n") + len("```json\n")
            end = prompt.find("\n```", start)
            fields = json.loads(prompt[start:end])
            call_payloads.append(fields)

            # Return "translated" versions by appending " (MNE)"
            translated: dict[str, Any] = {}
            for k, v in fields.items():
                if isinstance(v, str):
                    translated[k] = v + " (MNE)"
                elif isinstance(v, list):
                    translated[k] = [item + " (MNE)" if isinstance(item, str) else item for item in v]
                else:
                    translated[k] = v

            body = json.dumps(translated, ensure_ascii=False)
            msg = AssistantMessage(
                model="test", content=[TextBlock(text=body)]
            )
            yield msg

        from unittest.mock import patch

        with patch(
            "government.output.localization.claude_agent_sdk.query",
            side_effect=fake_query,
        ):
            localized = await localize_result(result)

        assert localized.debate is not None
        assert localized.debate.debate_transcript_mne == (
            "Finance argues for spending controls. Justice supports. (MNE)"
        )
        assert localized.debate.consensus_summary_mne == (
            "Ministries agree on the approach. (MNE)"
        )

        # Verify debate_transcript was included in one of the translation calls
        debate_call = [p for p in call_payloads if "debate_transcript" in p]
        assert len(debate_call) == 1
        assert debate_call[0]["debate_transcript"] == (
            "Finance argues for spending controls. Justice supports."
        )

    @pytest.mark.anyio
    async def test_debate_transcript_mne_default_empty(self) -> None:
        """debate_transcript_mne defaults to empty string."""
        debate = ParliamentDebate(
            decision_id="t",
            consensus_summary="Consensus",
            overall_verdict=Verdict.NEUTRAL,
            debate_transcript="Transcript",
        )
        assert debate.debate_transcript_mne == ""

    @pytest.mark.anyio
    async def test_no_debate_skips_translation(self) -> None:
        """localize_result should not fail when debate is None."""
        decision = GovernmentDecision(
            id="loc-002",
            title="Test",
            summary="Summary",
            date=date(2026, 2, 19),
            category="fiscal",
        )
        result = SessionResult(decision=decision, assessments=[])

        from unittest.mock import patch

        from claude_agent_sdk import AssistantMessage, TextBlock

        async def fake_query(
            *, prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[Any]:
            start = prompt.find("```json\n") + len("```json\n")
            end = prompt.find("\n```", start)
            fields = json.loads(prompt[start:end])
            body = json.dumps(fields, ensure_ascii=False)
            msg = AssistantMessage(
                model="test", content=[TextBlock(text=body)]
            )
            yield msg

        with patch(
            "government.output.localization.claude_agent_sdk.query",
            side_effect=fake_query,
        ):
            localized = await localize_result(result)

        assert localized.debate is None
