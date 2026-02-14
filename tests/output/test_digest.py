"""Tests for daily digest building in SiteBuilder."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

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
from ai_government.output.site_builder import SiteBuilder


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
    assessment_scores: list[int] | None = None,
    has_counter_proposal: bool = False,
    concerns: list[list[str]] | None = None,
) -> SessionResult:
    decision = _make_decision(id, title, day)
    scores = assessment_scores or [critic_score]
    ministries = ["Finance", "Justice", "Health", "Education"]
    assessments = [
        Assessment(
            ministry=ministries[i % len(ministries)],
            decision_id=id,
            verdict=Verdict.POSITIVE if s >= 7 else Verdict.NEGATIVE if s <= 4 else Verdict.NEUTRAL,
            score=s,
            summary=f"Assessment {i}",
            reasoning="Reasoning",
            key_concerns=concerns[i] if concerns and i < len(concerns) else ["Concern A"],
            recommendations=["Rec"],
        )
        for i, s in enumerate(scores)
    ]
    critic = CriticReport(
        decision_id=id,
        decision_score=critic_score,
        assessment_quality_score=6,
        blind_spots=["Blind spot"],
        overall_analysis="Analysis",
        headline=f"Headline for {title}",
    )
    debate = ParliamentDebate(
        decision_id=id,
        consensus_summary="Consensus",
        disagreements=["Disagreement"],
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
        assessments=assessments,
        debate=debate,
        critic_report=critic,
        counter_proposal=counter_proposal,
    )


DAY1 = date(2026, 2, 14)
DAY2 = date(2026, 2, 15)


@pytest.fixture()
def day1_results() -> list[SessionResult]:
    return [
        _make_result("d1", "Budget Law", DAY1, critic_score=4, assessment_scores=[3, 5]),
        _make_result(
            "d2",
            "Education Reform",
            DAY1,
            critic_score=8,
            has_counter_proposal=True,
            assessment_scores=[7, 8],
        ),
    ]


@pytest.fixture()
def day2_results() -> list[SessionResult]:
    return [
        _make_result("d3", "Health Policy", DAY2, critic_score=6, assessment_scores=[5, 6]),
    ]


@pytest.fixture()
def all_results(
    day1_results: list[SessionResult],
    day2_results: list[SessionResult],
) -> list[SessionResult]:
    return day1_results + day2_results


class TestGroupResultsByDate:
    def test_groups_correctly(self, all_results: list[SessionResult]) -> None:
        grouped = SiteBuilder._group_results_by_date(all_results)
        assert set(grouped.keys()) == {DAY1, DAY2}
        assert len(grouped[DAY1]) == 2
        assert len(grouped[DAY2]) == 1

    def test_empty_input(self) -> None:
        grouped = SiteBuilder._group_results_by_date([])
        assert grouped == {}

    def test_single_date(self, day1_results: list[SessionResult]) -> None:
        grouped = SiteBuilder._group_results_by_date(day1_results)
        assert list(grouped.keys()) == [DAY1]
        assert len(grouped[DAY1]) == 2


class TestComposeDigestData:
    def test_basic_fields(self, day1_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        assert data["date"] == DAY1
        assert data["decision_count"] == 2
        assert len(data["decisions"]) == 2

    def test_avg_score(self, day1_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        # Critic scores: 4 and 8 → avg 6.0
        assert data["avg_score"] == 6.0

    def test_decisions_sorted_by_score_ascending(
        self, day1_results: list[SessionResult]
    ) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        scores = [d["score"] for d in data["decisions"]]
        assert scores == sorted(scores)

    def test_lowest_and_highest(self, day1_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        assert data["lowest_score_decision"]["score"] == 4
        # Highest score is 8 (>= 7), so it should be set
        assert data["highest_score_decision"] is not None
        assert data["highest_score_decision"]["score"] == 8

    def test_highest_none_when_below_7(self, day2_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY2, day2_results)
        # Only score is 6, below threshold
        assert data["highest_score_decision"] is None

    def test_counter_proposal_count(self, day1_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        assert data["counter_proposal_count"] == 1

    def test_common_concerns(self) -> None:
        results = [
            _make_result(
                "x1",
                "X",
                DAY1,
                assessment_scores=[5, 5],
                concerns=[["Korupcija", "Transparentnost"], ["Korupcija", "Budžet"]],
            ),
        ]
        data = SiteBuilder._compose_digest_data(DAY1, results)
        # "Korupcija" appears twice, others once
        assert data["common_concerns"][0] == "Korupcija"

    def test_verdict_distribution(self, day1_results: list[SessionResult]) -> None:
        data = SiteBuilder._compose_digest_data(DAY1, day1_results)
        assert isinstance(data["verdict_distribution"], dict)
        total = sum(data["verdict_distribution"].values())
        # 2 results × 2 assessments each = 4 total
        assert total == 4

    def test_fallback_without_critic_report(self) -> None:
        decision = _make_decision("nc", "No Critic", DAY1)
        assessment = Assessment(
            ministry="Finance",
            decision_id="nc",
            verdict=Verdict.NEUTRAL,
            score=6,
            summary="Summary",
            reasoning="Reasoning",
        )
        result = SessionResult(decision=decision, assessments=[assessment])
        data = SiteBuilder._compose_digest_data(DAY1, [result])
        # Falls back to average assessment score
        assert data["decisions"][0]["score"] == 6
        assert data["decisions"][0]["headline"] == decision.summary


class TestBuildDigests:
    def test_creates_digest_pages(
        self, tmp_path: Path, all_results: list[SessionResult]
    ) -> None:
        builder = SiteBuilder(tmp_path)
        builder._build_digests(all_results)

        assert (tmp_path / "pregled" / "index.html").exists()
        assert (tmp_path / "pregled" / str(DAY1) / "index.html").exists()
        assert (tmp_path / "pregled" / str(DAY2) / "index.html").exists()

    def test_digest_content(
        self, tmp_path: Path, day1_results: list[SessionResult]
    ) -> None:
        builder = SiteBuilder(tmp_path)
        builder._build_digests(day1_results)

        html = (tmp_path / "pregled" / str(DAY1) / "index.html").read_text()
        assert "Budget Law" in html
        assert "Education Reform" in html

    def test_index_content(
        self, tmp_path: Path, all_results: list[SessionResult]
    ) -> None:
        builder = SiteBuilder(tmp_path)
        builder._build_digests(all_results)

        html = (tmp_path / "pregled" / "index.html").read_text()
        assert str(DAY1) in html
        assert str(DAY2) in html

    def test_empty_results(self, tmp_path: Path) -> None:
        builder = SiteBuilder(tmp_path)
        builder._build_digests([])
        # Index page should still be created (shows empty state)
        assert (tmp_path / "pregled" / "index.html").exists()
        html = (tmp_path / "pregled" / "index.html").read_text()
        assert "Nema dnevnih pregleda" in html
