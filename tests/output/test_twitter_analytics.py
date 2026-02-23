"""Tests for Twitter posting functionality."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

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
    PostedTweetRecord,
    TwitterState,
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
