"""Localization — translates English analysis content to Montenegrin."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock

if TYPE_CHECKING:
    from government.orchestrator import SessionResult

_logger = logging.getLogger(__name__)

TRANSLATION_SYSTEM_PROMPT = (
    "You are a professional English-to-Montenegrin translator. "
    "Translate all provided text fields from English to Montenegrin (Latin script). "
    "Preserve meaning, tone, and formatting. Use natural Montenegrin phrasing. "
    "Return ONLY a JSON object with the same keys, translated values."
)


def _build_translation_prompt(fields: dict[str, Any]) -> str:
    """Build a prompt asking for translation of the given fields."""
    return (
        "Translate the following JSON fields from English to Montenegrin (Latin script). "
        "Return ONLY a valid JSON object with exactly the same keys, "
        "but with values translated to Montenegrin.\n\n"
        f"```json\n{json.dumps(fields, ensure_ascii=False, indent=2)}\n```"
    )


async def _translate_fields(fields: dict[str, Any], model: str) -> dict[str, Any]:
    """Translate a dict of fields from English to Montenegrin via LLM."""
    if not any(v for v in fields.values() if v):
        return fields

    prompt = _build_translation_prompt(fields)
    response_text = ""

    async for message in claude_agent_sdk.query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=TRANSLATION_SYSTEM_PROMPT,
            model=model,
            max_turns=1,
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    response_text += block.text

    try:
        start = response_text.index("{")
        end = response_text.rindex("}") + 1
        result: dict[str, Any] = json.loads(response_text[start:end])
        return result
    except (ValueError, json.JSONDecodeError):
        _logger.warning("Translation response could not be parsed, using originals")
        return fields


async def localize_result(result: SessionResult, model: str = "claude-sonnet-4-5-20250929") -> SessionResult:
    """Populate Montenegrin translation fields on a SessionResult.

    Translates key public-facing fields: critic headline, assessment summaries,
    key findings, counter-proposal text, and debate content.

    Uses a cost-effective model (Sonnet) by default since translation doesn't
    require deep reasoning.
    """
    # Translate decision title and summary
    dec_fields: dict[str, Any] = {
        "title": result.decision.title,
        "summary": result.decision.summary,
    }
    dec_translated = await _translate_fields(dec_fields, model)
    result.decision.title_mne = dec_translated.get("title", result.decision.title)
    result.decision.summary_mne = dec_translated.get("summary", result.decision.summary)

    # Translate critic report fields
    if result.critic_report is not None:
        cr_fields = {
            "headline": result.critic_report.headline,
            "overall_analysis": result.critic_report.overall_analysis,
            "blind_spots": result.critic_report.blind_spots,
        }
        translated = await _translate_fields(cr_fields, model)
        result.critic_report.headline_mne = translated.get(
            "headline", result.critic_report.headline
        )
        result.critic_report.overall_analysis_mne = translated.get(
            "overall_analysis", result.critic_report.overall_analysis
        )
        result.critic_report.blind_spots_mne = translated.get(
            "blind_spots", result.critic_report.blind_spots
        )

    # Translate each assessment
    for assessment in result.assessments:
        a_fields: dict[str, Any] = {
            "summary": assessment.summary,
            "key_concerns": assessment.key_concerns,
            "recommendations": assessment.recommendations,
        }
        if assessment.executive_summary:
            a_fields["executive_summary"] = assessment.executive_summary

        translated = await _translate_fields(a_fields, model)
        assessment.summary_mne = translated.get("summary", assessment.summary)
        assessment.key_concerns_mne = translated.get(
            "key_concerns", assessment.key_concerns
        )
        assessment.recommendations_mne = translated.get(
            "recommendations", assessment.recommendations
        )
        if assessment.executive_summary:
            assessment.executive_summary_mne = translated.get(
                "executive_summary", assessment.executive_summary
            )

        # Translate ministry counter-proposal if present
        if assessment.counter_proposal is not None:
            cp_fields: dict[str, Any] = {
                "title": assessment.counter_proposal.title,
                "summary": assessment.counter_proposal.summary,
                "key_changes": assessment.counter_proposal.key_changes,
                "expected_benefits": assessment.counter_proposal.expected_benefits,
                "estimated_feasibility": assessment.counter_proposal.estimated_feasibility,
            }
            cp_translated = await _translate_fields(cp_fields, model)
            assessment.counter_proposal.title_mne = cp_translated.get(
                "title", assessment.counter_proposal.title
            )
            assessment.counter_proposal.summary_mne = cp_translated.get(
                "summary", assessment.counter_proposal.summary
            )
            assessment.counter_proposal.key_changes_mne = cp_translated.get(
                "key_changes", assessment.counter_proposal.key_changes
            )
            assessment.counter_proposal.expected_benefits_mne = cp_translated.get(
                "expected_benefits", assessment.counter_proposal.expected_benefits
            )
            assessment.counter_proposal.estimated_feasibility_mne = cp_translated.get(
                "estimated_feasibility", assessment.counter_proposal.estimated_feasibility
            )

    # Translate parliamentary debate
    if result.debate is not None:
        d_fields: dict[str, Any] = {
            "consensus_summary": result.debate.consensus_summary,
            "disagreements": result.debate.disagreements,
        }
        translated = await _translate_fields(d_fields, model)
        result.debate.consensus_summary_mne = translated.get(
            "consensus_summary", result.debate.consensus_summary
        )
        result.debate.disagreements_mne = translated.get(
            "disagreements", result.debate.disagreements
        )

    # Translate unified counter-proposal
    if result.counter_proposal is not None:
        ucp_fields: dict[str, Any] = {
            "title": result.counter_proposal.title,
            "executive_summary": result.counter_proposal.executive_summary,
            "detailed_proposal": result.counter_proposal.detailed_proposal,
            "ministry_contributions": result.counter_proposal.ministry_contributions,
            "key_differences": result.counter_proposal.key_differences,
            "implementation_steps": result.counter_proposal.implementation_steps,
            "risks_and_tradeoffs": result.counter_proposal.risks_and_tradeoffs,
        }
        translated = await _translate_fields(ucp_fields, model)
        result.counter_proposal.title_mne = translated.get(
            "title", result.counter_proposal.title
        )
        result.counter_proposal.executive_summary_mne = translated.get(
            "executive_summary", result.counter_proposal.executive_summary
        )
        result.counter_proposal.detailed_proposal_mne = translated.get(
            "detailed_proposal", result.counter_proposal.detailed_proposal
        )
        result.counter_proposal.ministry_contributions_mne = translated.get(
            "ministry_contributions", result.counter_proposal.ministry_contributions
        )
        result.counter_proposal.key_differences_mne = translated.get(
            "key_differences", result.counter_proposal.key_differences
        )
        result.counter_proposal.implementation_steps_mne = translated.get(
            "implementation_steps", result.counter_proposal.implementation_steps
        )
        result.counter_proposal.risks_and_tradeoffs_mne = translated.get(
            "risks_and_tradeoffs", result.counter_proposal.risks_and_tradeoffs
        )

    return result


def has_montenegrin_content(result: SessionResult) -> bool:
    """Check if a SessionResult has Montenegrin translations populated."""
    if result.critic_report is not None and result.critic_report.headline_mne:
        return True
    return bool(
        result.assessments and any(a.summary_mne for a in result.assessments)
    )
