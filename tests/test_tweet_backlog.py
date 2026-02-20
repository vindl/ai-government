"""Tests for tweet backlog functionality in twitter.py and main_loop.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from government.output.twitter import (
    TwitterState,
    get_unposted_results,
    load_unposted_from_dir,
    post_tweet_backlog,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))


def _make_result(decision_id: str = "dec-1", headline: str = "Test headline") -> MagicMock:
    """Create a mock SessionResult with the given decision ID and headline."""
    result = MagicMock()
    result.decision.id = decision_id
    result.decision.date = "2025-01-01"
    result.critic_report.headline = headline
    result.critic_report.decision_score = 7
    return result


def _make_result_no_critic(decision_id: str = "dec-1") -> MagicMock:
    """Create a mock SessionResult with no critic report."""
    result = MagicMock()
    result.decision.id = decision_id
    result.decision.date = "2025-01-01"
    result.critic_report = None
    return result


class TestGetUnpostedResults:
    """Tests for get_unposted_results()."""

    def test_all_unposted(self) -> None:
        results = [_make_result("a"), _make_result("b")]
        state = TwitterState()
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 2

    def test_some_already_posted(self) -> None:
        results = [_make_result("a"), _make_result("b"), _make_result("c")]
        state = TwitterState(posted_decision_ids=["a", "c"])
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 1
        assert unposted[0].decision.id == "b"

    def test_all_posted(self) -> None:
        results = [_make_result("a"), _make_result("b")]
        state = TwitterState(posted_decision_ids=["a", "b"])
        unposted = get_unposted_results(results, state)
        assert len(unposted) == 0

    def test_empty_results(self) -> None:
        state = TwitterState(posted_decision_ids=["a"])
        unposted = get_unposted_results([], state)
        assert len(unposted) == 0


class TestLoadUnpostedFromDir:
    """Tests for load_unposted_from_dir()."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        result = load_unposted_from_dir(missing)
        assert result == []

    def test_loads_and_filters(self, tmp_path: Path) -> None:
        """Mocks load_results_from_dir and twitter state to test filtering."""
        results = [_make_result("a"), _make_result("b"), _make_result("c")]
        state = TwitterState(posted_decision_ids=["b"])

        with (
            patch("government.output.site_builder.load_results_from_dir", return_value=results),
            patch("government.output.twitter.load_state", return_value=state),
        ):
            unposted = load_unposted_from_dir(tmp_path)

        assert len(unposted) == 2
        ids = [r.decision.id for r in unposted]
        assert "a" in ids
        assert "c" in ids
        assert "b" not in ids


class TestPostTweetBacklog:
    """Tests for post_tweet_backlog()."""

    def test_empty_backlog(self, tmp_path: Path) -> None:
        with patch("government.output.twitter.load_unposted_from_dir", return_value=[]):
            posted = post_tweet_backlog(tmp_path)
        assert posted == 0

    def test_posts_up_to_limit(self, tmp_path: Path) -> None:
        results = [_make_result(f"dec-{i}") for i in range(5)]
        with (
            patch("government.output.twitter.load_unposted_from_dir", return_value=results),
            patch("government.output.twitter.try_post_analysis", return_value=True),
        ):
            posted = post_tweet_backlog(tmp_path, limit=3)
        assert posted == 3

    def test_skips_placeholder_headline(self, tmp_path: Path) -> None:
        results = [_make_result("dec-1", headline="Analiza u toku")]
        with (
            patch("government.output.twitter.load_unposted_from_dir", return_value=results),
            patch("government.output.twitter.try_post_analysis", return_value=True) as mock_post,
        ):
            posted = post_tweet_backlog(tmp_path)
        assert posted == 0
        mock_post.assert_not_called()

    def test_skips_empty_headline(self, tmp_path: Path) -> None:
        results = [_make_result("dec-1", headline="")]
        with (
            patch("government.output.twitter.load_unposted_from_dir", return_value=results),
            patch("government.output.twitter.try_post_analysis", return_value=True) as mock_post,
        ):
            posted = post_tweet_backlog(tmp_path)
        assert posted == 0
        mock_post.assert_not_called()

    def test_skips_no_critic(self, tmp_path: Path) -> None:
        results = [_make_result_no_critic("dec-1")]
        with (
            patch("government.output.twitter.load_unposted_from_dir", return_value=results),
            patch("government.output.twitter.try_post_analysis", return_value=True) as mock_post,
        ):
            posted = post_tweet_backlog(tmp_path)
        assert posted == 0
        mock_post.assert_not_called()

    def test_counts_only_successful_posts(self, tmp_path: Path) -> None:
        results = [_make_result("dec-1"), _make_result("dec-2"), _make_result("dec-3")]
        # Only second one succeeds
        with (
            patch("government.output.twitter.load_unposted_from_dir", return_value=results),
            patch(
                "government.output.twitter.try_post_analysis",
                side_effect=[False, True, False],
            ),
        ):
            posted = post_tweet_backlog(tmp_path)
        assert posted == 1


class TestConductorAction:
    """Tests that post_pending_tweets is a valid conductor action."""

    def test_action_literal_includes_post_pending_tweets(self) -> None:
        from main_loop import ConductorAction

        action = ConductorAction(
            action="post_pending_tweets",
            reason="Drain tweet backlog",
        )
        assert action.action == "post_pending_tweets"

    def test_conductor_plan_accepts_post_pending_tweets(self) -> None:
        from main_loop import ConductorAction, ConductorPlan

        plan = ConductorPlan(
            reasoning="Test plan",
            actions=[
                ConductorAction(
                    action="post_pending_tweets",
                    reason="Drain tweet backlog",
                )
            ],
        )
        assert len(plan.actions) == 1
        assert plan.actions[0].action == "post_pending_tweets"
