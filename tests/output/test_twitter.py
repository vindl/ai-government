"""Tests for X (Twitter) posting functionality."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

from ai_government.models.assessment import (
    Assessment,
    CounterProposal,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from ai_government.models.decision import GovernmentDecision
from ai_government.orchestrator import SessionResult
from ai_government.output.twitter import (
    MAX_TWEET_LENGTH,
    MONTHLY_POST_LIMIT,
    TwitterState,
    _current_month,
    _truncate_at_word_boundary,
    compose_analysis_tweet,
    compose_daily_tweet,
    get_unposted_results,
    load_state,
    record_post,
    save_state,
    should_post,
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
    has_counter_proposal: bool = False,
) -> SessionResult:
    decision = _make_decision(id, title, day)
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
    counter_proposal = (
        CounterProposal(
            decision_id=id,
            title="Counter",
            executive_summary="Alt approach",
            detailed_proposal="Details",
        )
        if has_counter_proposal
        else None
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
        critic_report=critic,
        counter_proposal=counter_proposal,
    )


class TestTwitterState:
    def test_state_roundtrip(self, tmp_path: Path) -> None:
        """Test saving and loading state."""
        state_file = tmp_path / "twitter_state.json"
        state = TwitterState(
            last_posted_at=datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC),
            posted_decision_ids=["d1", "d2"],
            monthly_post_count=5,
            monthly_post_month="2026-02",
        )
        save_state(state, state_file)

        loaded = load_state(state_file)
        assert loaded.last_posted_at == state.last_posted_at
        assert loaded.posted_decision_ids == state.posted_decision_ids
        assert loaded.monthly_post_count == 5
        assert loaded.monthly_post_month == "2026-02"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Test loading when file doesn't exist."""
        state_file = tmp_path / "missing.json"
        state = load_state(state_file)
        assert state.last_posted_at is None
        assert state.posted_decision_ids == []
        assert state.monthly_post_count == 0
        assert state.monthly_post_month == ""

    def test_load_corrupt_file(self, tmp_path: Path) -> None:
        """Test loading when file is corrupt."""
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("invalid json{", encoding="utf-8")
        state = load_state(state_file)
        # Should return fresh state
        assert state.last_posted_at is None
        assert state.posted_decision_ids == []


class TestCurrentMonth:
    def test_format(self) -> None:
        """Test _current_month returns YYYY-MM format."""
        result = _current_month()
        assert len(result) == 7  # "YYYY-MM"
        assert result[4] == "-"


class TestShouldPost:
    def test_first_post(self) -> None:
        """Test should_post returns True for first post."""
        state = TwitterState()
        assert should_post(state) is True

    def test_cooldown_not_elapsed(self) -> None:
        """Test should_post returns False during cooldown."""
        state = TwitterState(
            last_posted_at=datetime.now(UTC) - timedelta(hours=12)
        )
        assert should_post(state, cooldown_hours=24) is False

    def test_cooldown_elapsed(self) -> None:
        """Test should_post returns True after cooldown."""
        state = TwitterState(
            last_posted_at=datetime.now(UTC) - timedelta(hours=25)
        )
        assert should_post(state, cooldown_hours=24) is True

    def test_monthly_limit_not_reached(self) -> None:
        """Test should_post returns True when under monthly limit."""
        current = _current_month()
        state = TwitterState(
            monthly_post_month=current,
            monthly_post_count=MONTHLY_POST_LIMIT - 1,
        )
        assert should_post(state, cooldown_hours=0) is True

    def test_monthly_limit_reached(self) -> None:
        """Test should_post returns False when monthly limit reached."""
        current = _current_month()
        state = TwitterState(
            monthly_post_month=current,
            monthly_post_count=MONTHLY_POST_LIMIT,
        )
        assert should_post(state, cooldown_hours=0) is False

    def test_monthly_limit_reset_new_month(self) -> None:
        """Test should_post returns True when new month resets limit."""
        state = TwitterState(
            monthly_post_month="2026-01",  # Old month
            monthly_post_count=MONTHLY_POST_LIMIT,  # At limit
        )
        # Current month is different, so limit should not apply
        assert should_post(state, cooldown_hours=0) is True


class TestRecordPost:
    def test_first_post(self) -> None:
        """Test record_post initializes counter on first post."""
        state = TwitterState()
        record_post(state)
        assert state.monthly_post_count == 1
        assert state.monthly_post_month == _current_month()

    def test_increment_same_month(self) -> None:
        """Test record_post increments counter in same month."""
        current = _current_month()
        state = TwitterState(
            monthly_post_month=current,
            monthly_post_count=5,
        )
        record_post(state)
        assert state.monthly_post_count == 6
        assert state.monthly_post_month == current

    def test_reset_new_month(self) -> None:
        """Test record_post resets counter for new month."""
        state = TwitterState(
            monthly_post_month="2026-01",  # Old month
            monthly_post_count=50,
        )
        record_post(state)
        assert state.monthly_post_count == 1  # Reset and incremented
        assert state.monthly_post_month == _current_month()


class TestGetUnpostedResults:
    def test_filters_posted(self) -> None:
        """Test get_unposted_results filters out posted decisions."""
        results = [
            _make_result("d1", "Decision 1", date(2026, 2, 14)),
            _make_result("d2", "Decision 2", date(2026, 2, 14)),
            _make_result("d3", "Decision 3", date(2026, 2, 14)),
        ]
        state = TwitterState(posted_decision_ids=["d1", "d3"])
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 1
        assert unposted[0].decision.id == "d2"

    def test_all_posted(self) -> None:
        """Test get_unposted_results with all posted."""
        results = [_make_result("d1", "Decision 1", date(2026, 2, 14))]
        state = TwitterState(posted_decision_ids=["d1"])
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 0

    def test_none_posted(self) -> None:
        """Test get_unposted_results with none posted."""
        results = [
            _make_result("d1", "Decision 1", date(2026, 2, 14)),
            _make_result("d2", "Decision 2", date(2026, 2, 14)),
        ]
        state = TwitterState()
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 2


class TestTruncateAtWordBoundary:
    def test_short_text_unchanged(self) -> None:
        """Text within limit is returned as-is."""
        assert _truncate_at_word_boundary("hello world", 50) == "hello world"

    def test_truncates_at_word_boundary(self) -> None:
        """Long text is cut at a space, not mid-word."""
        result = _truncate_at_word_boundary("one two three four five", 15)
        assert result.endswith("\u2026")
        assert len(result) <= 15
        # Should not cut inside a word
        without_ellipsis = result[:-1]
        assert without_ellipsis == without_ellipsis.rstrip()
        assert " " not in result or result.index("\u2026") > result.rfind(" ")

    def test_exact_limit(self) -> None:
        """Text exactly at limit is returned as-is."""
        text = "abcde"
        assert _truncate_at_word_boundary(text, 5) == text

    def test_single_long_word(self) -> None:
        """A single word longer than the limit still gets truncated."""
        result = _truncate_at_word_boundary("superlongword", 8)
        assert len(result) <= 8
        assert result.endswith("\u2026")


class TestComposeAnalysisTweet:
    def test_leads_with_headline(self) -> None:
        """Tweet should start with the headline, not the title."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=7,
            headline="Strong fiscal policy for Montenegro",
        )
        tweet = compose_analysis_tweet(result)
        assert tweet.startswith("Strong fiscal policy for Montenegro")

    def test_no_official_title(self) -> None:
        """Official decision title should NOT appear in the tweet."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=7,
            headline="Strong fiscal policy",
        )
        tweet = compose_analysis_tweet(result)
        assert "Budget Law" not in tweet

    def test_no_counter_proposal_tag(self) -> None:
        """Counter-proposal tag should NOT appear in analysis tweets."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=5,
            has_counter_proposal=True,
        )
        tweet = compose_analysis_tweet(result)
        assert "[+counter-proposal]" not in tweet

    def test_score_format(self) -> None:
        """Score should be formatted as 'Score: X/10'."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=7,
            headline="Strong fiscal policy",
        )
        tweet = compose_analysis_tweet(result)
        assert "Score: 7/10" in tweet

    def test_contains_link_and_hashtags(self) -> None:
        """Tweet should contain the decision link and hashtags."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=7,
            headline="Strong fiscal policy",
        )
        tweet = compose_analysis_tweet(result)
        assert "/decisions/d1.html" in tweet
        assert "#AIGovernment" in tweet
        assert "#Montenegro" in tweet
        assert len(tweet) <= MAX_TWEET_LENGTH

    def test_truncates_long_headline_at_word_boundary(self) -> None:
        """Long headlines are truncated at a word boundary, not mid-word."""
        long_headline = (
            "Montenegro's Parliament Rubber-Stamps 25 Laws in One Day "
            "Raising Serious Questions About Democratic Oversight and "
            "EU Integration Progress Amid Growing Concerns From Civil "
            "Society Organizations and Opposition Parties Who Demand "
            "More Transparent Legislative Processes"
        )
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=5,
            headline=long_headline,
        )
        tweet = compose_analysis_tweet(result)
        assert len(tweet) <= MAX_TWEET_LENGTH
        # Should use ellipsis character for truncation
        assert "\u2026" in tweet
        # Ellipsis should not appear mid-word — the char before it should be
        # a letter or punctuation, and it should be preceded by a space-delimited word
        ellipsis_pos = tweet.index("\u2026")
        before_ellipsis = tweet[:ellipsis_pos].rstrip()
        assert before_ellipsis[-1] != " "

    def test_no_headline(self) -> None:
        """Tweet without headline should still have score and link."""
        result = _make_result(
            "d1",
            "Budget Law",
            date(2026, 2, 14),
            critic_score=7,
            headline="",
        )
        tweet = compose_analysis_tweet(result)
        assert "Score: 7/10" in tweet
        assert "/decisions/d1.html" in tweet
        assert len(tweet) <= MAX_TWEET_LENGTH

    def test_no_critic_report(self) -> None:
        """Tweet without critic report should show '?' score."""
        decision = _make_decision("d1", "Budget Law", date(2026, 2, 14))
        assessment = Assessment(
            ministry="Finance",
            decision_id="d1",
            verdict=Verdict.NEUTRAL,
            score=5,
            summary="Summary",
            reasoning="Reasoning",
        )
        result = SessionResult(decision=decision, assessments=[assessment])
        tweet = compose_analysis_tweet(result)
        assert "Score: ?/10" in tweet
        assert len(tweet) <= MAX_TWEET_LENGTH


class TestTryPostAnalysis:
    def test_successful_post(self) -> None:
        """Test try_post_analysis successful post."""
        with (
            patch("ai_government.output.twitter.load_state") as mock_load,
            patch("ai_government.output.twitter.save_state") as mock_save,
            patch("ai_government.output.twitter.post_tweet") as mock_post,
        ):
            mock_load.return_value = TwitterState()
            mock_post.return_value = "12345"  # Tweet ID
            result = _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=7)
            success = try_post_analysis(result)

        assert success is True
        mock_post.assert_called_once()
        mock_save.assert_called_once()
        # Check the state that was saved
        saved_state = mock_save.call_args[0][0]
        assert "d1" in saved_state.posted_decision_ids
        assert saved_state.last_posted_at is not None
        assert saved_state.monthly_post_count == 1

    def test_already_posted(self) -> None:
        """Test try_post_analysis skips already-posted decision."""
        with (
            patch("ai_government.output.twitter.load_state") as mock_load,
            patch("ai_government.output.twitter.post_tweet") as mock_post,
        ):
            mock_load.return_value = TwitterState(posted_decision_ids=["d1"])
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False
        mock_post.assert_not_called()

    def test_monthly_limit_reached(self) -> None:
        """Test try_post_analysis respects monthly limit."""
        current = _current_month()
        with (
            patch("ai_government.output.twitter.load_state") as mock_load,
            patch("ai_government.output.twitter.post_tweet") as mock_post,
        ):
            mock_load.return_value = TwitterState(
                monthly_post_month=current,
                monthly_post_count=MONTHLY_POST_LIMIT,
            )
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False
        mock_post.assert_not_called()

    def test_post_tweet_fails(self) -> None:
        """Test try_post_analysis handles post_tweet failure."""
        with (
            patch("ai_government.output.twitter.load_state") as mock_load,
            patch("ai_government.output.twitter.post_tweet") as mock_post,
        ):
            mock_load.return_value = TwitterState()
            mock_post.return_value = None  # Failure
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False
        mock_post.assert_called_once()


class TestComposeDailyTweet:
    def test_basic_digest(self) -> None:
        """Test compose_daily_tweet basic format."""
        results = [
            _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=4),
            _make_result("d2", "Education Reform", date(2026, 2, 14), critic_score=8),
        ]
        tweet = compose_daily_tweet(results)
        assert "AI Government — daily digest" in tweet
        assert "Budget Law: 4/10" in tweet
        assert "Education Reform: 8/10" in tweet
        assert "#AIGovernment" in tweet
        assert len(tweet) <= MAX_TWEET_LENGTH

    def test_sorts_by_score_ascending(self) -> None:
        """Test compose_daily_tweet sorts by score (lowest first)."""
        results = [
            _make_result("d1", "High Score", date(2026, 2, 14), critic_score=8),
            _make_result("d2", "Low Score", date(2026, 2, 14), critic_score=3),
            _make_result("d3", "Mid Score", date(2026, 2, 14), critic_score=5),
        ]
        tweet = compose_daily_tweet(results)
        # Low score should appear first
        low_pos = tweet.find("Low Score")
        mid_pos = tweet.find("Mid Score")
        high_pos = tweet.find("High Score")
        assert low_pos < mid_pos < high_pos

    def test_max_three_results(self) -> None:
        """Test compose_daily_tweet limits to 3 results."""
        results = [
            _make_result(f"d{i}", f"Decision {i}", date(2026, 2, 14), critic_score=i)
            for i in range(1, 6)
        ]
        tweet = compose_daily_tweet(results)
        # Should only contain first 3 (lowest scores: 1, 2, 3)
        assert "Decision 1" in tweet
        assert "Decision 2" in tweet
        assert "Decision 3" in tweet
        assert "Decision 4" not in tweet
        assert "Decision 5" not in tweet

    def test_empty_results(self) -> None:
        """Test compose_daily_tweet with empty results."""
        tweet = compose_daily_tweet([])
        assert tweet == ""

    def test_counter_proposal_tag(self) -> None:
        """Test compose_daily_tweet includes counter-proposal tag."""
        results = [
            _make_result(
                "d1",
                "Budget Law",
                date(2026, 2, 14),
                critic_score=5,
                has_counter_proposal=True,
            ),
        ]
        tweet = compose_daily_tweet(results)
        assert "[+counter-proposal]" in tweet
