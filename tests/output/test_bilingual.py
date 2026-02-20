"""Tests for bilingual (MNE/EN) data in models and JSON export."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from government.models.assessment import (
    Assessment,
    CounterProposal,
    CriticReport,
    MinistryCounterProposal,
    ParliamentDebate,
    Verdict,
)
from government.models.decision import GovernmentDecision
from government.orchestrator import SessionResult
from government.output.html import _ministry_name_mne, _verdict_label_mne
from government.output.json_export import export_json
from government.output.localization import has_montenegrin_content


def _make_bilingual_result() -> SessionResult:
    """Create a SessionResult with both EN and MNE content populated."""
    decision = GovernmentDecision(
        id="bi-001",
        title="Predlog zakona o zaštiti životne sredine",
        summary="Zakon o zaštiti životne sredine sa novim standardima.",
        date=date(2026, 2, 15),
        category="environment",
        title_mne="Predlog zakona o zaštiti životne sredine",
        summary_mne="Zakon o zaštiti životne sredine sa novim standardima.",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="bi-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="A positive step for environmental protection with fiscal implications.",
        reasoning="The law introduces new standards.",
        key_concerns=["Budget impact", "Implementation timeline"],
        recommendations=["Monitor fiscal impact", "Evaluate after 6 months"],
        executive_summary="Positive measure with fiscal risks.",
        summary_mne="Pozitivan korak za zaštitu životne sredine sa fiskalnim implikacijama.",
        executive_summary_mne="Pozitivna mjera sa fiskalnim rizicima.",
        key_concerns_mne=["Uticaj na budžet", "Rokovi implementacije"],
        recommendations_mne=["Praćenje fiskalnog uticaja", "Evaluacija nakon 6 mjeseci"],
        counter_proposal=MinistryCounterProposal(
            title="Phased Implementation",
            summary="Gradual rollout over 3 phases.",
            key_changes=["Phase 1: standards", "Phase 2: enforcement"],
            expected_benefits=["Less disruption", "Better compliance"],
            estimated_feasibility="High — builds on existing framework",
            title_mne="Fazna implementacija",
            summary_mne="Postepeno uvođenje u 3 faze.",
            key_changes_mne=["Faza 1: standardi", "Faza 2: sprovođenje"],
            expected_benefits_mne=["Manje poremećaja", "Bolja usklađenost"],
            estimated_feasibility_mne="Visoka — nadograđuje postojeći okvir",
        ),
    )
    critic = CriticReport(
        decision_id="bi-001",
        decision_score=7,
        assessment_quality_score=6,
        blind_spots=["Impact on small businesses"],
        overall_analysis="Good measure with room for improvement.",
        headline="Environment Law: Forward Step with Risks",
        headline_mne="Zakon o životnoj sredini: korak naprijed uz rizike",
        overall_analysis_mne="Dobra mjera sa prostorom za poboljšanje.",
        blind_spots_mne=["Uticaj na mala preduzeća"],
    )
    debate = ParliamentDebate(
        decision_id="bi-001",
        consensus_summary="Ministries agree the measure is socially justified.",
        disagreements=["Fiscal impact is disputed"],
        overall_verdict=Verdict.POSITIVE,
        debate_transcript="Debate transcript...",
        consensus_summary_mne="Ministarstva se slažu da je mjera socijalno opravdana.",
        disagreements_mne=["Fiskalni uticaj je sporan"],
    )
    counter_proposal = CounterProposal(
        decision_id="bi-001",
        title="Progressive Environmental Reform",
        executive_summary="A gradual approach to environmental standards.",
        detailed_proposal="The proposed approach combines fiscal prudence with protection.",
        ministry_contributions=["Finance: fiscal impact analysis", "Health: public health assessment"],
        key_differences=["Gradual instead of immediate"],
        implementation_steps=["Adopt framework", "Phase 1"],
        risks_and_tradeoffs=["Slower environmental impact"],
        title_mne="Progresivna reforma životne sredine",
        executive_summary_mne="Postepeni pristup standardima zaštite životne sredine.",
        detailed_proposal_mne="Predloženi pristup kombinuje fiskalnu opreznost sa zaštitom.",
        ministry_contributions_mne=[
            "Finansije: analiza fiskalnog uticaja",
            "Zdravlje: procjena javnog zdravlja",
        ],
        key_differences_mne=["Postepeno umjesto trenutnog"],
        implementation_steps_mne=["Usvojiti okvir", "Faza 1"],
        risks_and_tradeoffs_mne=["Sporiji uticaj na životnu sredinu"],
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
        critic_report=critic,
        counter_proposal=counter_proposal,
    )


def _make_english_only_result() -> SessionResult:
    """Create a SessionResult with only English content (no MNE translations)."""
    decision = GovernmentDecision(
        id="en-001",
        title="Budget Amendment",
        summary="Amendment to the annual budget.",
        date=date(2026, 2, 14),
        category="fiscal",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="en-001",
        verdict=Verdict.NEUTRAL,
        score=5,
        summary="Neutral assessment of budget changes.",
        reasoning="Standard budget procedure.",
    )
    critic = CriticReport(
        decision_id="en-001",
        decision_score=5,
        assessment_quality_score=5,
        overall_analysis="Standard budget amendment.",
        headline="Budget Change: Business as Usual",
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        critic_report=critic,
    )


class TestVerdictLabelMne:
    def test_all_verdicts_have_mne_labels(self) -> None:
        for verdict in Verdict:
            label = _verdict_label_mne(verdict.value)
            assert label != verdict.value, f"Missing MNE label for {verdict.value}"

    def test_strongly_positive(self) -> None:
        assert _verdict_label_mne("strongly_positive") == "Izrazito pozitivno"

    def test_negative(self) -> None:
        assert _verdict_label_mne("negative") == "Negativno"

    def test_unknown_value_returns_as_is(self) -> None:
        assert _verdict_label_mne("unknown") == "unknown"


class TestHasMontenegrinContent:
    def test_bilingual_result_has_mne(self) -> None:
        result = _make_bilingual_result()
        assert has_montenegrin_content(result) is True

    def test_english_only_result_no_mne(self) -> None:
        result = _make_english_only_result()
        assert has_montenegrin_content(result) is False

    def test_empty_result_no_mne(self) -> None:
        decision = GovernmentDecision(
            id="empty-001",
            title="Test",
            summary="Test",
            date=date(2026, 1, 1),
            category="test",
        )
        result = SessionResult(decision=decision)
        assert has_montenegrin_content(result) is False


class TestJsonExportBilingual:
    """Test that JSON export preserves bilingual content."""

    @pytest.fixture()
    def exported_data(self, tmp_path: Path) -> dict:
        result = _make_bilingual_result()
        output_dir = tmp_path / "data"
        export_json([result], None, output_dir)
        # Read the individual analysis JSON
        analysis_path = output_dir / "analyses" / "bi-001.json"
        return json.loads(analysis_path.read_text())

    @pytest.fixture()
    def exported_index(self, tmp_path: Path) -> list:
        result = _make_bilingual_result()
        output_dir = tmp_path / "data"
        export_json([result], None, output_dir)
        index_path = output_dir / "analyses-index.json"
        return json.loads(index_path.read_text())

    def test_analysis_contains_mne_headline(self, exported_data: dict) -> None:
        assert exported_data["critic_report"]["headline_mne"] == (
            "Zakon o životnoj sredini: korak naprijed uz rizike"
        )

    def test_analysis_contains_en_headline(self, exported_data: dict) -> None:
        assert exported_data["critic_report"]["headline"] == (
            "Environment Law: Forward Step with Risks"
        )

    def test_analysis_contains_mne_summary(self, exported_data: dict) -> None:
        assert "Pozitivan korak za zaštitu" in exported_data["assessments"][0]["summary_mne"]

    def test_analysis_contains_en_summary(self, exported_data: dict) -> None:
        assert "positive step for environmental" in exported_data["assessments"][0]["summary"]

    def test_analysis_contains_mne_counter_proposal(self, exported_data: dict) -> None:
        assert exported_data["counter_proposal"]["title_mne"] == (
            "Progresivna reforma životne sredine"
        )

    def test_analysis_scores(self, exported_data: dict) -> None:
        assert exported_data["critic_report"]["decision_score"] == 7
        assert exported_data["critic_report"]["assessment_quality_score"] == 6

    def test_index_contains_verdict_labels(self, exported_index: list) -> None:
        entry = exported_index[0]
        assert entry["verdict_label"] == "Positive"
        assert entry["verdict_label_mne"] == "Pozitivno"

    def test_index_contains_decision_score(self, exported_index: list) -> None:
        entry = exported_index[0]
        assert entry["decision_score"] == 7


class TestMinistryNameMne:
    def test_known_ministries(self) -> None:
        assert _ministry_name_mne("Finance") == "finansija"
        assert _ministry_name_mne("Justice") == "pravde"
        assert _ministry_name_mne("EU Integration") == "evropskih integracija"
        assert _ministry_name_mne("Health") == "zdravlja"
        assert _ministry_name_mne("Education") == "prosvjete"
        assert _ministry_name_mne("Economy") == "ekonomije"
        assert _ministry_name_mne("Tourism") == "turizma"
        assert _ministry_name_mne("Environment") == "ekologije"

    def test_unknown_ministry_returns_as_is(self) -> None:
        assert _ministry_name_mne("Defence") == "Defence"


class TestBilingualModelFields:
    """Test that MNE fields on Pydantic models work correctly."""

    def test_critic_report_mne_defaults(self) -> None:
        cr = CriticReport(
            decision_id="t",
            decision_score=5,
            assessment_quality_score=5,
            overall_analysis="Analysis",
            headline="Headline",
        )
        assert cr.headline_mne == ""
        assert cr.overall_analysis_mne == ""
        assert cr.blind_spots_mne == []

    def test_assessment_mne_defaults(self) -> None:
        a = Assessment(
            ministry="Finance",
            decision_id="t",
            verdict=Verdict.NEUTRAL,
            score=5,
            summary="Summary",
            reasoning="Reasoning",
        )
        assert a.summary_mne == ""
        assert a.executive_summary_mne is None
        assert a.key_concerns_mne == []
        assert a.recommendations_mne == []

    def test_counter_proposal_mne_defaults(self) -> None:
        cp = CounterProposal(
            decision_id="t",
            title="Title",
            executive_summary="Summary",
            detailed_proposal="Proposal",
        )
        assert cp.title_mne == ""
        assert cp.executive_summary_mne == ""
        assert cp.detailed_proposal_mne == ""
        assert cp.ministry_contributions_mne == []
        assert cp.key_differences_mne == []
        assert cp.implementation_steps_mne == []
        assert cp.risks_and_tradeoffs_mne == []

    def test_parliament_debate_mne_defaults(self) -> None:
        pd = ParliamentDebate(
            decision_id="t",
            consensus_summary="Consensus",
            overall_verdict=Verdict.NEUTRAL,
            debate_transcript="Transcript",
        )
        assert pd.consensus_summary_mne == ""
        assert pd.disagreements_mne == []
        assert pd.debate_transcript_mne == ""

    def test_ministry_counter_proposal_mne_defaults(self) -> None:
        mcp = MinistryCounterProposal(
            title="Title",
            summary="Summary",
        )
        assert mcp.title_mne == ""
        assert mcp.summary_mne == ""
        assert mcp.key_changes_mne == []
        assert mcp.expected_benefits_mne == []
        assert mcp.estimated_feasibility_mne == ""

    def test_serialization_roundtrip(self) -> None:
        """MNE fields survive JSON serialization/deserialization."""
        result = _make_bilingual_result()
        json_str = result.model_dump_json()
        restored = SessionResult.model_validate_json(json_str)
        assert restored.critic_report is not None
        assert restored.critic_report.headline_mne == "Zakon o životnoj sredini: korak naprijed uz rizike"
        assert restored.assessments[0].summary_mne == (
            "Pozitivan korak za zaštitu životne sredine sa fiskalnim implikacijama."
        )
        assert restored.counter_proposal is not None
        assert restored.counter_proposal.title_mne == "Progresivna reforma životne sredine"
