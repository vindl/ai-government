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
MONTHLY_POST_LIMIT = 400  # X free tier allows 500/month; keep headroom
STATE_FILE = Path("output/twitter_state.json")


class TwitterState(BaseModel):
    """Persisted state for the X poster."""

    last_posted_at: datetime | None = None
    posted_decision_ids: list[str] = Field(default_factory=list)
    monthly_post_count: int = 0
    monthly_post_month: str = ""  # "YYYY-MM" for the tracked month


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


def _current_month() -> str:
    """Return current month as 'YYYY-MM'."""
    return datetime.now(UTC).strftime("%Y-%m")


def should_post(state: TwitterState, cooldown_hours: int = DEFAULT_COOLDOWN_HOURS) -> bool:
    """Return True if enough time has passed and monthly limit not reached."""
    if state.last_posted_at is not None:
        elapsed = datetime.now(UTC) - state.last_posted_at
        if elapsed.total_seconds() < cooldown_hours * 3600:
            return False

    # Check monthly limit (reset counter if new month)
    current = _current_month()
    if state.monthly_post_month == current and state.monthly_post_count >= MONTHLY_POST_LIMIT:
        log.warning(
            "Monthly post limit reached (%d/%d) — skipping",
            state.monthly_post_count,
            MONTHLY_POST_LIMIT,
        )
        return False

    return True


def record_post(state: TwitterState) -> None:
    """Increment the monthly post counter, resetting if new month."""
    current = _current_month()
    if state.monthly_post_month != current:
        state.monthly_post_month = current
        state.monthly_post_count = 0
    state.monthly_post_count += 1


def get_unposted_results(
    results: list[SessionResult],
    state: TwitterState,
) -> list[SessionResult]:
    """Filter out results whose decision IDs have already been posted."""
    posted = set(state.posted_decision_ids)
    return [r for r in results if r.decision.id not in posted]


def compose_analysis_tweet(result: SessionResult) -> str:
    """Build a tweet for a single completed analysis."""
    title = result.decision.title
    score = result.critic_report.decision_score if result.critic_report else "?"
    headline = result.critic_report.headline if result.critic_report else ""
    cp_tag = " [+counter-proposal]" if result.counter_proposal else ""
    link = f"{SITE_BASE_URL}/decisions/{result.decision.id}.html"

    text = f"{title}: {score}/10{cp_tag}"
    if headline:
        text += f"\n\n{headline}"
    text += f"\n\n{link}\n\n#AIGovernment #Montenegro"

    if len(text) > MAX_TWEET_LENGTH:
        # Trim headline to fit
        overhead = len(text) - MAX_TWEET_LENGTH
        if headline and len(headline) > overhead + 3:
            headline = headline[: len(headline) - overhead - 3] + "..."
            text = f"{title}: {score}/10{cp_tag}\n\n{headline}\n\n{link}\n\n#AIGovernment #Montenegro"
        else:
            text = f"{title}: {score}/10{cp_tag}\n\n{link}\n\n#AIGovernment #Montenegro"

    return text[:MAX_TWEET_LENGTH]


def try_post_analysis(result: SessionResult) -> bool:
    """Post a tweet for a completed analysis, respecting monthly limits.

    Returns True if posted, False otherwise. Non-fatal.
    """
    state = load_state()

    # Check monthly limit only (no cooldown between analysis tweets)
    current = _current_month()
    if state.monthly_post_month == current and state.monthly_post_count >= MONTHLY_POST_LIMIT:
        log.warning("Monthly post limit reached — skipping analysis tweet")
        return False

    # Skip if already posted for this decision
    if result.decision.id in state.posted_decision_ids:
        return False

    text = compose_analysis_tweet(result)
    if not text:
        return False

    log.info("Composed analysis tweet:\n%s", text)
    tweet_id = post_tweet(text)
    if tweet_id is None:
        return False

    state.last_posted_at = datetime.now(UTC)
    state.posted_decision_ids.append(result.decision.id)
    record_post(state)
    save_state(state)
    return True


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
