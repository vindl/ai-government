"""Shared test fixtures."""

import json
from datetime import date
from pathlib import Path

import pytest

from ai_government.models.assessment import (
    Assessment,
    CriticReport,
    ParliamentDebate,
    Verdict,
)
from ai_government.models.decision import GovernmentDecision


@pytest.fixture
def sample_decision() -> GovernmentDecision:
    return GovernmentDecision(
        id="test-001",
        title="Predlog zakona o izmjenama Zakona o PDV-u",
        summary="Sniženje PDV-a na osnovne prehrambene proizvode sa 21% na 7%.",
        date=date(2025, 12, 15),
        source_url="https://www.gov.me/test",
        category="fiscal",
        tags=["PDV", "porezi"],
    )


@pytest.fixture
def sample_assessment() -> Assessment:
    return Assessment(
        ministry="Finance",
        decision_id="test-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Pozitivna mjera za životni standard, ali sa fiskalnim rizicima.",
        reasoning="Smanjenje PDV-a na osnovne proizvode direktno pomaže građanima.",
        key_concerns=["Smanjenje budžetskih prihoda", "Potreba za alternativnim izvorima"],
        recommendations=["Monitoring fiskalnog uticaja", "Evaluacija nakon 6 mjeseci"],
    )


@pytest.fixture
def sample_assessments(sample_assessment: Assessment) -> list[Assessment]:
    return [
        sample_assessment,
        Assessment(
            ministry="Justice",
            decision_id="test-001",
            verdict=Verdict.NEUTRAL,
            score=6,
            summary="Pravno usklađena mjera bez većih primjedbi.",
            reasoning="Zakon je u skladu sa ustavnim okvirom.",
            key_concerns=["Potrebna podzakonska akta"],
            recommendations=["Definisati precizno listu proizvoda"],
        ),
    ]


@pytest.fixture
def sample_debate() -> ParliamentDebate:
    return ParliamentDebate(
        decision_id="test-001",
        consensus_summary="Ministarstva se slažu da je mjera socijalno opravdana.",
        disagreements=["Fiskalni uticaj je sporan"],
        overall_verdict=Verdict.POSITIVE,
        debate_transcript="Debata o PDV-u...",
    )


@pytest.fixture
def sample_critic_report() -> CriticReport:
    return CriticReport(
        decision_id="test-001",
        decision_score=7,
        assessment_quality_score=6,
        blind_spots=["Uticaj na mala preduzeća"],
        overall_analysis="Dobra mjera sa prostorom za poboljšanje.",
        headline="PDV reforma: korak naprijed uz rizike",
    )


@pytest.fixture
def seed_decisions_path() -> Path:
    return Path(__file__).parent.parent / "data" / "seed" / "sample_decisions.json"


@pytest.fixture
def seed_decisions(seed_decisions_path: Path) -> list[GovernmentDecision]:
    with open(seed_decisions_path) as f:
        data = json.load(f)
    return [GovernmentDecision(**d) for d in data]
