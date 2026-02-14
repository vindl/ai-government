"""Markdown scorecard renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_government.orchestrator import SessionResult


def _verdict_emoji(verdict_value: str) -> str:
    mapping = {
        "strongly_positive": "++++",
        "positive": "+++",
        "neutral": "~",
        "negative": "---",
        "strongly_negative": "----",
    }
    return mapping.get(verdict_value, "?")


def _score_bar(score: int) -> str:
    filled = "#" * score
    empty = "." * (10 - score)
    return f"[{filled}{empty}] {score}/10"


def render_scorecard(result: SessionResult) -> str:
    """Render a full session result as a markdown scorecard."""
    d = result.decision
    lines: list[str] = [
        "# AI Government Scorecard",
        f"## {d.title}",
        f"**Date**: {d.date}  ",
        f"**Category**: {d.category}  ",
        f"**Source**: {d.source_url or 'N/A'}",
        "",
        f"> {d.summary}",
        "",
    ]

    # Critic headline
    if result.critic_report:
        cr = result.critic_report
        lines.extend([
            "## Headline",
            f"**{cr.headline}**",
            "",
            f"Decision Score: {_score_bar(cr.decision_score)}  ",
            f"Assessment Quality: {_score_bar(cr.assessment_quality_score)}",
            "",
        ])

    # Ministry assessments
    lines.append("## Ministry Assessments")
    lines.append("")
    lines.append("| Ministry | Verdict | Score |")
    lines.append("|----------|---------|-------|")

    for a in result.assessments:
        lines.append(
            f"| {a.ministry} | {_verdict_emoji(a.verdict.value)} {a.verdict.value} | {_score_bar(a.score)} |"
        )

    lines.append("")

    # Detailed assessments
    for a in result.assessments:
        lines.extend([
            f"### Ministry of {a.ministry}",
            f"**Verdict**: {a.verdict.value} ({a.score}/10)",
            "",
            a.summary,
            "",
        ])
        if a.key_concerns:
            lines.append("**Key Concerns:**")
            for concern in a.key_concerns:
                lines.append(f"- {concern}")
            lines.append("")
        if a.recommendations:
            lines.append("**Recommendations:**")
            for rec in a.recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        if a.counter_proposal:
            cp = a.counter_proposal
            lines.extend([
                f"**Counter-proposal: {cp.title}**",
                cp.summary,
                "",
            ])
            if cp.key_changes:
                lines.append("Key changes:")
                for change in cp.key_changes:
                    lines.append(f"- {change}")
                lines.append("")

    # Parliament debate
    if result.debate:
        db = result.debate
        lines.extend([
            "## Parliamentary Debate",
            f"**Overall Verdict**: {db.overall_verdict.value}",
            "",
            "### Consensus",
            db.consensus_summary,
            "",
        ])
        if db.disagreements:
            lines.append("### Points of Disagreement")
            for d_item in db.disagreements:
                lines.append(f"- {d_item}")
            lines.append("")
        lines.extend([
            "### Debate Transcript",
            db.debate_transcript,
            "",
        ])

    # Critic report
    if result.critic_report:
        cr = result.critic_report
        lines.extend([
            "## Independent Critic Report",
            "",
            cr.overall_analysis,
            "",
        ])
        if cr.blind_spots:
            lines.append("### Blind Spots")
            for bs in cr.blind_spots:
                lines.append(f"- {bs}")
            lines.append("")

    # Unified counter-proposal
    if result.counter_proposal:
        ucp = result.counter_proposal
        lines.extend([
            "## Kontraprijedlog AI Vlade",
            f"### {ucp.title}",
            "",
            f"**{ucp.executive_summary}**",
            "",
            ucp.detailed_proposal,
            "",
        ])
        if ucp.key_differences:
            lines.append("### Key Differences")
            for diff in ucp.key_differences:
                lines.append(f"- {diff}")
            lines.append("")
        if ucp.implementation_steps:
            lines.append("### Implementation Steps")
            for step in ucp.implementation_steps:
                lines.append(f"1. {step}")
            lines.append("")
        if ucp.risks_and_tradeoffs:
            lines.append("### Risks & Tradeoffs")
            for risk in ucp.risks_and_tradeoffs:
                lines.append(f"- {risk}")
            lines.append("")
        if ucp.ministry_contributions:
            lines.append("### Ministry Contributions")
            for contrib in ucp.ministry_contributions:
                lines.append(f"- {contrib}")
            lines.append("")

    lines.append("---")
    lines.append("*Generated by AI Government*")

    return "\n".join(lines)
