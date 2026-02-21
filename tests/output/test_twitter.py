"""Tests for X (Twitter) posting functionality."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import call, patch

if TYPE_CHECKING:
    from pathlib import Path

from government.models.assessment import (
    Assessment,
    CounterProposal,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from government.orchestrator import SessionResult
from government.output.twitter import (
    MAX_TWEET_LENGTH,
    MONTHLY_POST_LIMIT,
    BilingualTweet,
    TwitterState,
    _current_month,
    _truncate_at_word_boundary,
    compose_analysis_tweet,
    get_unposted_results,
    load_state,
    record_post,
    save_state,
    translate_headline,
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


class TestTranslateHeadline:
    def test_empty_headline(self) -> None:
        """Empty headline should be returned as-is."""
        assert translate_headline("") == ""

    def test_successful_translation(self) -> None:
        """Successful translation returns translated text."""
        with patch("government.output.twitter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "Prevedeni naslov\n"
            mock_run.return_value.returncode = 0
            result = translate_headline("Translated headline")
        assert result == "Prevedeni naslov"

    def test_failed_translation_falls_back(self) -> None:
        """Failed translation returns the original English headline."""
        with patch("government.output.twitter.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("claude not found")
            result = translate_headline("Original headline")
        assert result == "Original headline"

    def test_empty_output_falls_back(self) -> None:
        """Empty translation output returns the original headline."""
        with patch("government.output.twitter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 0
            result = translate_headline("Original headline")
        assert result == "Original headline"

    def test_nonzero_returncode_falls_back(self) -> None:
        """Non-zero return code falls back to original headline."""
        with patch("government.output.twitter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "something"
            mock_run.return_value.returncode = 1
            result = translate_headline("Original headline")
        assert result == "Original headline"


class TestComposeAnalysisTweet:
    def test_returns_bilingual_tweet(self) -> None:
        """compose_analysis_tweet should return a BilingualTweet."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert isinstance(tweets, BilingualTweet)
        assert isinstance(tweets.me, str)
        assert isinstance(tweets.en, str)

    def test_me_tweet_has_montenegrin_hashtags(self) -> None:
        """Montenegrin tweet should use #AIVlada #CrnaGora."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "#AIVlada" in tweets.me
        assert "#CrnaGora" in tweets.me
        assert "#AIGovernment" not in tweets.me

    def test_en_tweet_has_english_hashtags(self) -> None:
        """English reply should use #AIGovernment #Montenegro."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "#AIGovernment" in tweets.en
        assert "#Montenegro" in tweets.en
        assert "#AIVlada" not in tweets.en

    def test_me_tweet_uses_ocjena(self) -> None:
        """Montenegrin tweet should use 'Ocjena' instead of 'Score'."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "Ocjena: 7/10" in tweets.me
        assert "Score:" not in tweets.me

    def test_en_tweet_uses_score(self) -> None:
        """English reply should use 'Score'."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "Score: 7/10" in tweets.en

    def test_me_tweet_has_flag_prefix(self) -> None:
        """Montenegrin reply should start with a flag emoji."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert tweets.me.startswith("\U0001f1f2\U0001f1ea")

    def test_en_tweet_leads_with_headline(self) -> None:
        """English primary tweet should start with the headline."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy for Montenegro",
        )
        tweets = compose_analysis_tweet(result)
        assert tweets.en.startswith("Strong fiscal policy for Montenegro")

    def test_no_official_title(self) -> None:
        """Official decision title should NOT appear in either tweet."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "Budget Law" not in tweets.me
        assert "Budget Law" not in tweets.en

    def test_no_counter_proposal_tag(self) -> None:
        """Counter-proposal tag should NOT appear in analysis tweets."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=5, has_counter_proposal=True,
        )
        tweets = compose_analysis_tweet(result)
        assert "[+counter-proposal]" not in tweets.me
        assert "[+counter-proposal]" not in tweets.en

    def test_both_tweets_contain_link(self) -> None:
        """Both tweets should contain the decision link."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert "/analyses/d1" in tweets.me
        assert "/analyses/d1" in tweets.en

    def test_both_tweets_fit_280_chars(self) -> None:
        """Both tweets must independently fit within 280 characters."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Strong fiscal policy",
        )
        tweets = compose_analysis_tweet(result)
        assert len(tweets.me) <= MAX_TWEET_LENGTH
        assert len(tweets.en) <= MAX_TWEET_LENGTH

    def test_truncates_long_headline_at_word_boundary(self) -> None:
        """Long headlines are truncated at a word boundary in both tweets."""
        long_headline = (
            "Montenegro's Parliament Rubber-Stamps 25 Laws in One Day "
            "Raising Serious Questions About Democratic Oversight and "
            "EU Integration Progress Amid Growing Concerns From Civil "
            "Society Organizations and Opposition Parties Who Demand "
            "More Transparent Legislative Processes"
        )
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=5, headline=long_headline,
        )
        tweets = compose_analysis_tweet(result)
        assert len(tweets.me) <= MAX_TWEET_LENGTH
        assert len(tweets.en) <= MAX_TWEET_LENGTH
        # Should use ellipsis character for truncation in both
        assert "\u2026" in tweets.me
        assert "\u2026" in tweets.en

    def test_no_headline(self) -> None:
        """Tweet without headline should still have score and link."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="",
        )
        tweets = compose_analysis_tweet(result)
        assert "Ocjena: 7/10" in tweets.me
        assert "Score: 7/10" in tweets.en
        assert "/analyses/d1" in tweets.me
        assert "/analyses/d1" in tweets.en
        assert len(tweets.me) <= MAX_TWEET_LENGTH
        assert len(tweets.en) <= MAX_TWEET_LENGTH

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
        tweets = compose_analysis_tweet(result)
        assert "Ocjena: ?/10" in tweets.me
        assert "Score: ?/10" in tweets.en
        assert len(tweets.me) <= MAX_TWEET_LENGTH
        assert len(tweets.en) <= MAX_TWEET_LENGTH

    def test_headline_me_used_for_montenegrin(self) -> None:
        """When headline_me is provided, it should be used for the MNE tweet."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="English headline",
        )
        tweets = compose_analysis_tweet(
            result, headline_me="Crnogorski naslov",
        )
        assert "Crnogorski naslov" in tweets.me
        assert "English headline" not in tweets.me
        assert "English headline" in tweets.en

    def test_fallback_headline_when_no_me(self) -> None:
        """When no headline_me, English headline is used for both."""
        result = _make_result(
            "d1", "Budget Law", date(2026, 2, 14),
            critic_score=7, headline="Shared headline",
        )
        tweets = compose_analysis_tweet(result)
        assert "Shared headline" in tweets.me
        assert "Shared headline" in tweets.en


class TestTryPostAnalysis:
    def test_successful_post_creates_thread(self) -> None:
        """try_post_analysis should post EN primary and MNE reply."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.save_state") as mock_save,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.side_effect = ["12345", "67890"]
            mock_translate.return_value = "Prevedeni naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=7)
            success = try_post_analysis(result)

        assert success is True
        # Should post twice: primary MNE + EN reply
        assert mock_post.call_count == 2
        # Second call should be a reply to the first tweet
        second_call = mock_post.call_args_list[1]
        assert second_call == call(
            mock_post.call_args_list[1][0][0],
            in_reply_to_tweet_id="12345",
        )
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][0]
        assert "d1" in saved_state.posted_decision_ids
        assert saved_state.last_posted_at is not None
        assert saved_state.monthly_post_count == 1

    def test_already_posted(self) -> None:
        """Test try_post_analysis skips already-posted decision."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.post_tweet") as mock_post,
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
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.post_tweet") as mock_post,
        ):
            mock_load.return_value = TwitterState(
                monthly_post_month=current,
                monthly_post_count=MONTHLY_POST_LIMIT,
            )
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False
        mock_post.assert_not_called()

    def test_primary_post_fails(self) -> None:
        """Test try_post_analysis handles primary tweet failure."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.return_value = None  # Failure
            mock_translate.return_value = "Naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14))
            success = try_post_analysis(result)

        assert success is False
        mock_post.assert_called_once()

    def test_reply_failure_still_succeeds(self) -> None:
        """If the MNE reply fails, the post is still considered successful."""
        with (
            patch("government.output.twitter.load_state") as mock_load,
            patch("government.output.twitter.save_state") as mock_save,
            patch("government.output.twitter.post_tweet") as mock_post,
            patch("government.output.twitter.translate_headline") as mock_translate,
        ):
            mock_load.return_value = TwitterState()
            mock_post.side_effect = ["12345", None]  # Primary OK, reply fails
            mock_translate.return_value = "Naslov"
            result = _make_result("d1", "Budget Law", date(2026, 2, 14), critic_score=7)
            success = try_post_analysis(result)

        assert success is True
        assert mock_post.call_count == 2
        mock_save.assert_called_once()

    def test_counts_as_single_post(self) -> None:
        """Both tweets should count as a single post toward monthly limit."""
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
            try_post_analysis(result)

        saved_state = mock_save.call_args[0][0]
        assert saved_state.monthly_post_count == 1  # Not 2


