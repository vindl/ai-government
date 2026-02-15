"""Static site builder — assembles scorecards, index, about, and feed pages."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import markdown as md
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from ai_government.models.override import HumanOverride, HumanSuggestion
from ai_government.orchestrator import SessionResult
from ai_government.output.html import _verdict_css_class, _verdict_label

if TYPE_CHECKING:
    import datetime

SITE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "site"
TEMPLATES_DIR = SITE_DIR / "templates"
STATIC_DIR = SITE_DIR / "static"
CONTENT_DIR = SITE_DIR / "content"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs"


def _create_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    env.filters["verdict_label"] = _verdict_label
    env.filters["verdict_css_class"] = _verdict_css_class
    return env


def load_results_from_dir(data_dir: Path) -> list[SessionResult]:
    """Load serialized SessionResult JSON files from a directory."""
    results: list[SessionResult] = []
    for path in sorted(data_dir.glob("*.json")):
        # Skip overrides.json (not a SessionResult)
        if path.name == "overrides.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = SessionResult.model_validate(raw)
        results.append(result)
    return results


def load_overrides_from_file(data_dir: Path) -> list[HumanOverride]:
    """Load human override records from overrides.json."""
    overrides_path = data_dir / "overrides.json"
    if not overrides_path.exists():
        return []

    raw_list = json.loads(overrides_path.read_text(encoding="utf-8"))
    return [HumanOverride.model_validate(item) for item in raw_list]


def load_suggestions_from_file(data_dir: Path) -> list[HumanSuggestion]:
    """Load human suggestion records from suggestions.json."""
    suggestions_path = data_dir / "suggestions.json"
    if not suggestions_path.exists():
        return []

    raw_list = json.loads(suggestions_path.read_text(encoding="utf-8"))
    return [HumanSuggestion.model_validate(item) for item in raw_list]


def save_result_json(result: SessionResult, output_dir: Path) -> Path:
    """Serialize a SessionResult to JSON. Returns the written path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.decision.id}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def _parse_announcement(path: Path) -> dict[str, Any]:
    """Parse a markdown announcement file.

    Expects filename format: YYYY-MM-DD_slug.md
    First line starting with # is the title.
    """
    text = path.read_text(encoding="utf-8")
    stem = path.stem
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    date_str = date_match.group(1) if date_match else ""

    lines = text.strip().splitlines()
    title = ""
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)

    html = md.markdown("\n".join(body_lines).strip())
    return {"date": date_str, "title": title, "html": Markup(html)}


class SiteBuilder:
    """Builds the complete static site from session results and content."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.env = _create_env()

    def build(self, results: list[SessionResult], data_dir: Path | None = None) -> None:
        """Build the full static site."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._copy_static()
        self._build_scorecards(results)
        self._build_index(results)
        self._build_about()
        self._build_feed()
        self._build_digests(results)

        # Build transparency page if data_dir is provided
        if data_dir is not None:
            overrides = load_overrides_from_file(data_dir)
            suggestions = load_suggestions_from_file(data_dir)
            self._build_transparency(overrides, suggestions)

    def _copy_static(self) -> None:
        dest = self.output_dir / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(STATIC_DIR), str(dest))

    def _build_scorecards(self, results: list[SessionResult]) -> None:
        decisions_dir = self.output_dir / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)

        template = self.env.get_template("scorecard.html")
        for result in results:
            html = template.render(
                result=result,
                css_path="../static/css/style.css",
                base_path="../",
            )
            path = decisions_dir / f"{result.decision.id}.html"
            path.write_text(html, encoding="utf-8")

        # Decisions index page
        sorted_results = sorted(results, key=lambda r: r.decision.date, reverse=True)
        index_template = self.env.get_template("decisions_index.html")
        html = index_template.render(
            results=sorted_results,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (decisions_dir / "index.html").write_text(html, encoding="utf-8")

    def _build_index(self, results: list[SessionResult]) -> None:
        # Sort by date descending
        sorted_results = sorted(results, key=lambda r: r.decision.date, reverse=True)
        template = self.env.get_template("index.html")
        html = template.render(
            results=sorted_results,
            css_path="static/css/style.css",
            base_path="",
        )
        (self.output_dir / "index.html").write_text(html, encoding="utf-8")

    def _build_about(self) -> None:
        about_dir = self.output_dir / "about"
        about_dir.mkdir(parents=True, exist_ok=True)

        constitution_path = DOCS_DIR / "CONSTITUTION.md"
        constitution_md = constitution_path.read_text(encoding="utf-8")
        constitution_html = Markup(md.markdown(constitution_md))

        template = self.env.get_template("about.html")
        html = template.render(
            constitution_html=constitution_html,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (about_dir / "index.html").write_text(html, encoding="utf-8")

    def _build_feed(self) -> None:
        announcements_dir = CONTENT_DIR / "announcements"
        announcements: list[dict[str, Any]] = []
        if announcements_dir.exists():
            for path in sorted(announcements_dir.glob("*.md"), reverse=True):
                announcements.append(_parse_announcement(path))

        feed_dir = self.output_dir / "news"
        feed_dir.mkdir(parents=True, exist_ok=True)
        template = self.env.get_template("feed.html")
        html = template.render(
            announcements=announcements,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (feed_dir / "index.html").write_text(html, encoding="utf-8")

    def _build_transparency(
        self, overrides: list[HumanOverride], suggestions: list[HumanSuggestion]
    ) -> None:
        """Build the human overrides transparency report page."""
        transparency_dir = self.output_dir / "transparency"
        transparency_dir.mkdir(parents=True, exist_ok=True)

        template = self.env.get_template("transparency.html")
        html = template.render(
            overrides=overrides,
            suggestions=suggestions,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (transparency_dir / "index.html").write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # Daily digests
    # ------------------------------------------------------------------

    @staticmethod
    def _group_results_by_date(
        results: list[SessionResult],
    ) -> dict[datetime.date, list[SessionResult]]:
        """Group session results by decision date."""
        grouped: dict[datetime.date, list[SessionResult]] = defaultdict(list)
        for r in results:
            grouped[r.decision.date].append(r)
        return dict(grouped)

    @staticmethod
    def _compose_digest_data(
        day: datetime.date,
        results: list[SessionResult],
    ) -> dict[str, Any]:
        """Compose template-ready data for a single day's digest."""
        decisions: list[dict[str, Any]] = []
        all_concerns: list[str] = []
        verdict_counts: Counter[str] = Counter()
        counter_proposal_count = 0
        score_sum = 0.0
        score_count = 0

        for r in results:
            # Determine score: prefer critic_report.decision_score, fall back to
            # average assessment score, then 0 if nothing available.
            if r.critic_report is not None:
                score = r.critic_report.decision_score
                headline = r.critic_report.headline
            elif r.assessments:
                score = round(
                    sum(a.score for a in r.assessments) / len(r.assessments)
                )
                headline = r.decision.summary
            else:
                score = 0
                headline = r.decision.summary

            has_cp = r.counter_proposal is not None
            if has_cp:
                counter_proposal_count += 1

            # Determine primary verdict from debate or first assessment
            verdict = ""
            if r.debate is not None:
                verdict = r.debate.overall_verdict.value
            elif r.assessments:
                verdict = r.assessments[0].verdict.value

            decisions.append(
                {
                    "id": r.decision.id,
                    "title": r.decision.title,
                    "score": score,
                    "headline": headline,
                    "verdict": verdict,
                    "has_counter_proposal": has_cp,
                }
            )

            score_sum += score
            score_count += 1

            # Collect concerns and verdicts from all assessments
            for a in r.assessments:
                all_concerns.extend(a.key_concerns)
                verdict_counts[a.verdict.value] += 1

        # Sort decisions by score ascending (worst first)
        decisions.sort(key=lambda d: d["score"])

        avg_score = round(score_sum / score_count, 1) if score_count else 0.0

        # Top 3 most common concerns
        concern_counter: Counter[str] = Counter(all_concerns)
        common_concerns = [c for c, _ in concern_counter.most_common(3)]

        lowest = decisions[0] if decisions else None
        highest = decisions[-1] if decisions and decisions[-1]["score"] >= 7 else None

        return {
            "date": day,
            "decision_count": len(results),
            "avg_score": avg_score,
            "decisions": decisions,
            "lowest_score_decision": lowest,
            "highest_score_decision": highest,
            "common_concerns": common_concerns,
            "verdict_distribution": dict(verdict_counts),
            "counter_proposal_count": counter_proposal_count,
        }

    def _build_digests(self, results: list[SessionResult]) -> None:
        """Build daily digest pages and a digest index page."""
        grouped = self._group_results_by_date(results)

        digest_template = self.env.get_template("digest.html")
        index_template = self.env.get_template("digest_index.html")

        digests: list[dict[str, Any]] = []

        for day in sorted(grouped):
            data = self._compose_digest_data(day, grouped[day])
            digests.append(data)

            day_dir = self.output_dir / "digest" / str(day)
            day_dir.mkdir(parents=True, exist_ok=True)
            html = digest_template.render(
                digest=data,
                css_path="../../static/css/style.css",
                base_path="../../",
            )
            (day_dir / "index.html").write_text(html, encoding="utf-8")

        # Digest index — always render (shows empty state when no digests)
        digests.sort(key=lambda d: d["date"], reverse=True)
        digest_dir = self.output_dir / "digest"
        digest_dir.mkdir(parents=True, exist_ok=True)
        html = index_template.render(
            digests=digests,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (digest_dir / "index.html").write_text(html, encoding="utf-8")
