"""Social media thread formatter (X / formerly Twitter)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_government.orchestrator import SessionResult


MAX_TWEET_LENGTH = 280


def _truncate(text: str, max_len: int = MAX_TWEET_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_thread(result: SessionResult) -> list[str]:
    """Format a session result as an X thread."""
    d = result.decision
    tweets: list[str] = []

    # Tweet 1: Headline + decision
    headline = ""
    if result.critic_report:
        headline = f"{result.critic_report.headline}\n\n"
    tweets.append(_truncate(
        f"{headline}"
        f"AI Vlada analizira: {d.title}\n\n"
        f"Rezultati analize:"
    ))

    # Tweet 2-N: Ministry scores
    for a in result.assessments:
        score_visual = "#" * a.score + "." * (10 - a.score)
        tweets.append(_truncate(
            f"Ministarstvo {a.ministry}: {a.score}/10\n"
            f"[{score_visual}]\n\n"
            f"{a.summary}"
        ))

    # Parliament summary
    if result.debate:
        tweets.append(_truncate(
            f"Skupstina: {result.debate.overall_verdict.value}\n\n"
            f"{result.debate.consensus_summary}"
        ))

    # Critic headline
    if result.critic_report:
        cr = result.critic_report
        tweets.append(_truncate(
            f"Nezavisna ocjena: {cr.decision_score}/10\n\n"
            f"{cr.overall_analysis[:200]}"
        ))

    # Counter-proposal
    if result.counter_proposal:
        cp = result.counter_proposal
        tweets.append(_truncate(
            f"Kontraprijedlog: {cp.title}\n\n"
            f"{cp.executive_summary}"
        ))

    # Final tweet
    tweets.append(_truncate(
        "Kompletna analiza: [link]\n\n"
        "#AIVlada #CrnaGora #Transparentnost"
    ))

    return tweets


def format_thread_text(result: SessionResult) -> str:
    """Format thread as plain text with tweet separators."""
    tweets = format_thread(result)
    parts: list[str] = []
    for i, tweet in enumerate(tweets, 1):
        parts.append(f"--- Tweet {i}/{len(tweets)} ---\n{tweet}")
    return "\n\n".join(parts)
