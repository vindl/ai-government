"""X (formerly Twitter) daily digest — compose and post a summary tweet."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ai_government.orchestrator import SessionResult

log = logging.getLogger(__name__)

SITE_BASE_URL = "https://vindl.github.io/ai-government"
MAX_TWEET_LENGTH = 280
DEFAULT_COOLDOWN_HOURS = 24
STATE_FILE = Path("output/twitter_state.json")


class TwitterState(BaseModel):
    """Persisted state for the X poster."""

    last_posted_at: datetime | None = None
    posted_decision_ids: list[str] = Field(default_factory=list)


def load_state(path: Path = STATE_FILE) -> TwitterState:
    """Read state from JSON file; return empty state if missing."""
    if not path.exists():
        return TwitterState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TwitterState.model_validate(raw)
    except (json.JSONDecodeError, ValueError):
        log.warning("Corrupt twitter state file %s — starting fresh", path)
        return TwitterState()


def save_state(state: TwitterState, path: Path = STATE_FILE) -> None:
    """Write state to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def should_post(state: TwitterState, cooldown_hours: int = DEFAULT_COOLDOWN_HOURS) -> bool:
    """Return True if enough time has passed since the last post."""
    if state.last_posted_at is None:
        return True
    elapsed = datetime.now(UTC) - state.last_posted_at
    return elapsed.total_seconds() >= cooldown_hours * 3600


def get_unposted_results(
    results: list[SessionResult],
    state: TwitterState,
) -> list[SessionResult]:
    """Filter out results whose decision IDs have already been posted."""
    posted = set(state.posted_decision_ids)
    return [r for r in results if r.decision.id not in posted]


def compose_daily_tweet(results: list[SessionResult]) -> str:
    """Build a daily digest tweet from analysis results.

    Picks up to 3 results sorted by critic ``decision_score`` ascending
    (most concerning first) and formats bullet points with a link.
    Truncates to fit within 280 characters.
    """
    if not results:
        return ""

    # Sort by critic score ascending (lowest = most concerning)
    def _sort_key(r: SessionResult) -> int:
        if r.critic_report is not None:
            return r.critic_report.decision_score
        return 10  # no critic report → least concerning

    sorted_results = sorted(results, key=_sort_key)[:3]

    header = "AI Government \u2014 daily digest\n\n"
    footer = f"\n\n{SITE_BASE_URL}\n\n#AIGovernment #Montenegro"

    # Build bullet lines, trimming decision titles to fit
    bullets: list[str] = []
    for r in sorted_results:
        score = r.critic_report.decision_score if r.critic_report else "?"
        title = r.decision.title
        cp_tag = " [+counter-proposal]" if r.counter_proposal else ""
        line = f"\u2022 {title}: {score}/10{cp_tag}"
        bullets.append(line)

    body = "\n".join(bullets)
    tweet = header + body + footer

    # Truncate bullets if tweet exceeds limit
    while len(tweet) > MAX_TWEET_LENGTH and bullets:
        # Shorten the last bullet's title
        last = bullets[-1]
        if len(last) > 20:
            bullets[-1] = last[:len(last) - 4] + "..."
            body = "\n".join(bullets)
            tweet = header + body + footer
        else:
            # Drop the last bullet entirely
            bullets.pop()
            body = "\n".join(bullets)
            tweet = header + body + footer

    return tweet


def post_tweet(text: str) -> str | None:
    """Post a tweet via the X API v2 (tweepy).

    Reads ``TWITTER_*`` env vars and uses tweepy with OAuth 1.0a.
    Returns the tweet ID on success, or ``None`` if credentials are
    missing or the API call fails.
    """
    consumer_key = os.environ.get("TWITTER_CONSUMER_KEY", "")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET", "")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        log.info("X API credentials not set — skipping post")
        return None

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        response = client.create_tweet(text=text)
        tweet_id: str = str(response.data["id"])
        log.info("Posted tweet %s", tweet_id)
        return tweet_id
    except Exception:
        log.exception("Failed to post to X")
        return None
