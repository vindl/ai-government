"""Static site builder — assembles scorecards, index, about, and feed pages."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import markdown as md
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from ai_government.orchestrator import SessionResult
from ai_government.output.html import _verdict_css_class, _verdict_label

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
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = SessionResult.model_validate(raw)
        results.append(result)
    return results


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

    def build(self, results: list[SessionResult]) -> None:
        """Build the full static site."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._copy_static()
        self._build_scorecards(results)
        self._build_index(results)
        self._build_about()
        self._build_feed()

    def _copy_static(self) -> None:
        dest = self.output_dir / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(STATIC_DIR), str(dest))

    def _build_scorecards(self, results: list[SessionResult]) -> None:
        decisions_dir = self.output_dir / "odluke"
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
        constitution_path = DOCS_DIR / "CONSTITUTION.md"
        if constitution_path.exists():
            constitution_md = constitution_path.read_text(encoding="utf-8")
            constitution_html = Markup(md.markdown(constitution_md))
        else:
            constitution_html = Markup("<p>Ustav projekta nije pronadjen.</p>")

        about_dir = self.output_dir / "o-projektu"
        about_dir.mkdir(parents=True, exist_ok=True)
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

        feed_dir = self.output_dir / "novosti"
        feed_dir.mkdir(parents=True, exist_ok=True)
        template = self.env.get_template("feed.html")
        html = template.render(
            announcements=announcements,
            css_path="../static/css/style.css",
            base_path="../",
        )
        (feed_dir / "index.html").write_text(html, encoding="utf-8")
