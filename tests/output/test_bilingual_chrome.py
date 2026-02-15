"""Tests for bilingual navigation chrome and global language toggle.

Verifies that base.html provides bilingual nav/footer on all pages
and that all page templates contain lang-mne/lang-en pairs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from ai_government.models.assessment import Assessment, CriticReport, Verdict
from ai_government.models.decision import GovernmentDecision
from ai_government.models.override import HumanOverride, HumanSuggestion
from ai_government.orchestrator import SessionResult
from ai_government.output.site_builder import SiteBuilder


def _make_result() -> SessionResult:
    """Minimal SessionResult for testing page rendering."""
    decision = GovernmentDecision(
        id="chrome-001",
        title="Test Decision",
        summary="A test decision.",
        date=date(2026, 2, 15),
        category="test",
        title_mne="Testna odluka",
        summary_mne="Testna odluka opis.",
    )
    assessment = Assessment(
        ministry="Finance",
        decision_id="chrome-001",
        verdict=Verdict.POSITIVE,
        score=7,
        summary="Good decision.",
        reasoning="Sound reasoning.",
    )
    critic = CriticReport(
        decision_id="chrome-001",
        decision_score=7,
        assessment_quality_score=6,
        overall_analysis="Good.",
        headline="Test Headline",
    )
    return SessionResult(
        decision=decision,
        assessments=[assessment],
        critic_report=critic,
    )


@pytest.fixture()
def site_dir(tmp_path: Path) -> Path:
    """Build a full site and return the output directory."""
    output_dir = tmp_path / "site"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Write empty overrides/suggestions so transparency page renders
    (data_dir / "overrides.json").write_text("[]")
    (data_dir / "suggestions.json").write_text("[]")

    builder = SiteBuilder(output_dir)
    builder.build([_make_result()], data_dir=data_dir)
    return output_dir


class TestGlobalLanguageToggle:
    """Toggle button appears on every page, not just scorecards."""

    def _read(self, site_dir: Path, rel: str) -> str:
        return (site_dir / rel).read_text()

    def test_toggle_on_index(self, site_dir: Path) -> None:
        html = self._read(site_dir, "index.html")
        assert 'class="lang-toggle"' in html

    def test_toggle_on_decisions_index(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/index.html")
        assert 'class="lang-toggle"' in html

    def test_toggle_on_scorecard(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/chrome-001.html")
        assert 'class="lang-toggle"' in html

    def test_toggle_on_constitution(self, site_dir: Path) -> None:
        html = self._read(site_dir, "constitution/index.html")
        assert 'class="lang-toggle"' in html

    def test_toggle_on_transparency(self, site_dir: Path) -> None:
        html = self._read(site_dir, "transparency/index.html")
        assert 'class="lang-toggle"' in html


class TestScoreardToggleRemoved:
    """The toggle should live only in base.html, not duplicated in scorecard."""

    def test_only_one_toggle_in_scorecard(self, site_dir: Path) -> None:
        html = (site_dir / "decisions" / "chrome-001.html").read_text()
        # Should have exactly one lang-toggle (from base.html nav)
        assert html.count('class="lang-toggle"') == 1


class TestBilingualNav:
    """Nav bar contains both MNE and EN versions of all links."""

    @pytest.fixture()
    def nav_html(self, site_dir: Path) -> str:
        html = (site_dir / "index.html").read_text()
        # Extract the nav section
        start = html.find("<nav>")
        end = html.find("</nav>") + len("</nav>")
        return html[start:end]

    def test_nav_contains_mne_links(self, nav_html: str) -> None:
        assert "Odluke" in nav_html
        assert "Transparentnost" in nav_html
        assert "Ustav" in nav_html
        assert "Vijesti" in nav_html

    def test_nav_contains_en_links(self, nav_html: str) -> None:
        assert "Decisions" in nav_html
        assert "Transparency" in nav_html
        assert "Constitution" in nav_html
        assert "News" in nav_html

    def test_site_title_bilingual(self, nav_html: str) -> None:
        assert "AI Vlada Crne Gore" in nav_html
        assert "AI Government of Montenegro" in nav_html


class TestBilingualFooter:
    """Footer contains both MNE and EN versions."""

    @pytest.fixture()
    def footer_html(self, site_dir: Path) -> str:
        html = (site_dir / "index.html").read_text()
        start = html.find("<footer>")
        end = html.find("</footer>") + len("</footer>")
        return html[start:end]

    def test_footer_mne(self, footer_html: str) -> None:
        assert "Nezavisna AI analiza vladinih odluka" in footer_html
        assert "Izvorni kod" in footer_html

    def test_footer_en(self, footer_html: str) -> None:
        assert "Independent AI analysis of government decisions" in footer_html
        assert "Source code" in footer_html

    def test_footer_has_lang_classes(self, footer_html: str) -> None:
        assert "lang-mne" in footer_html
        assert "lang-en" in footer_html


class TestIndexPageBilingual:
    """index.html has bilingual headings and CTA."""

    @pytest.fixture()
    def html(self, site_dir: Path) -> str:
        return (site_dir / "index.html").read_text()

    def test_mne_heading(self, html: str) -> None:
        assert "AI Vlada Crne Gore" in html

    def test_en_heading(self, html: str) -> None:
        assert "AI Government of Montenegro" in html

    def test_mne_latest_decisions(self, html: str) -> None:
        assert "Posljednje odluke" in html

    def test_en_latest_decisions(self, html: str) -> None:
        assert "Latest Decisions" in html

    def test_mne_cta(self, html: str) -> None:
        assert "Predložite odluku za analizu" in html

    def test_en_cta(self, html: str) -> None:
        assert "Suggest a decision for analysis" in html


class TestDecisionsIndexBilingual:
    """decisions_index.html has bilingual headings."""

    @pytest.fixture()
    def html(self, site_dir: Path) -> str:
        return (site_dir / "decisions" / "index.html").read_text()

    def test_mne_heading(self, html: str) -> None:
        assert "Sve odluke" in html

    def test_en_heading(self, html: str) -> None:
        assert "All Decisions" in html

    def test_mne_description(self, html: str) -> None:
        assert "Kompletna lista analiziranih vladinih odluka" in html

    def test_en_description(self, html: str) -> None:
        assert "Complete list of analyzed government decisions" in html


class TestTransparencyPageBilingual:
    """transparency.html has bilingual headings and labels."""

    @pytest.fixture()
    def html(self, site_dir: Path) -> str:
        return (site_dir / "transparency" / "index.html").read_text()

    def test_mne_heading(self, html: str) -> None:
        assert "Izvještaj o transparentnosti ljudskog uticaja" in html

    def test_en_heading(self, html: str) -> None:
        assert "Human Influence Transparency Report" in html

    def test_mne_how_overrides(self, html: str) -> None:
        assert "Kako zamjene funkcionišu" in html

    def test_en_how_overrides(self, html: str) -> None:
        assert "How Overrides Work" in html

    def test_mne_no_records(self, html: str) -> None:
        assert "Još nijesu zabilježene ljudske intervencije" in html

    def test_en_no_records(self, html: str) -> None:
        assert "No human interventions have been recorded yet" in html


class TestTransparencyPageWithData:
    """transparency.html with overrides and suggestions has bilingual labels."""

    @pytest.fixture()
    def html(self, tmp_path: Path) -> str:
        output_dir = tmp_path / "site"
        overrides = [
            HumanOverride(
                timestamp=datetime(2026, 2, 14, 12, 0, tzinfo=UTC),
                issue_number=42,
                override_type="comment",
                actor="vindl",
                issue_title="Test issue",
                ai_verdict="Rejected",
                human_action="Moved to backlog",
            )
        ]
        suggestions = [
            HumanSuggestion(
                timestamp=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
                issue_number=99,
                issue_title="Suggested task",
                status="open",
                creator="vindl",
            )
        ]
        builder = SiteBuilder(output_dir)
        builder._build_transparency(overrides, suggestions)
        return (output_dir / "transparency" / "index.html").read_text()

    def test_mne_overrides_heading(self, html: str) -> None:
        assert "Zamjene AI odluka" in html

    def test_en_overrides_heading(self, html: str) -> None:
        assert "AI Decision Overrides" in html

    def test_mne_suggestions_heading(self, html: str) -> None:
        assert "Zadaci koje su odredili ljudi" in html

    def test_en_suggestions_heading(self, html: str) -> None:
        assert "Human-Directed Tasks" in html

    def test_mne_labels(self, html: str) -> None:
        assert "Tip zamjene" in html
        assert "Akter" in html

    def test_en_labels(self, html: str) -> None:
        assert "Override type" in html
        assert "Actor:" in html


class TestBilingualDecisionTitles:
    """Decision titles and summaries are wrapped with lang-mne/lang-en on listing pages."""

    def _read(self, site_dir: Path, rel: str) -> str:
        return (site_dir / rel).read_text()

    def test_index_has_mne_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "index.html")
        assert '<span class="lang-mne">Testna odluka</span>' in html

    def test_index_has_en_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "index.html")
        assert '<span class="lang-en">Test Decision</span>' in html

    def test_index_has_mne_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "index.html")
        assert "lang-mne" in html
        assert "Testna odluka opis." in html

    def test_index_has_en_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "index.html")
        assert "A test decision." in html

    def test_decisions_index_has_mne_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/index.html")
        assert '<span class="lang-mne">Testna odluka</span>' in html

    def test_decisions_index_has_en_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/index.html")
        assert '<span class="lang-en">Test Decision</span>' in html

    def test_decisions_index_has_mne_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/index.html")
        assert "Testna odluka opis." in html

    def test_decisions_index_has_en_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/index.html")
        assert "A test decision." in html

    def test_scorecard_has_mne_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/chrome-001.html")
        assert '<h1 class="lang-mne">Testna odluka</h1>' in html

    def test_scorecard_has_en_title(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/chrome-001.html")
        assert '<h1 class="lang-en">Test Decision</h1>' in html

    def test_scorecard_has_mne_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/chrome-001.html")
        assert "Testna odluka opis." in html

    def test_scorecard_has_en_summary(self, site_dir: Path) -> None:
        html = self._read(site_dir, "decisions/chrome-001.html")
        assert "A test decision." in html

class TestBilingualTitlesBackwardCompat:
    """When _mne fields are empty, titles render without lang classes (always visible)."""

    @pytest.fixture()
    def site_dir_no_mne(self, tmp_path: Path) -> Path:
        output_dir = tmp_path / "site"
        decision = GovernmentDecision(
            id="compat-001",
            title="English Only Title",
            summary="English only summary.",
            date=date(2026, 2, 15),
            category="test",
        )
        assessment = Assessment(
            ministry="Finance",
            decision_id="compat-001",
            verdict=Verdict.POSITIVE,
            score=7,
            summary="Good decision.",
            reasoning="Sound reasoning.",
        )
        critic = CriticReport(
            decision_id="compat-001",
            decision_score=7,
            assessment_quality_score=6,
            overall_analysis="Good.",
            headline="Test Headline",
        )
        result = SessionResult(
            decision=decision,
            assessments=[assessment],
            critic_report=critic,
        )
        builder = SiteBuilder(output_dir)
        builder.build([result])
        return output_dir

    def test_index_no_lang_class_when_empty(self, site_dir_no_mne: Path) -> None:
        html = (site_dir_no_mne / "index.html").read_text()
        # Title should be present without lang-en class wrapping
        assert "English Only Title" in html
        # No lang-mne span for the title since title_mne is empty
        assert "lang-mne" not in html or '<span class="lang-mne">English Only Title' not in html

    def test_decisions_index_no_lang_class_when_empty(self, site_dir_no_mne: Path) -> None:
        html = (site_dir_no_mne / "decisions" / "index.html").read_text()
        assert "English Only Title" in html
