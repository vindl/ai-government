"""X (formerly Twitter) posting — compose and post per-analysis tweets."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ai_government.orchestrator import SessionResult

log = logging.getLogger(__name__)

SITE_BASE_URL = "https://vindl.github.io/ai-government"
MAX_TWEET_LENGTH = 280
MONTHLY_POST_LIMIT = 400  # X free tier allows 500/month; keep headroom
STATE_FILE = Path("output/twitter_state.json")


class BilingualTweet(NamedTuple):
    """A bilingual tweet pair: Montenegrin primary + English reply."""

    me: str  # Montenegrin (primary tweet)
    en: str  # English (thread reply)


def translate_headline(headline: str) -> str:
    """Translate an English headline to Montenegrin using Claude.

    Falls back to the original headline if translation fails.
    """
    if not headline:
        return headline
    try:
        result = subprocess.run(  # noqa: S603
            [
                "claude",
                "-p",
                (
                    "Translate the following headline to Montenegrin (Latin script). "
                    "Return ONLY the translated text, nothing else. "
                    "Keep it concise — same length or shorter.\n\n"
                    f"{headline}"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        translated = result.stdout.strip()
        if translated and result.returncode == 0:
            return translated
    except Exception:
        log.warning("Headline translation failed — using English")
    return headline


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


def _truncate_at_word_boundary(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len* characters at a word boundary.

    If truncation is needed the result ends with ``…`` (single char ellipsis)
    and never breaks mid-word.
    """
    if len(text) <= max_len:
        return text
    # Reserve one char for the ellipsis
    truncated = text[: max_len - 1]
    # Find last space to avoid cutting mid-word
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "\u2026"


def compose_analysis_tweet(
    result: SessionResult,
    *,
    headline_me: str = "",
) -> BilingualTweet:
    """Build a bilingual tweet pair for a single completed analysis.

    Returns a ``BilingualTweet`` with Montenegrin primary and English reply.

    Montenegrin format::

        <headline_me>

        Ocjena: X/10

        <link>

        #AIVlada #CrnaGora

    English reply::

        🌐 <headline_en>

        Score: X/10

        <link>

        #AIGovernment #Montenegro

    If *headline_me* is not provided, the English headline is used as-is for
    the Montenegrin tweet (caller should translate beforehand).
    """
    score = result.critic_report.decision_score if result.critic_report else "?"
    headline_en = result.critic_report.headline if result.critic_report else ""
    if not headline_me:
        headline_me = headline_en
    link = f"{SITE_BASE_URL}/decisions/{result.decision.id}.html"

    # --- Montenegrin primary tweet ---
    me_suffix = f"\n\nOcjena: {score}/10\n\n{link}\n\n#AIVlada #CrnaGora"
    if headline_me:
        max_hl = MAX_TWEET_LENGTH - len(me_suffix)
        me_text = _truncate_at_word_boundary(headline_me, max_hl) + me_suffix
    else:
        me_text = f"Ocjena: {score}/10\n\n{link}\n\n#AIVlada #CrnaGora"
    me_text = me_text[:MAX_TWEET_LENGTH]

    # --- English reply ---
    en_suffix = f"\n\nScore: {score}/10\n\n{link}\n\n#AIGovernment #Montenegro"
    en_prefix = "\U0001f310 "  # 🌐
    if headline_en:
        max_hl = MAX_TWEET_LENGTH - len(en_suffix) - len(en_prefix)
        en_text = en_prefix + _truncate_at_word_boundary(headline_en, max_hl) + en_suffix
    else:
        en_text = f"\U0001f310 Score: {score}/10\n\n{link}\n\n#AIGovernment #Montenegro"
    en_text = en_text[:MAX_TWEET_LENGTH]

    return BilingualTweet(me=me_text, en=en_text)


def try_post_analysis(result: SessionResult) -> bool:
    """Post a bilingual tweet thread for a completed analysis.

    Posts a Montenegrin primary tweet and an English reply thread.
    Both tweets count as a single post toward the monthly limit.

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

    # Translate headline to Montenegrin
    headline_en = result.critic_report.headline if result.critic_report else ""
    headline_me = translate_headline(headline_en)

    tweets = compose_analysis_tweet(result, headline_me=headline_me)
    if not tweets.me:
        return False

    log.info("Composed analysis tweet (MNE):\n%s", tweets.me)
    log.info("Composed analysis tweet (EN):\n%s", tweets.en)

    # Post Montenegrin primary
    tweet_id = post_tweet(tweets.me)
    if tweet_id is None:
        return False

    # Post English reply in thread
    if tweets.en:
        reply_id = post_tweet(tweets.en, in_reply_to_tweet_id=tweet_id)
        if reply_id is None:
            log.warning("Failed to post English reply — primary tweet still posted")

    state.last_posted_at = datetime.now(UTC)
    state.posted_decision_ids.append(result.decision.id)
    record_post(state)
    save_state(state)
    return True



def post_tweet(text: str, *, in_reply_to_tweet_id: str | None = None) -> str | None:
    """Post a tweet via the X API v2 (tweepy).

    Reads ``TWITTER_*`` env vars and uses tweepy with OAuth 1.0a.
    Returns the tweet ID on success, or ``None`` if credentials are
    missing or the API call fails.

    If *in_reply_to_tweet_id* is provided, the tweet is posted as a reply
    to the given tweet (thread).
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
        kwargs: dict[str, str] = {"text": text}
        if in_reply_to_tweet_id is not None:
            kwargs["in_reply_to_tweet_id"] = in_reply_to_tweet_id
        response = client.create_tweet(**kwargs)
        tweet_id: str = str(response.data["id"])
        log.info("Posted tweet %s", tweet_id)
        return tweet_id
    except Exception:
        log.exception("Failed to post to X")
        return None
