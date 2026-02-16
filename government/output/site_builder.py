"""Static site builder — assembles scorecards, index, constitution, and feed pages."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import markdown as md
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from pydantic import ValidationError

from government.models.override import HumanOverride, HumanSuggestion, PRMerge
from government.orchestrator import SessionResult
from government.output.html import _verdict_css_class, _verdict_label, _verdict_label_mne

SITE_DIR = Path(__file__).resolve().parent.parent.parent / "site"
TEMPLATES_DIR = SITE_DIR / "templates"
STATIC_DIR = SITE_DIR / "static"
CONTENT_DIR = SITE_DIR / "content"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


def _create_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    env.filters["verdict_label"] = _verdict_label
    env.filters["verdict_label_mne"] = _verdict_label_mne
    env.filters["verdict_css_class"] = _verdict_css_class
    return env


_logger = logging.getLogger(__name__)


def load_results_from_dir(data_dir: Path) -> list[SessionResult]:
    """Load serialized SessionResult JSON files from a directory.

    Non-SessionResult JSON files (e.g. overrides.json, suggestions.json) are
    silently skipped with a debug log message.
    """
    results: list[SessionResult] = []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            result = SessionResult.model_validate(raw)
        except ValidationError:
            _logger.debug("Skipping non-SessionResult file: %s", path.name)
            continue
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


def load_pr_merges_from_file(data_dir: Path) -> list[PRMerge]:
    """Load PR merge records from pr_merges.json."""
    merges_path = data_dir / "pr_merges.json"
    if not merges_path.exists():
        return []

    raw_list = json.loads(merges_path.read_text(encoding="utf-8"))
    return [PRMerge.model_validate(item) for item in raw_list]


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
        self._build_constitution()
        self._build_architecture()
        self._build_feed()

        # Build transparency page if data_dir is provided
        if data_dir is not None:
            overrides = load_overrides_from_file(data_dir)
            suggestions = load_suggestions_from_file(data_dir)
            pr_merges = load_pr_merges_from_file(data_dir)
            self._build_transparency(overrides, suggestions, pr_merges)

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

    def _build_constitution(self) -> None:
        constitution_dir = self.output_dir / "constitution"
        constitution_dir.mkdir(parents=True, exist_ok=True)

        constitution_path = DOCS_DIR / "CONSTITUTION.md"
        constitution_md = constitution_path.read_text(encoding="utf-8")
        constitution_html = Markup(md.markdown(constitution_md))

        template = self.env.get_template("constitution.html")
        html = template.render(
            constitution_html=constitution_html,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (constitution_dir / "index.html").write_text(html, encoding="utf-8")

    def _build_architecture(self) -> None:
        arch_dir = self.output_dir / "architecture"
        arch_dir.mkdir(parents=True, exist_ok=True)

        decisions_en = (DOCS_DIR / "DECISIONS.md").read_text(encoding="utf-8")
        decisions_mne = (DOCS_DIR / "DECISIONS_MNE.md").read_text(encoding="utf-8")

        template = self.env.get_template("architecture.html")
        html = template.render(
            architecture_html_en=Markup(md.markdown(decisions_en)),
            architecture_html_mne=Markup(md.markdown(decisions_mne)),
            css_path="../static/css/style.css",
            base_path="../",
        )
        (arch_dir / "index.html").write_text(html, encoding="utf-8")

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
        self,
        overrides: list[HumanOverride],
        suggestions: list[HumanSuggestion],
        pr_merges: list[PRMerge] | None = None,
    ) -> None:
        """Build the human overrides transparency report page."""
        transparency_dir = self.output_dir / "transparency"
        transparency_dir.mkdir(parents=True, exist_ok=True)

        # Merge overrides, suggestions, and PR merges into a single chronological list
        interventions: list[dict[str, Any]] = []
        for o in overrides:
            interventions.append({"type": "override", "item": o, "timestamp": o.timestamp})
        for s in suggestions:
            interventions.append({"type": "suggestion", "item": s, "timestamp": s.timestamp})
        for m in pr_merges or []:
            interventions.append({"type": "pr_merge", "item": m, "timestamp": m.timestamp})
        interventions.sort(key=lambda x: x["timestamp"], reverse=True)

        template = self.env.get_template("transparency.html")
        html = template.render(
            interventions=interventions,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (transparency_dir / "index.html").write_text(html, encoding="utf-8")

