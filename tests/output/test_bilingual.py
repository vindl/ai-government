"""Tests for bilingual (MNE/EN) rendering on scorecard pages."""

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
    MinistryCounterProposal,
    ParliamentDebate,
    Verdict,
)
from ai_government.models.decision import GovernmentDecision
from ai_government.orchestrator import SessionResult
from ai_government.output.html import _verdict_label_mne
from ai_government.output.localization import has_montenegrin_content
from ai_government.output.site_builder import SiteBuilder


def _make_bilingual_result() -> SessionResult:
    """Create a SessionResult with both EN and MNE content populated."""
    decision = GovernmentDecision(
        id="bi-001",
        title="Predlog zakona o zaštiti životne sredine",
        summary="Zakon o zaštiti životne sredine sa novim standardima.",
        date=date(2026, 2, 15),
        category="environment",
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
            title_mne="Fazna implementacija",
            summary_mne="Postepeno uvođenje u 3 faze.",
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
        key_differences=["Gradual instead of immediate"],
        implementation_steps=["Adopt framework", "Phase 1"],
        risks_and_tradeoffs=["Slower environmental impact"],
        title_mne="Progresivna reforma životne sredine",
        executive_summary_mne="Postepeni pristup standardima zaštite životne sredine.",
        detailed_proposal_mne="Predloženi pristup kombinuje fiskalnu opreznost sa zaštitom.",
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


class TestBilingualScorecardRendering:
    """Test that bilingual content renders correctly in scorecard HTML."""

    @pytest.fixture()
    def bilingual_html(self, tmp_path: Path) -> str:
        builder = SiteBuilder(tmp_path)
        result = _make_bilingual_result()
        builder._build_scorecards([result])
        path = tmp_path / "decisions" / "bi-001.html"
        return path.read_text()

    @pytest.fixture()
    def english_only_html(self, tmp_path: Path) -> str:
        builder = SiteBuilder(tmp_path)
        result = _make_english_only_result()
        builder._build_scorecards([result])
        path = tmp_path / "decisions" / "en-001.html"
        return path.read_text()

    def test_contains_language_toggle(self, bilingual_html: str) -> None:
        assert 'class="lang-toggle"' in bilingual_html
        assert 'data-lang="mne"' in bilingual_html
        assert 'data-lang="en"' in bilingual_html

    def test_contains_mne_headline(self, bilingual_html: str) -> None:
        assert "korak naprijed uz rizike" in bilingual_html

    def test_contains_en_headline(self, bilingual_html: str) -> None:
        assert "Forward Step with Risks" in bilingual_html

    def test_contains_mne_verdict_label(self, bilingual_html: str) -> None:
        assert "Pozitivno" in bilingual_html

    def test_contains_en_verdict_label(self, bilingual_html: str) -> None:
        assert "Positive" in bilingual_html

    def test_contains_mne_summary(self, bilingual_html: str) -> None:
        assert "Pozitivan korak za za\u0161titu" in bilingual_html

    def test_contains_en_summary(self, bilingual_html: str) -> None:
        assert "positive step for environmental" in bilingual_html

    def test_contains_mne_section_headers(self, bilingual_html: str) -> None:
        assert "Ocjene ministarstava" in bilingual_html
        assert "Detaljne analize" in bilingual_html
        assert "Nezavisna kritička analiza" in bilingual_html

    def test_contains_en_section_headers(self, bilingual_html: str) -> None:
        assert "Ministry Verdicts" in bilingual_html
        assert "Detailed Analyses" in bilingual_html
        assert "Independent Critical Analysis" in bilingual_html

    def test_contains_mne_key_concerns(self, bilingual_html: str) -> None:
        assert "Uticaj na budžet" in bilingual_html

    def test_contains_en_key_concerns(self, bilingual_html: str) -> None:
        assert "Budget impact" in bilingual_html

    def test_contains_mne_counter_proposal(self, bilingual_html: str) -> None:
        assert "Kontra-prijedlog AI Vlade" in bilingual_html
        assert "Progresivna reforma" in bilingual_html

    def test_contains_en_counter_proposal(self, bilingual_html: str) -> None:
        assert "AI Government Counter-proposal" in bilingual_html
        assert "Progressive Environmental Reform" in bilingual_html

    def test_contains_mne_debate_section(self, bilingual_html: str) -> None:
        assert "Parlamentarna debata" in bilingual_html
        assert "mjera socijalno opravdana" in bilingual_html

    def test_contains_en_debate_section(self, bilingual_html: str) -> None:
        assert "Parliamentary Debate" in bilingual_html
        assert "socially justified" in bilingual_html

    def test_lang_classes_present(self, bilingual_html: str) -> None:
        assert 'class="lang-mne"' in bilingual_html
        assert 'class="lang-en"' in bilingual_html

    def test_scores_remain_neutral(self, bilingual_html: str) -> None:
        assert "7/10" in bilingual_html
        assert "6/10" in bilingual_html

    def test_english_only_still_renders(self, english_only_html: str) -> None:
        assert "Budget Change: Business as Usual" in english_only_html
        assert "lang-toggle" in english_only_html

    def test_mne_score_labels(self, bilingual_html: str) -> None:
        assert "Ocjena odluke" in bilingual_html
        assert "Kvalitet analize" in bilingual_html

    def test_mne_error_report(self, bilingual_html: str) -> None:
        assert "Prijavite grešku" in bilingual_html
        assert "Report an error" in bilingual_html

    def test_ministry_counter_proposal_mne(self, bilingual_html: str) -> None:
        assert "Fazna implementacija" in bilingual_html
        assert "Postepeno uvođenje" in bilingual_html


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

    def test_ministry_counter_proposal_mne_defaults(self) -> None:
        mcp = MinistryCounterProposal(
            title="Title",
            summary="Summary",
        )
        assert mcp.title_mne == ""
        assert mcp.summary_mne == ""

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
