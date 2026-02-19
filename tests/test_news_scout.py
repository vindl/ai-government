"""Tests for news scout helper functions in main_loop.py."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest
    from government.models.decision import GovernmentDecision

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from main_loop import (  # noqa: E402
    CATEGORY_CAP_MIN_KEPT,
    NEWS_GATE_MAX_PENDING,
    NewsScoutState,
    _build_category_distribution_context,
    _enforce_category_caps,
    _generate_decision_id,
    _parse_json_array,
    should_fetch_news,
)

# ---------------------------------------------------------------------------
# NewsScoutState model
# ---------------------------------------------------------------------------


class TestNewsScoutState:
    def test_create_default(self) -> None:
        state = NewsScoutState()
        assert state.last_fetch_date == ""

    def test_create_with_date(self) -> None:
        state = NewsScoutState(last_fetch_date="2026-02-14")
        assert state.last_fetch_date == "2026-02-14"

    def test_json_roundtrip(self) -> None:
        state = NewsScoutState(last_fetch_date="2026-02-14")
        raw = state.model_dump_json()
        restored = NewsScoutState.model_validate_json(raw)
        assert restored.last_fetch_date == "2026-02-14"


# ---------------------------------------------------------------------------
# should_fetch_news()
# ---------------------------------------------------------------------------


class TestShouldFetchNews:
    def test_returns_true_when_no_state_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_false_when_fetched_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        today = _dt.date.today().isoformat()
        state_path.write_text(NewsScoutState(last_fetch_date=today).model_dump_json())
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is False

    def test_returns_true_when_fetched_yesterday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        state_path.write_text(NewsScoutState(last_fetch_date=yesterday).model_dump_json())
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_true_on_corrupt_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text("not json")
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", state_path)
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 0)
        assert should_fetch_news() is True

    def test_returns_true_when_backlog_within_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """News scout runs when pending issues are at or below threshold."""
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        # 1 pending issue is within the NEWS_GATE_MAX_PENDING=2 threshold
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: 1)
        assert should_fetch_news() is True

    def test_returns_true_when_backlog_at_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """News scout runs when pending issues are exactly at threshold."""
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: NEWS_GATE_MAX_PENDING)
        assert should_fetch_news() is True

    def test_returns_false_when_backlog_exceeds_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """News scout blocks when pending issues exceed threshold."""
        monkeypatch.setattr("main_loop.NEWS_SCOUT_STATE_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setattr("main_loop._count_pending_analysis_issues", lambda: NEWS_GATE_MAX_PENDING + 1)
        assert should_fetch_news() is False


# ---------------------------------------------------------------------------
# _generate_decision_id()
# ---------------------------------------------------------------------------


class TestGenerateDecisionId:
    def test_deterministic(self) -> None:
        d = _dt.date(2026, 2, 14)
        id1 = _generate_decision_id("Test title", d)
        id2 = _generate_decision_id("Test title", d)
        assert id1 == id2

    def test_format(self) -> None:
        d = _dt.date(2026, 2, 14)
        result = _generate_decision_id("Vlada usvojila budžet", d)
        assert result.startswith("item-2026-02-14-")
        # 8 hex chars after the date prefix (item-YYYY-MM-DD-XXXXXXXX)
        suffix = result.rsplit("-", 1)[-1]
        assert len(suffix) == 8

    def test_different_titles_different_ids(self) -> None:
        d = _dt.date(2026, 2, 14)
        id1 = _generate_decision_id("Title A", d)
        id2 = _generate_decision_id("Title B", d)
        assert id1 != id2

    def test_different_dates_different_ids(self) -> None:
        id1 = _generate_decision_id("Same title", _dt.date(2026, 2, 14))
        id2 = _generate_decision_id("Same title", _dt.date(2026, 2, 15))
        assert id1 != id2


# ---------------------------------------------------------------------------
# _parse_json_array() — used by news scout output parsing
# ---------------------------------------------------------------------------


class TestParseJsonArray:
    def test_parses_clean_json(self) -> None:
        raw = json.dumps([{"title": "T", "summary": "S"}])
        result = _parse_json_array(raw)
        assert len(result) == 1
        assert result[0]["title"] == "T"

    def test_extracts_json_from_surrounding_text(self) -> None:
        text = 'Here are the results:\n[{"title": "X"}]\nDone.'
        result = _parse_json_array(text)
        assert len(result) == 1

    def test_returns_empty_on_no_json(self) -> None:
        assert _parse_json_array("no json here") == []

    def test_returns_empty_on_empty_string(self) -> None:
        assert _parse_json_array("") == []


# ---------------------------------------------------------------------------
# Decision JSON embedding in issue body
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _build_category_distribution_context()
# ---------------------------------------------------------------------------


class TestBuildCategoryDistributionContext:
    """Test the category distribution context builder for news scout."""

    def test_returns_empty_when_no_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("main_loop.DATA_DIR", tmp_path / "nonexistent")
        assert _build_category_distribution_context() == ""

    def test_returns_empty_when_no_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        assert _build_category_distribution_context() == ""

    def test_shows_category_counts_and_percentages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create 3 results: 2 legal, 1 fiscal
        for i, cat in enumerate(["legal", "legal", "fiscal"]):
            result = SessionResult(
                decision=GovernmentDecision(
                    id=f"item-2026-02-14-{i:08x}",
                    title=f"Decision {i}",
                    summary="Summary",
                    date=_dt.date(2026, 2, 14),
                    category=cat,
                ),
            )
            (data_dir / f"result_{i}.json").write_text(
                result.model_dump_json(indent=2)
            )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        assert "## Recent Category Distribution" in ctx
        assert "3 published analyses" in ctx
        assert "legal: 2 (67%)" in ctx
        assert "fiscal: 1 (33%)" in ctx

    def test_marks_overrepresented_categories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create 10 results: 6 legal (60%), 2 fiscal, 2 economy
        cats = ["legal"] * 6 + ["fiscal"] * 2 + ["economy"] * 2
        for i, cat in enumerate(cats):
            result = SessionResult(
                decision=GovernmentDecision(
                    id=f"item-2026-02-14-{i:08x}",
                    title=f"Decision {i}",
                    summary="Summary",
                    date=_dt.date(2026, 2, 14),
                    category=cat,
                ),
            )
            (data_dir / f"result_{i}.json").write_text(
                result.model_dump_json(indent=2)
            )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        # legal at 60% should be marked as overrepresented
        assert "OVER" in ctx
        assert "legal: 6 (60%)" in ctx
        # fiscal at 20% should NOT be marked
        assert "fiscal: 2 (20%)" in ctx
        # Verify the fiscal line itself doesn't contain the OVER marker
        fiscal_line = next(line for line in ctx.split("\n") if "fiscal:" in line)
        assert "OVER" not in fiscal_line

    def test_no_over_marker_when_balanced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create 5 results across 5 categories (each at 20%)
        cats = ["legal", "fiscal", "economy", "health", "education"]
        for i, cat in enumerate(cats):
            result = SessionResult(
                decision=GovernmentDecision(
                    id=f"item-2026-02-14-{i:08x}",
                    title=f"Decision {i}",
                    summary="Summary",
                    date=_dt.date(2026, 2, 14),
                    category=cat,
                ),
            )
            (data_dir / f"result_{i}.json").write_text(
                result.model_dump_json(indent=2)
            )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        # No category above 40%, so no OVER markers on category lines
        # (the instruction text mentions "OVER" generically)
        cat_lines = [
            line for line in ctx.split("\n")
            if line.strip().startswith(("legal:", "fiscal:", "economy:", "health:", "education:"))
        ]
        for line in cat_lines:
            assert "OVER" not in line

    def test_shows_priority_gaps_for_missing_high_resonance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Only legal and eu covered — economy, health, education, fiscal, security are missing
        for i, cat in enumerate(["legal", "eu"]):
            result = SessionResult(
                decision=GovernmentDecision(
                    id=f"item-2026-02-14-{i:08x}",
                    title=f"Decision {i}",
                    summary="Summary",
                    date=_dt.date(2026, 2, 14),
                    category=cat,
                ),
            )
            (data_dir / f"result_{i}.json").write_text(
                result.model_dump_json(indent=2)
            )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        assert "Priority gaps" in ctx
        for cat in ["economy", "health", "education", "fiscal", "security"]:
            assert cat in ctx

    def test_lists_uncovered_categories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        result = SessionResult(
            decision=GovernmentDecision(
                id="item-2026-02-14-00000000",
                title="Test",
                summary="Summary",
                date=_dt.date(2026, 2, 14),
                category="legal",
            ),
        )
        (data_dir / "result_0.json").write_text(
            result.model_dump_json(indent=2)
        )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        assert "Categories NOT yet covered:" in ctx
        # These high-resonance categories should appear as uncovered
        for cat in ["economy", "health", "education"]:
            assert cat in ctx

    def test_includes_diversify_instruction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from government.models.decision import GovernmentDecision
        from government.orchestrator import SessionResult

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        result = SessionResult(
            decision=GovernmentDecision(
                id="item-2026-02-14-00000000",
                title="Test",
                summary="Summary",
                date=_dt.date(2026, 2, 14),
                category="legal",
            ),
        )
        (data_dir / "result_0.json").write_text(
            result.model_dump_json(indent=2)
        )

        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        ctx = _build_category_distribution_context()

        assert "diversify" in ctx.lower()


# ---------------------------------------------------------------------------
# News scout prompt content
# ---------------------------------------------------------------------------


class TestNewsScoutPromptContent:
    """Verify the news scout prompt includes topic-resonance weighting."""

    def test_prompt_has_resonance_tiers(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "HIGH resonance" in content
        assert "LOW resonance" in content
        # High-resonance topics should be listed
        for topic in ["economy", "health", "education"]:
            assert topic in content

    def test_prompt_deprioritizes_routine_legal(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "routine legal harmonization" in content
        assert "procedural legislative amendments" in content

    def test_prompt_references_historical_balance(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "Recent Category Distribution" in content

    def test_prompt_has_legal_hard_cap(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "Hard cap on legal category" in content
        assert "At most 1 out of 3" in content

    def test_prompt_includes_corruption_as_high_resonance(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "corruption" in content.lower()
        # Corruption should be in the HIGH resonance tier
        high_section = content.split("HIGH resonance")[1].split("MEDIUM resonance")[0]
        assert "corruption" in high_section.lower()

    def test_prompt_requests_category_diversity_in_output(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "at least 2 different categories" in content

    def test_prompt_overrepresentation_threshold(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "40%" in content
        assert "OVER" in content

    def test_prompt_includes_official_gazette(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "sluzbenilist.me" in content
        assert "Službeni list Crne Gore" in content
        # Should have specific search guidance, not just a name
        for term in ["zakoni", "uredbe", "odluke"]:
            assert term in content

    def test_prompt_includes_parliament_website(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "skupstina.me" in content
        assert "Skupština Crne Gore" in content
        # Should have specific search guidance
        assert "plenary" in content.lower() or "session" in content.lower()
        assert "committee" in content.lower()

    def test_prompt_has_lookback_window(self) -> None:
        """News scout prompt allows looking back up to 3 days."""
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "3 days" in content
        assert "look back" in content.lower()

    def test_existing_sources_unchanged(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "news-scout" / "CLAUDE.md"
        content = prompt_path.read_text()

        for source in [
            "vijesti.me",
            "rtcg.me",
            "pobjeda.me",
            "gov.me",
            "cdm.me",
            "portalanalitika.me",
        ]:
            assert source in content


class TestConductorPromptDiversity:
    """Verify the conductor prompt includes topic-diversity guidance."""

    def test_conductor_has_diversity_section(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "conductor" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "Analysis Topic Diversity" in content

    def test_conductor_prefers_non_legal(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "theseus" / "conductor" / "CLAUDE.md"
        content = prompt_path.read_text()

        assert "non-legal" in content.lower() or "non-legal" in content
        for topic in ["economy", "health", "education"]:
            assert topic in content.lower()


class TestDecisionJsonEmbedding:
    """Test that we can embed and extract GovernmentDecision JSON from issue bodies."""

    def test_roundtrip(self) -> None:
        from government.models.decision import GovernmentDecision

        decision = GovernmentDecision(
            id="news-2026-02-14-abc12345",
            title="Test odluka",
            summary="Kratak opis odluke",
            full_text="Puni tekst",
            date=_dt.date(2026, 2, 14),
            source_url="https://vijesti.me/test",
            category="fiscal",
            tags=["budzet"],
        )

        # Simulate what create_analysis_issue() does
        decision_json = decision.model_dump_json(indent=2)
        body = (
            f"**Decision ID**: {decision.id}\n"
            f"**Date**: {decision.date}\n"
            f"**Category**: {decision.category}\n\n"
            f"> {decision.summary}\n\n"
            f"Run full AI cabinet analysis on this decision.\n\n"
            f"<details><summary>Decision JSON</summary>\n\n"
            f"```json\n{decision_json}\n```\n</details>"
        )

        # Simulate what step_execute_analysis() does to parse it back
        json_match = re.search(r"```json\n(.*?)\n```", body, re.DOTALL)
        assert json_match is not None
        restored = GovernmentDecision.model_validate_json(json_match.group(1))
        assert restored.id == decision.id
        assert restored.title == decision.title
        assert restored.category == decision.category
        assert restored.date == decision.date


# ---------------------------------------------------------------------------
# _enforce_category_caps()
# ---------------------------------------------------------------------------


def _make_decision(title: str, category: str) -> GovernmentDecision:
    """Helper to build a GovernmentDecision for testing."""
    from government.models.decision import GovernmentDecision

    return GovernmentDecision(
        id=f"item-2026-02-14-{hashlib.sha256(title.encode()).hexdigest()[:8]}",
        title=title,
        summary="Summary",
        date=_dt.date(2026, 2, 14),
        category=category,
    )


def _write_historical_results(
    data_dir: Path, categories: list[str],
) -> None:
    """Write fake SessionResult files to simulate historical analyses."""
    from government.models.decision import GovernmentDecision
    from government.orchestrator import SessionResult

    for i, cat in enumerate(categories):
        result = SessionResult(
            decision=GovernmentDecision(
                id=f"item-2026-02-14-{i:08x}",
                title=f"Historical decision {i}",
                summary="Summary",
                date=_dt.date(2026, 2, 14),
                category=cat,
            ),
        )
        (data_dir / f"result_{i}.json").write_text(
            result.model_dump_json(indent=2)
        )


class TestEnforceCategoryCaps:
    """Tests for the _enforce_category_caps() diversity enforcement."""

    def test_no_history_passes_all_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When there's no historical data, all decisions pass through."""
        monkeypatch.setattr("main_loop.DATA_DIR", tmp_path / "nonexistent")
        decisions = [
            _make_decision("A", "legal"),
            _make_decision("B", "legal"),
            _make_decision("C", "legal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 3

    def test_balanced_history_passes_all_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no category exceeds the threshold, all decisions pass."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 5 categories, each at 20% — none over 40%
        _write_historical_results(
            data_dir, ["legal", "fiscal", "economy", "health", "education"],
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("A", "legal"),
            _make_decision("B", "legal"),
            _make_decision("C", "fiscal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 3

    def test_caps_overrepresented_category(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When legal is >40%, at most 1 legal decision passes through."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 6 legal out of 10 → 60%
        _write_historical_results(
            data_dir, ["legal"] * 6 + ["fiscal"] * 2 + ["economy"] * 2,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Legal 1", "legal"),
            _make_decision("Legal 2", "legal"),
            _make_decision("Fiscal 1", "fiscal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 2
        # First legal kept, second dropped, fiscal kept
        assert result[0].title == "Legal 1"
        assert result[1].title == "Fiscal 1"

    def test_keeps_first_decision_in_overrepresented_category(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The first decision in an overrepresented category is always kept."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # legal at 50%
        _write_historical_results(
            data_dir, ["legal"] * 5 + ["fiscal"] * 5,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Legal 1", "legal"),
            _make_decision("Legal 2", "legal"),
            _make_decision("Legal 3", "legal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 1
        assert result[0].title == "Legal 1"

    def test_non_overrepresented_categories_unaffected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Categories below the threshold are not capped."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # legal at 60%, fiscal at 20%, economy at 20%
        _write_historical_results(
            data_dir, ["legal"] * 6 + ["fiscal"] * 2 + ["economy"] * 2,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Fiscal 1", "fiscal"),
            _make_decision("Fiscal 2", "fiscal"),
            _make_decision("Fiscal 3", "fiscal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 3  # fiscal is under threshold, all pass

    def test_empty_decisions_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty input returns empty output."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_historical_results(data_dir, ["legal"] * 10)
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        result = _enforce_category_caps([])
        assert result == []

    def test_logs_dropped_decisions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Dropped decisions are logged at INFO level."""
        import logging

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_historical_results(
            data_dir, ["legal"] * 6 + ["fiscal"] * 2 + ["economy"] * 2,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Legal 1", "legal"),
            _make_decision("Legal 2", "legal"),
        ]
        with caplog.at_level(logging.INFO):
            _enforce_category_caps(decisions)

        assert any("Category cap" in msg for msg in caplog.messages)
        assert any("Legal 2" in msg for msg in caplog.messages)

    def test_multiple_overrepresented_categories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Multiple categories can be overrepresented and capped independently."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # legal at 50%, fiscal at 50% — both over 40%
        _write_historical_results(
            data_dir, ["legal"] * 5 + ["fiscal"] * 5,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Legal 1", "legal"),
            _make_decision("Legal 2", "legal"),
            _make_decision("Fiscal 1", "fiscal"),
            _make_decision("Fiscal 2", "fiscal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 2
        cats = [d.category for d in result]
        assert cats.count("legal") == 1
        assert cats.count("fiscal") == 1

    def test_exactly_at_threshold_not_capped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A category at exactly the threshold (40%) is NOT capped (> not >=)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # legal at exactly 40% (4 out of 10)
        _write_historical_results(
            data_dir, ["legal"] * 4 + ["fiscal"] * 3 + ["economy"] * 3,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        decisions = [
            _make_decision("Legal 1", "legal"),
            _make_decision("Legal 2", "legal"),
        ]
        result = _enforce_category_caps(decisions)
        assert len(result) == 2  # 40% is not > 40%, so no cap

    def test_rescues_decision_when_all_dropped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When all decisions would be dropped, at least MIN_KEPT survives."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # economy at 50% — overrepresented
        _write_historical_results(
            data_dir, ["economy"] * 5 + ["fiscal"] * 5,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        # Both categories are overrepresented (50% each > 40%)
        # With max_per_fetch=1, economy gets 1 kept + 1 dropped,
        # fiscal gets 1 kept + 1 dropped → 2 kept, 2 dropped.
        # But if ALL decisions are from one overrepresented category:
        decisions = [
            _make_decision("Econ 1", "economy"),
            _make_decision("Econ 2", "economy"),
            _make_decision("Econ 3", "economy"),
        ]
        result = _enforce_category_caps(decisions)
        # Without rescue: would keep 1 (max_per_fetch). That's >= MIN_KEPT=1.
        assert len(result) >= CATEGORY_CAP_MIN_KEPT
        assert result[0].title == "Econ 1"

    def test_rescues_when_kept_is_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When cap would leave 0 items, rescue kicks in."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # economy at 60% — overrepresented
        _write_historical_results(
            data_dir, ["economy"] * 6 + ["legal"] * 4,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)

        # Monkeypatch MAX_PER_FETCH to 0 to force all drops
        monkeypatch.setattr("main_loop.CATEGORY_CAP_MAX_PER_FETCH", 0)

        decisions = [
            _make_decision("Econ 1", "economy"),
            _make_decision("Econ 2", "economy"),
        ]
        result = _enforce_category_caps(decisions)
        # Rescue should bring back at least 1
        assert len(result) >= CATEGORY_CAP_MIN_KEPT
        assert result[0].title == "Econ 1"

    def test_rescue_logs_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Rescued decisions are logged at INFO level."""
        import logging

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_historical_results(
            data_dir, ["economy"] * 6 + ["legal"] * 4,
        )
        monkeypatch.setattr("main_loop.DATA_DIR", data_dir)
        monkeypatch.setattr("main_loop.CATEGORY_CAP_MAX_PER_FETCH", 0)

        decisions = [_make_decision("Econ 1", "economy")]
        with caplog.at_level(logging.INFO):
            _enforce_category_caps(decisions)

        assert any("rescuing" in msg for msg in caplog.messages)
