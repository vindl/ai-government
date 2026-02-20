"""Tests for verdict and score data in the analyses-index JSON export."""

from __future__ import annotations

import json
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
from government.output.json_export import export_json


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


def _export_and_load_index(tmp_path: Path, results: list[SessionResult]) -> list[dict]:
    """Export JSON and return the parsed analyses-index."""
    export_json(results, None, tmp_path)
    index_path = tmp_path / "analyses-index.json"
    return json.loads(index_path.read_text(encoding="utf-8"))


class TestIndexFeedVerdict:
    """Verdict data appears in analyses-index JSON."""

    def test_verdict_present(self, tmp_path: Path) -> None:
        index = _export_and_load_index(tmp_path, [_make_result()])
        assert index[0]["overall_verdict"] == "positive"

    def test_verdict_value(self, tmp_path: Path) -> None:
        index = _export_and_load_index(
            tmp_path, [_make_result(verdict=Verdict.NEGATIVE)]
        )
        assert index[0]["overall_verdict"] == "negative"


class TestIndexFeedScore:
    """Critic decision score appears in analyses-index JSON."""

    def test_score_present(self, tmp_path: Path) -> None:
        index = _export_and_load_index(tmp_path, [_make_result()])
        assert index[0]["decision_score"] == 7

    def test_score_value(self, tmp_path: Path) -> None:
        index = _export_and_load_index(
            tmp_path, [_make_result(decision_score=3)]
        )
        assert index[0]["decision_score"] == 3


class TestIndexFeedWithoutDebateOrCritic:
    """Index entries gracefully omit verdict/score when data is missing."""

    def test_no_verdict_without_debate(self, tmp_path: Path) -> None:
        index = _export_and_load_index(
            tmp_path, [_make_result(include_debate=False)]
        )
        assert index[0]["overall_verdict"] is None

    def test_no_score_without_critic(self, tmp_path: Path) -> None:
        index = _export_and_load_index(
            tmp_path, [_make_result(include_critic=False)]
        )
        assert index[0]["decision_score"] is None


class TestIndexFeedVerdictVariants:
    """Different verdict values produce correct values in JSON."""

    @pytest.mark.parametrize(
        ("verdict", "expected_value"),
        [
            (Verdict.STRONGLY_POSITIVE, "strongly_positive"),
            (Verdict.POSITIVE, "positive"),
            (Verdict.NEUTRAL, "neutral"),
            (Verdict.NEGATIVE, "negative"),
            (Verdict.STRONGLY_NEGATIVE, "strongly_negative"),
        ],
    )
    def test_verdict_variant(
        self,
        tmp_path: Path,
        verdict: Verdict,
        expected_value: str,
    ) -> None:
        index = _export_and_load_index(tmp_path, [_make_result(verdict=verdict)])
        assert index[0]["overall_verdict"] == expected_value
