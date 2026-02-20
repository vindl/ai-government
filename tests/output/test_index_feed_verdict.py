"""Tests for verdict badge and critic score on the index page feed."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

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
from government.output.site_builder import SiteBuilder


def _make_result(
    *,
    verdict: Verdict = Verdict.POSITIVE,
    decision_score: int = 7,
    include_debate: bool = True,
    include_critic: bool = True,
) -> SessionResult:
    """Create a SessionResult with configurable debate/critic presence."""
    decision = GovernmentDecision(
        id="feed-test-001",
        title="Feed Test Decision",
        summary="A test decision for feed rendering.",
        date=date(2026, 2, 20),
        category="test",
        title_mne="Testna odluka za feed",
        summary_mne="Opis testne odluke za feed.",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="feed-test-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Good decision.",
        reasoning="Sound reasoning.",
    )
    debate = None
    if include_debate:
        debate = ParliamentDebate(
            decision_id="feed-test-001",
            consensus_summary="Ministries agree.",
            disagreements=[],
            overall_verdict=verdict,
            debate_transcript="Debate text.",
        )
    critic = None
    if include_critic:
        critic = CriticReport(
            decision_id="feed-test-001",
            decision_score=decision_score,
            assessment_quality_score=6,
            overall_analysis="Good.",
            headline="Test Headline",
        )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
        critic_report=critic,
    )


@pytest.fixture()
def built_index(tmp_path: Path) -> str:
    """Build site and return the index.html content."""
    output_dir = tmp_path / "site"
    builder = SiteBuilder(output_dir=output_dir)
    builder.build([_make_result()])
    return (output_dir / "index.html").read_text(encoding="utf-8")


class TestIndexFeedVerdict:
    """Verdict badge appears on the index page feed."""

    def test_verdict_badge_present(self, built_index: str) -> None:
        assert "feed-verdict" in built_index

    def test_verdict_css_class_applied(self, built_index: str) -> None:
        assert "verdict-pos" in built_index

    def test_verdict_label_mne(self, built_index: str) -> None:
        assert "Pozitivno" in built_index

    def test_verdict_label_en(self, built_index: str) -> None:
        assert "Positive" in built_index


class TestIndexFeedScore:
    """Critic decision score appears on the index page feed."""

    def test_score_badge_present(self, built_index: str) -> None:
        assert "feed-score" in built_index

    def test_score_value_displayed(self, built_index: str) -> None:
        assert "7/10" in built_index

    def test_score_css_class(self, built_index: str) -> None:
        assert "feed-score-7" in built_index


class TestIndexFeedWithoutDebateOrCritic:
    """Feed items gracefully omit badges when data is missing."""

    def test_no_verdict_without_debate(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "site"
        builder = SiteBuilder(output_dir=output_dir)
        builder.build([_make_result(include_debate=False)])
        html = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "feed-verdict" not in html

    def test_no_score_without_critic(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "site"
        builder = SiteBuilder(output_dir=output_dir)
        builder.build([_make_result(include_critic=False)])
        html = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "feed-score" not in html


class TestIndexFeedVerdictVariants:
    """Different verdict values produce correct CSS classes and labels."""

    @pytest.mark.parametrize(
        ("verdict", "css_class", "label_mne"),
        [
            (Verdict.STRONGLY_POSITIVE, "verdict-strong-pos", "Izrazito pozitivno"),
            (Verdict.POSITIVE, "verdict-pos", "Pozitivno"),
            (Verdict.NEUTRAL, "verdict-neutral", "Neutralno"),
            (Verdict.NEGATIVE, "verdict-neg", "Negativno"),
            (Verdict.STRONGLY_NEGATIVE, "verdict-strong-neg", "Izrazito negativno"),
        ],
    )
    def test_verdict_variant(
        self,
        tmp_path: Path,
        verdict: Verdict,
        css_class: str,
        label_mne: str,
    ) -> None:
        output_dir = tmp_path / "site"
        builder = SiteBuilder(output_dir=output_dir)
        builder.build([_make_result(verdict=verdict)])
        html = (output_dir / "index.html").read_text(encoding="utf-8")
        assert css_class in html
        assert label_mne in html
