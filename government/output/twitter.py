"""X (formerly Twitter) posting — compose and post per-analysis tweets."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from government.orchestrator import SessionResult

log = logging.getLogger(__name__)

SITE_BASE_URL = "https://vindl.github.io/ai-government"
MAX_TWEET_LENGTH = 280
MONTHLY_POST_LIMIT = 400  # X free tier allows 500/month; keep headroom
STATE_FILE = Path("output/twitter_state.json")
METRICS_FILE = Path("output/data/tweet_metrics.jsonl")

# Age window for metrics collection: fetch metrics for tweets posted 24-48h ago
METRICS_MIN_AGE = timedelta(hours=24)
METRICS_MAX_AGE = timedelta(hours=48)


class BilingualTweet(NamedTuple):
    """A bilingual tweet pair: English primary + Montenegrin reply."""

    en: str  # English (primary tweet)
    me: str  # Montenegrin (thread reply)


class PostedTweetRecord(BaseModel):
    """Metadata for a posted tweet, stored in TwitterState for later metrics fetch."""

    tweet_id: str
    reply_tweet_id: str | None = None
    decision_id: str
    posted_at: datetime
    category: str = ""


class TweetMetrics(BaseModel):
    """Public metrics fetched from the X API for a single tweet."""

    tweet_id: str
    decision_id: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    impression_count: int = 0
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    # Derived
    engagement_rate: float = 0.0  # (likes + retweets + replies) / impressions


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
    posted_tweets: list[PostedTweetRecord] = Field(default_factory=list)


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


def load_unposted_from_dir(data_dir: Path) -> list[SessionResult]:
    """Load completed analyses from *data_dir* that haven't been tweeted yet.

    Reads all ``SessionResult`` JSON files and filters against
    ``twitter_state.json``.  Returns results sorted oldest-first so the
    backlog drains in chronological order.
    """
    from government.output.site_builder import load_results_from_dir

    if not data_dir.exists():
        return []
    results = load_results_from_dir(data_dir)
    state = load_state()
    unposted = get_unposted_results(results, state)
    # Sort by decision date (oldest first) so backlog drains chronologically
    unposted.sort(key=lambda r: r.decision.date)
    return unposted


def post_tweet_backlog(data_dir: Path, *, limit: int = 3) -> int:
    """Post tweets for up to *limit* unposted analyses from the backlog.

    Returns the number of tweets successfully posted.
    """
    unposted = load_unposted_from_dir(data_dir)
    if not unposted:
        log.info("Tweet backlog: no unposted analyses found")
        return 0

    log.info("Tweet backlog: %d unposted analyses, will attempt up to %d", len(unposted), limit)
    posted = 0
    for result in unposted[:limit]:
        # Skip results without a real headline (same guard as try_post_analysis)
        headline = result.critic_report.headline if result.critic_report else ""
        if not headline or headline == "Analiza u toku":
            log.info("Tweet backlog: skipping %s — no real headline", result.decision.id)
            continue
        if try_post_analysis(result):
            posted += 1
            log.info("Tweet backlog: posted tweet for %s", result.decision.id)
    return posted


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

    Returns a ``BilingualTweet`` with English primary and Montenegrin reply.

    English format::

        <headline_en>

        Score: X/10

        <link>

        #AIGovernment #Montenegro

    Montenegrin reply::

        🇲🇪 <headline_me>

        Ocjena: X/10

        <link>

        #AIVlada #CrnaGora

    If *headline_me* is not provided, the English headline is used as-is for
    the Montenegrin tweet (caller should translate beforehand).
    """
    score = result.critic_report.decision_score if result.critic_report else "?"
    headline_en = result.critic_report.headline if result.critic_report else ""
    if not headline_me:
        headline_me = headline_en
    link = f"{SITE_BASE_URL}/analyses/{result.decision.id}.html"

    # --- English primary tweet ---
    en_suffix = f"\n\nScore: {score}/10\n\n{link}\n\n#AIGovernment #Montenegro"
    if headline_en:
        max_hl = MAX_TWEET_LENGTH - len(en_suffix)
        en_text = _truncate_at_word_boundary(headline_en, max_hl) + en_suffix
    else:
        en_text = f"Score: {score}/10\n\n{link}\n\n#AIGovernment #Montenegro"
    en_text = en_text[:MAX_TWEET_LENGTH]

    # --- Montenegrin thread reply ---
    me_suffix = f"\n\nOcjena: {score}/10\n\n{link}\n\n#AIVlada #CrnaGora"
    me_prefix = "\U0001f1f2\U0001f1ea "  # 🇲🇪
    if headline_me:
        max_hl = MAX_TWEET_LENGTH - len(me_suffix) - len(me_prefix)
        me_text = me_prefix + _truncate_at_word_boundary(headline_me, max_hl) + me_suffix
    else:
        me_text = f"\U0001f1f2\U0001f1ea Ocjena: {score}/10\n\n{link}\n\n#AIVlada #CrnaGora"
    me_text = me_text[:MAX_TWEET_LENGTH]

    return BilingualTweet(en=en_text, me=me_text)


def try_post_analysis(result: SessionResult) -> bool:
    """Post a bilingual tweet thread for a completed analysis.

    Posts an English primary tweet and a Montenegrin reply thread.
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

    # Skip if critic fell back to placeholder headline
    headline_en = result.critic_report.headline if result.critic_report else ""
    if not headline_en or headline_en == "Analiza u toku":
        log.warning("Skipping tweet — no real headline from critic")
        return False

    # Translate headline to Montenegrin
    headline_me = translate_headline(headline_en)

    tweets = compose_analysis_tweet(result, headline_me=headline_me)
    if not tweets.en:
        return False

    log.info("Composed analysis tweet (EN):\n%s", tweets.en)
    log.info("Composed analysis tweet (MNE):\n%s", tweets.me)

    # Post English primary
    tweet_id = post_tweet(tweets.en)
    if tweet_id is None:
        return False

    # Post Montenegrin reply in thread
    reply_id: str | None = None
    if tweets.me:
        reply_id = post_tweet(tweets.me, in_reply_to_tweet_id=tweet_id)
        if reply_id is None:
            log.warning("Failed to post Montenegrin reply — primary tweet still posted")

    now = datetime.now(UTC)
    state.last_posted_at = now
    state.posted_decision_ids.append(result.decision.id)
    state.posted_tweets.append(
        PostedTweetRecord(
            tweet_id=tweet_id,
            reply_tweet_id=reply_id,
            decision_id=result.decision.id,
            posted_at=now,
            category=result.decision.category,
        )
    )
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


# ---------------------------------------------------------------------------
# Tweet analytics / metrics collection
# ---------------------------------------------------------------------------


def _get_tweets_needing_metrics(
    state: TwitterState,
    *,
    now: datetime | None = None,
) -> list[PostedTweetRecord]:
    """Return posted tweets in the 24-48 hour age window for metrics collection."""
    now = now or datetime.now(UTC)
    results: list[PostedTweetRecord] = []
    for record in state.posted_tweets:
        age = now - record.posted_at
        if METRICS_MIN_AGE <= age <= METRICS_MAX_AGE:
            results.append(record)
    return results


def _fetch_tweet_public_metrics(tweet_ids: list[str]) -> dict[str, TweetMetrics]:
    """Fetch public_metrics for a batch of tweet IDs from the X API v2.

    Uses ``GET /2/tweets`` with ``tweet.fields=public_metrics``.
    Returns a mapping of tweet_id → TweetMetrics (only for successfully fetched tweets).
    """
    if not tweet_ids:
        return {}

    consumer_key = os.environ.get("TWITTER_CONSUMER_KEY", "")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET", "")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        log.info("X API credentials not set — skipping metrics collection")
        return {}

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        # X API v2: GET /2/tweets with tweet.fields=public_metrics
        # tweepy batches up to 100 IDs per request
        response = client.get_tweets(
            ids=tweet_ids,
            tweet_fields=["public_metrics"],
        )
        if not response.data:
            log.info("No tweet data returned from X API")
            return {}

        metrics_map: dict[str, TweetMetrics] = {}
        for tweet in response.data:
            pm = tweet.public_metrics or {}
            impressions = pm.get("impression_count", 0)
            likes = pm.get("like_count", 0)
            retweets = pm.get("retweet_count", 0)
            replies = pm.get("reply_count", 0)
            engagement = (likes + retweets + replies) / impressions if impressions > 0 else 0.0
            metrics_map[str(tweet.id)] = TweetMetrics(
                tweet_id=str(tweet.id),
                decision_id="",  # filled by caller
                impression_count=impressions,
                like_count=likes,
                retweet_count=retweets,
                reply_count=replies,
                engagement_rate=round(engagement, 6),
            )
        return metrics_map
    except Exception:
        log.exception("Failed to fetch tweet metrics from X API")
        return {}


def collect_tweet_metrics(
    *,
    metrics_path: Path = METRICS_FILE,
    state_path: Path = STATE_FILE,
) -> list[TweetMetrics]:
    """Fetch public_metrics for tweets posted 24-48 hours ago and log to JSONL.

    Returns the list of collected TweetMetrics entries.
    """
    state = load_state(state_path)
    eligible = _get_tweets_needing_metrics(state)
    if not eligible:
        log.info("No tweets in the 24-48h window for metrics collection")
        return []

    # Collect all tweet IDs (primary + reply) for batch fetch
    tweet_id_to_record: dict[str, PostedTweetRecord] = {}
    for record in eligible:
        tweet_id_to_record[record.tweet_id] = record
        if record.reply_tweet_id:
            tweet_id_to_record[record.reply_tweet_id] = record

    all_ids = list(tweet_id_to_record.keys())
    log.info("Collecting metrics for %d tweet(s) from %d analysis post(s)", len(all_ids), len(eligible))

    raw_metrics = _fetch_tweet_public_metrics(all_ids)
    if not raw_metrics:
        return []

    # Assign decision_id and write to JSONL
    results: list[TweetMetrics] = []
    for tweet_id, metrics in raw_metrics.items():
        matched_record = tweet_id_to_record.get(tweet_id)
        if matched_record is not None:
            metrics.decision_id = matched_record.decision_id
        results.append(metrics)

    # Append to JSONL
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("a", encoding="utf-8") as f:
        for m in results:
            f.write(m.model_dump_json() + "\n")

    log.info("Collected metrics for %d tweet(s)", len(results))
    return results


def load_tweet_metrics(path: Path = METRICS_FILE) -> list[TweetMetrics]:
    """Load all tweet metrics entries from the JSONL file."""
    if not path.exists():
        return []
    entries: list[TweetMetrics] = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if line:
            entries.append(TweetMetrics.model_validate_json(line))
    return entries
