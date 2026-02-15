"""Tests for bilingual (Montenegrin/English) site output."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

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
from ai_government.output.localization import UI_LABELS, ui_label, verdict_label
from ai_government.output.site_builder import SiteBuilder

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Localization helpers
# ---------------------------------------------------------------------------


class TestVerdictLabel:
    def test_english_labels(self) -> None:
        assert verdict_label("positive", "en") == "Positive"
        assert verdict_label("strongly_negative", "en") == "Strongly Negative"

    def test_montenegrin_labels(self) -> None:
        assert verdict_label("positive", "mne") == "Pozitivno"
        assert verdict_label("strongly_negative", "mne") == "Izrazito negativno"

    def test_unknown_verdict_returns_raw(self) -> None:
        assert verdict_label("unknown_value", "en") == "unknown_value"

    def test_default_lang_is_english(self) -> None:
        assert verdict_label("neutral") == "Neutral"


class TestUiLabel:
    def test_english_label(self) -> None:
        assert ui_label("ministry_verdicts", "en") == "Ministry Verdicts"

    def test_montenegrin_label(self) -> None:
        assert ui_label("ministry_verdicts", "mne") == "Ocjene ministarstava"

    def test_unknown_key_returns_key(self) -> None:
        assert ui_label("nonexistent_key", "en") == "nonexistent_key"

    def test_all_en_keys_have_mne_counterpart(self) -> None:
        for key in UI_LABELS["en"]:
            assert key in UI_LABELS["mne"], f"Missing Montenegrin translation for '{key}'"


# ---------------------------------------------------------------------------
# Model _mne fields
# ---------------------------------------------------------------------------


class TestMneModelFields:
    def test_critic_report_mne_defaults(self) -> None:
        report = CriticReport(
            decision_id="x",
            decision_score=5,
            assessment_quality_score=5,
            overall_analysis="Analysis",
            headline="Headline",
        )
        assert report.headline_mne == ""
        assert report.overall_analysis_mne == ""

    def test_critic_report_mne_populated(self) -> None:
        report = CriticReport(
            decision_id="x",
            decision_score=5,
            assessment_quality_score=5,
            overall_analysis="Analysis",
            headline="Headline",
            headline_mne="Naslov",
            overall_analysis_mne="Analiza",
        )
        assert report.headline_mne == "Naslov"
        assert report.overall_analysis_mne == "Analiza"

    def test_assessment_mne_defaults(self) -> None:
        a = Assessment(
            ministry="Finance",
            decision_id="x",
            verdict=Verdict.NEUTRAL,
            score=5,
            summary="Summary",
            reasoning="Reasoning",
        )
        assert a.summary_mne == ""
        assert a.executive_summary_mne == ""

    def test_counter_proposal_mne_default(self) -> None:
        cp = CounterProposal(
            decision_id="x",
            title="Title",
            executive_summary="Exec summary",
            detailed_proposal="Details",
        )
        assert cp.executive_summary_mne == ""

    def test_ministry_counter_proposal_mne_default(self) -> None:
        mcp = MinistryCounterProposal(
            title="Title",
            summary="Summary",
        )
        assert mcp.summary_mne == ""

    def test_mne_fields_roundtrip_json(self) -> None:
        """Ensure _mne fields survive JSON serialization."""
        report = CriticReport(
            decision_id="x",
            decision_score=5,
            assessment_quality_score=5,
            overall_analysis="Analysis",
            headline="Headline",
            headline_mne="Naslov MNE",
        )
        json_str = report.model_dump_json()
        restored = CriticReport.model_validate_json(json_str)
        assert restored.headline_mne == "Naslov MNE"


# ---------------------------------------------------------------------------
# Bilingual scorecard rendering
# ---------------------------------------------------------------------------


def _make_bilingual_result() -> SessionResult:
    """Create a SessionResult with Montenegrin translations populated."""
    decision = GovernmentDecision(
        id="bi-001",
        title="Test Decision",
        summary="Decision summary",
        date=date(2026, 2, 15),
        category="fiscal",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="bi-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="English summary of assessment.",
        summary_mne="Crnogorski rezime ocjene.",
        executive_summary="English exec summary.",
        executive_summary_mne="Crnogorski kratak pregled.",
        reasoning="Reasoning text",
        key_concerns=["Concern A"],
        recommendations=["Recommendation A"],
        counter_proposal=MinistryCounterProposal(
            title="Alt Proposal",
            summary="English counter-proposal summary.",
            summary_mne="Crnogorski rezime kontraprijedloga.",
        ),
    )
    critic = CriticReport(
        decision_id="bi-001",
        decision_score=7,
        assessment_quality_score=6,
        blind_spots=["Blind spot"],
        overall_analysis="English analysis.",
        overall_analysis_mne="Crnogorska analiza.",
        headline="English Headline",
        headline_mne="Crnogorski naslov",
    )
    debate = ParliamentDebate(
        decision_id="bi-001",
        consensus_summary="Consensus text",
        disagreements=["Point of disagreement"],
        overall_verdict=Verdict.POSITIVE,
        debate_transcript="Debate transcript",
    )
    counter = CounterProposal(
        decision_id="bi-001",
        title="Unified Counter",
        executive_summary="English exec summary for counter.",
        executive_summary_mne="Crnogorski kratak pregled kontraprijedloga.",
        detailed_proposal="Detailed proposal text",
        key_differences=["Diff 1"],
        implementation_steps=["Step 1"],
        risks_and_tradeoffs=["Risk 1"],
        ministry_contributions=["Finance: contribution"],
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        debate=debate,
        critic_report=critic,
        counter_proposal=counter,
    )


class TestBilingualScorecard:
    def test_scorecard_contains_both_languages(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        # Montenegrin content
        assert "Crnogorski naslov" in html
        assert "Crnogorski rezime ocjene." in html
        assert "Crnogorski kratak pregled." in html
        assert "Crnogorska analiza." in html
        assert "Crnogorski rezime kontraprijedloga." in html
        assert "Crnogorski kratak pregled kontraprijedloga." in html

        # English content
        assert "English Headline" in html
        assert "English summary of assessment." in html
        assert "English exec summary." in html
        assert "English analysis." in html

    def test_scorecard_contains_lang_switcher(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        assert "lang-switcher" in html
        assert 'data-lang="mne"' in html
        assert 'data-lang="en"' in html

    def test_scorecard_contains_bilingual_ui_labels(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        # Montenegrin UI labels
        assert "Ocjene ministarstava" in html  # Ministry Verdicts
        assert "Detaljne analize" in html  # Detailed Analyses
        assert "Ocjena odluke" in html  # Decision Score

        # English UI labels
        assert "Ministry Verdicts" in html
        assert "Detailed Analyses" in html
        assert "Decision Score" in html

    def test_scorecard_contains_bilingual_verdict_labels(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        assert "Pozitivno" in html  # Montenegrin "Positive"
        assert "Positive" in html  # English

    def test_scorecard_has_lang_css_classes(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        assert 'class="lang-mne"' in html
        assert 'class="lang-en"' in html

    def test_scorecard_js_toggle_script(self, tmp_path: Path) -> None:
        result = _make_bilingual_result()
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "bi-001.html").read_text()

        assert "aigov-lang" in html  # localStorage key
        assert "setLang" in html  # JS function
        assert "defaultLang" in html


class TestBilingualFallback:
    """When _mne fields are empty, template falls back to English content."""

    def test_fallback_when_no_mne_translations(self, tmp_path: Path) -> None:
        decision = GovernmentDecision(
            id="fb-001",
            title="Fallback Decision",
            summary="Decision summary",
            date=date(2026, 2, 15),
            category="general",
        )
        assessment = Assessment(
            ministry="Justice",
            decision_id="fb-001",
            verdict=Verdict.NEUTRAL,
            score=5,
            summary="English only summary.",
            reasoning="Reasoning",
        )
        critic = CriticReport(
            decision_id="fb-001",
            decision_score=5,
            assessment_quality_score=5,
            overall_analysis="English only analysis.",
            headline="English Only Headline",
            # No _mne fields set — defaults to ""
        )
        result = SessionResult(
            decision=decision,
            assessments=[assessment],
            critic_report=critic,
        )
        builder = SiteBuilder(tmp_path)
        builder._build_scorecards([result])

        html = (tmp_path / "decisions" / "fb-001.html").read_text()

        # The English content should still appear for both language views
        assert "English Only Headline" in html
        assert "English only summary." in html
        assert "English only analysis." in html

        # The page should still have the language toggle
        assert "lang-switcher" in html
