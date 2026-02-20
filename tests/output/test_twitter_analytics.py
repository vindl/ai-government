"""Tests for Twitter analytics / metrics collection functionality."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from government.models.assessment import (
    Assessment,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from government.orchestrator import SessionResult
from government.output.twitter import (
    METRICS_MAX_AGE,
    METRICS_MIN_AGE,
    PostedTweetRecord,
    TweetMetrics,
    TwitterState,
    _get_tweets_needing_metrics,
    collect_tweet_metrics,
    load_tweet_metrics,
    save_state,
    try_post_analysis,
)


def _make_decision(
    id: str,
    title: str,
    day: date,
    category: str = "fiscal",
) -> GovernmentDecision:
    return GovernmentDecision(
        id=id,
        title=title,
        summary=f"Summary of {title}",
        date=day,
        category=category,
    )


def _make_result(
    id: str,
    title: str,
    day: date,
    *,
    critic_score: int = 5,
    headline: str = "",
    category: str = "fiscal",
) -> SessionResult:
    decision = _make_decision(id, title, day, category=category)
    assessment = Assessment(
        ministry="Finance",
        decision_id=id,
        verdict=Verdict.NEUTRAL,
        score=critic_score,
        summary=f"Assessment for {title}",
        reasoning="Reasoning",
    )
    critic = CriticReport(
        decision_id=id,
        decision_score=critic_score,
        assessment_quality_score=6,
        blind_spots=["Blind spot"],
        overall_analysis="Analysis",
        headline=headline or f"Headline for {title}",
    )
    debate = ParliamentDebate(
        decision_id=id,
        consensus_summary="Consensus",
        disagreements=[],
        overall_verdict=Verdict.NEUTRAL,
        debate_transcript="Transcript",
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
        critic_report=critic,
    )


class TestPostedTweetRecord:
    def test_model_roundtrip(self) -> None:
        """PostedTweetRecord serializes and deserializes correctly."""
        now = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)
        record = PostedTweetRecord(
            tweet_id="111",
            reply_tweet_id="222",
            decision_id="d1",
            posted_at=now,
            category="fiscal",
        )
        raw = record.model_dump_json()
        loaded = PostedTweetRecord.model_validate_json(raw)
        assert loaded.tweet_id == "111"
        assert loaded.reply_tweet_id == "222"
        assert loaded.decision_id == "d1"
        assert loaded.posted_at == now
        assert loaded.category == "fiscal"

    def test_optional_reply_id(self) -> None:
        """reply_tweet_id defaults to None."""
        record = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=datetime.now(UTC),
        )
        assert record.reply_tweet_id is None


class TestTweetMetrics:
    def test_model_roundtrip(self) -> None:
        """TweetMetrics serializes and deserializes correctly."""
        m = TweetMetrics(
            tweet_id="111",
            decision_id="d1",
            impression_count=1000,
            like_count=50,
            retweet_count=10,
            reply_count=5,
            engagement_rate=0.065,
        )
        raw = m.model_dump_json()
        loaded = TweetMetrics.model_validate_json(raw)
        assert loaded.tweet_id == "111"
        assert loaded.impression_count == 1000
        assert loaded.like_count == 50
        assert loaded.retweet_count == 10
        assert loaded.reply_count == 5
        assert loaded.engagement_rate == pytest.approx(0.065)

    def test_defaults(self) -> None:
        """TweetMetrics defaults to zero counts."""
        m = TweetMetrics(tweet_id="111", decision_id="d1")
        assert m.impression_count == 0
        assert m.like_count == 0
        assert m.retweet_count == 0
        assert m.reply_count == 0
        assert m.engagement_rate == 0.0


class TestTwitterStateWithPostedTweets:
    def test_state_roundtrip_with_posted_tweets(self, tmp_path: Path) -> None:
        """TwitterState with posted_tweets survives save/load cycle."""
        state_file = tmp_path / "twitter_state.json"
        now = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)
        state = TwitterState(
            last_posted_at=now,
            posted_decision_ids=["d1"],
            monthly_post_count=1,
            monthly_post_month="2026-02",
            posted_tweets=[
                PostedTweetRecord(
                    tweet_id="111",
                    reply_tweet_id="222",
                    decision_id="d1",
                    posted_at=now,
                    category="fiscal",
                )
            ],
        )
        save_state(state, state_file)

        from government.output.twitter import load_state
        loaded = load_state(state_file)
        assert len(loaded.posted_tweets) == 1
        assert loaded.posted_tweets[0].tweet_id == "111"
        assert loaded.posted_tweets[0].reply_tweet_id == "222"
        assert loaded.posted_tweets[0].decision_id == "d1"

    def test_backward_compat_no_posted_tweets(self, tmp_path: Path) -> None:
        """Old state files without posted_tweets still load fine."""
        state_file = tmp_path / "twitter_state.json"
        state_file.write_text(json.dumps({
            "last_posted_at": None,
            "posted_decision_ids": ["d1"],
            "monthly_post_count": 1,
            "monthly_post_month": "2026-02",
        }), encoding="utf-8")

        from government.output.twitter import load_state
        loaded = load_state(state_file)
        assert loaded.posted_tweets == []
        assert loaded.posted_decision_ids == ["d1"]


class TestTryPostAnalysisStoresTweetIds:
    def test_stores_tweet_ids_on_success(self) -> None:
        """try_post_analysis should store tweet IDs in posted_tweets."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.save_state") as mock_save,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.side_effect = ["12345", "67890"]
            mock_translate.return_value = "Naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=7)
            success = try_post_analysis(result)

        assert success is True
        saved_state = mock_save.call_args[0][0]
        assert len(saved_state.posted_tweets) == 1
        record = saved_state.posted_tweets[0]
        assert record.tweet_id == "12345"
        assert record.reply_tweet_id == "67890"
        assert record.decision_id == "d1"
        assert record.category == "fiscal"

    def test_stores_primary_only_when_reply_fails(self) -> None:
        """If reply fails, still stores the primary tweet ID."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.save_state") as mock_save,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.side_effect = ["12345", None]
            mock_translate.return_value = "Naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=7)
            try_post_analysis(result)

        saved_state = mock_save.call_args[0][0]
        assert len(saved_state.posted_tweets) == 1
        record = saved_state.posted_tweets[0]
        assert record.tweet_id == "12345"
        assert record.reply_tweet_id is None

    def test_no_record_when_primary_fails(self) -> None:
        """If primary tweet fails, no record is stored."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.return_value = None
            mock_translate.return_value = "Naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False


class TestGetTweetsNeedingMetrics:
    def test_returns_tweets_in_window(self) -> None:
        """Tweets 24-48h old should be eligible for metrics."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        record_30h = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=now - timedelta(hours=30),
        )
        state = TwitterState(posted_tweets=[record_30h])
        eligible = _get_tweets_needing_metrics(state, now=now)
        assert len(eligible) == 1
        assert eligible[0].tweet_id == "111"

    def test_excludes_too_recent(self) -> None:
        """Tweets < 24h old should not be eligible."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        record_12h = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=now - timedelta(hours=12),
        )
        state = TwitterState(posted_tweets=[record_12h])
        eligible = _get_tweets_needing_metrics(state, now=now)
        assert len(eligible) == 0

    def test_excludes_too_old(self) -> None:
        """Tweets > 48h old should not be eligible."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        record_72h = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=now - timedelta(hours=72),
        )
        state = TwitterState(posted_tweets=[record_72h])
        eligible = _get_tweets_needing_metrics(state, now=now)
        assert len(eligible) == 0

    def test_boundary_exactly_24h(self) -> None:
        """Tweet exactly 24h old should be eligible (inclusive)."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        record = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=now - METRICS_MIN_AGE,
        )
        state = TwitterState(posted_tweets=[record])
        eligible = _get_tweets_needing_metrics(state, now=now)
        assert len(eligible) == 1

    def test_boundary_exactly_48h(self) -> None:
        """Tweet exactly 48h old should be eligible (inclusive)."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        record = PostedTweetRecord(
            tweet_id="111",
            decision_id="d1",
            posted_at=now - METRICS_MAX_AGE,
        )
        state = TwitterState(posted_tweets=[record])
        eligible = _get_tweets_needing_metrics(state, now=now)
        assert len(eligible) == 1

    def test_empty_state(self) -> None:
        """Empty state returns no eligible tweets."""
        state = TwitterState()
        eligible = _get_tweets_needing_metrics(state)
        assert eligible == []

    def test_mixed_ages(self) -> None:
        """Only tweets in the window are returned."""
        now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC)
        records = [
            PostedTweetRecord(tweet_id="too_new", decision_id="d1",
                              posted_at=now - timedelta(hours=2)),
            PostedTweetRecord(tweet_id="eligible1", decision_id="d2",
                              posted_at=now - timedelta(hours=25)),
            PostedTweetRecord(tweet_id="eligible2", decision_id="d3",
                              posted_at=now - timedelta(hours=47)),
            PostedTweetRecord(tweet_id="too_old", decision_id="d4",
                              posted_at=now - timedelta(hours=100)),
        ]
        state = TwitterState(posted_tweets=records)
        eligible = _get_tweets_needing_metrics(state, now=now)
        ids = {r.tweet_id for r in eligible}
        assert ids == {"eligible1", "eligible2"}


class TestCollectTweetMetrics:
    def test_no_eligible_tweets(self, tmp_path: Path) -> None:
        """When no tweets are in the metrics window, returns empty list."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        state = TwitterState()
        save_state(state, state_file)

        result = collect_tweet_metrics(
            metrics_path=metrics_file,
            state_path=state_file,
        )
        assert result == []
        assert not metrics_file.exists()

    def test_collects_and_writes_metrics(self, tmp_path: Path) -> None:
        """Metrics are fetched and written to JSONL file."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        now = datetime.now(UTC)

        state = TwitterState(posted_tweets=[
            PostedTweetRecord(
                tweet_id="111",
                decision_id="d1",
                posted_at=now - timedelta(hours=30),
                category="fiscal",
            ),
        ])
        save_state(state, state_file)

        mock_tweet = MagicMock()
        mock_tweet.id = 111
        mock_tweet.public_metrics = {
            "impression_count": 500,
            "like_count": 20,
            "retweet_count": 5,
            "reply_count": 2,
        }
        mock_response = MagicMock()
        mock_response.data = [mock_tweet]

        with patch("government.output.twitter.os.environ.get") as mock_env:
            mock_env.return_value = "test_key"
            with patch("tweepy.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_tweets.return_value = mock_response
                mock_client_cls.return_value = mock_client

                result = collect_tweet_metrics(
                    metrics_path=metrics_file,
                    state_path=state_file,
                )

        assert len(result) == 1
        assert result[0].tweet_id == "111"
        assert result[0].decision_id == "d1"
        assert result[0].impression_count == 500
        assert result[0].like_count == 20
        assert result[0].retweet_count == 5
        assert result[0].reply_count == 2
        expected_engagement = (20 + 5 + 2) / 500
        assert result[0].engagement_rate == pytest.approx(expected_engagement, abs=1e-5)

        # Verify JSONL was written
        assert metrics_file.exists()
        lines = metrics_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tweet_id"] == "111"
        assert entry["impression_count"] == 500

    def test_includes_reply_tweet_ids(self, tmp_path: Path) -> None:
        """Both primary and reply tweet IDs are fetched."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        now = datetime.now(UTC)

        state = TwitterState(posted_tweets=[
            PostedTweetRecord(
                tweet_id="111",
                reply_tweet_id="222",
                decision_id="d1",
                posted_at=now - timedelta(hours=30),
            ),
        ])
        save_state(state, state_file)

        mock_tweet1 = MagicMock()
        mock_tweet1.id = 111
        mock_tweet1.public_metrics = {
            "impression_count": 500, "like_count": 20,
            "retweet_count": 5, "reply_count": 2,
        }
        mock_tweet2 = MagicMock()
        mock_tweet2.id = 222
        mock_tweet2.public_metrics = {
            "impression_count": 300, "like_count": 10,
            "retweet_count": 3, "reply_count": 1,
        }
        mock_response = MagicMock()
        mock_response.data = [mock_tweet1, mock_tweet2]

        with patch("government.output.twitter.os.environ.get") as mock_env:
            mock_env.return_value = "test_key"
            with patch("tweepy.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_tweets.return_value = mock_response
                mock_client_cls.return_value = mock_client

                result = collect_tweet_metrics(
                    metrics_path=metrics_file,
                    state_path=state_file,
                )

        assert len(result) == 2
        ids = {m.tweet_id for m in result}
        assert ids == {"111", "222"}
        # Both should have the same decision_id
        for m in result:
            assert m.decision_id == "d1"

    def test_no_credentials_returns_empty(self, tmp_path: Path) -> None:
        """Missing credentials produces empty result."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        now = datetime.now(UTC)

        state = TwitterState(posted_tweets=[
            PostedTweetRecord(
                tweet_id="111",
                decision_id="d1",
                posted_at=now - timedelta(hours=30),
            ),
        ])
        save_state(state, state_file)

        with patch.dict("os.environ", {}, clear=True):
            result = collect_tweet_metrics(
                metrics_path=metrics_file,
                state_path=state_file,
            )

        assert result == []

    def test_api_error_returns_empty(self, tmp_path: Path) -> None:
        """API errors are handled gracefully."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        now = datetime.now(UTC)

        state = TwitterState(posted_tweets=[
            PostedTweetRecord(
                tweet_id="111",
                decision_id="d1",
                posted_at=now - timedelta(hours=30),
            ),
        ])
        save_state(state, state_file)

        with patch("government.output.twitter.os.environ.get") as mock_env:
            mock_env.return_value = "test_key"
            with patch("tweepy.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_tweets.side_effect = Exception("API error")
                mock_client_cls.return_value = mock_client

                result = collect_tweet_metrics(
                    metrics_path=metrics_file,
                    state_path=state_file,
                )

        assert result == []

    def test_appends_to_existing_metrics(self, tmp_path: Path) -> None:
        """New metrics are appended to existing JSONL file."""
        state_file = tmp_path / "state.json"
        metrics_file = tmp_path / "metrics.jsonl"
        now = datetime.now(UTC)

        # Pre-existing entry
        existing = TweetMetrics(
            tweet_id="000",
            decision_id="d0",
            impression_count=100,
        )
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        metrics_file.write_text(existing.model_dump_json() + "\n", encoding="utf-8")

        state = TwitterState(posted_tweets=[
            PostedTweetRecord(
                tweet_id="111",
                decision_id="d1",
                posted_at=now - timedelta(hours=30),
            ),
        ])
        save_state(state, state_file)

        mock_tweet = MagicMock()
        mock_tweet.id = 111
        mock_tweet.public_metrics = {
            "impression_count": 500, "like_count": 20,
            "retweet_count": 5, "reply_count": 2,
        }
        mock_response = MagicMock()
        mock_response.data = [mock_tweet]

        with patch("government.output.twitter.os.environ.get") as mock_env:
            mock_env.return_value = "test_key"
            with patch("tweepy.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_tweets.return_value = mock_response
                mock_client_cls.return_value = mock_client

                collect_tweet_metrics(
                    metrics_path=metrics_file,
                    state_path=state_file,
                )

        lines = metrics_file.read_text().strip().splitlines()
        assert len(lines) == 2  # existing + new


class TestLoadTweetMetrics:
    def test_empty_file(self, tmp_path: Path) -> None:
        """Missing file returns empty list."""
        path = tmp_path / "metrics.jsonl"
        assert load_tweet_metrics(path) == []

    def test_loads_entries(self, tmp_path: Path) -> None:
        """Loads all entries from JSONL."""
        path = tmp_path / "metrics.jsonl"
        entries = [
            TweetMetrics(tweet_id="111", decision_id="d1", impression_count=100),
            TweetMetrics(tweet_id="222", decision_id="d2", impression_count=200),
        ]
        path.write_text(
            "\n".join(e.model_dump_json() for e in entries) + "\n",
            encoding="utf-8",
        )
        loaded = load_tweet_metrics(path)
        assert len(loaded) == 2
        assert loaded[0].tweet_id == "111"
        assert loaded[1].tweet_id == "222"

    def test_zero_impressions_engagement(self) -> None:
        """engagement_rate stays 0 when impressions are 0."""
        m = TweetMetrics(
            tweet_id="111",
            decision_id="d1",
            impression_count=0,
            like_count=5,
        )
        assert m.engagement_rate == 0.0
