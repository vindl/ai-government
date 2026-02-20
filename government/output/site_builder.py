"""Static site builder — exports JSON data files and builds the React SPA."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import markdown as md
from pydantic import ValidationError

from government.models.override import HumanOverride, HumanSuggestion, PRMerge
from government.orchestrator import SessionResult

SITE_DIR = Path(__file__).resolve().parent.parent.parent / "site"
CONTENT_DIR = SITE_DIR / "content"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

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
    return {"date": date_str, "title": title, "html": html}


class SiteBuilder:
    """Builds the complete static site by exporting JSON and building the React SPA."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def build(self, results: list[SessionResult], data_dir: Path | None = None) -> None:
        """Build the full static site.

        1. Export JSON data files to site/public/data/
        2. Run npm build in site/
        3. Copy dist/ to output directory
        4. Create 404.html for SPA routing on GitHub Pages
        """
        json_output_dir = SITE_DIR / "public" / "data"

        # Step 1: Export JSON data (lazy import to avoid circular dependency)
        from government.output.json_export import export_json

        _logger.info("Exporting JSON data to %s", json_output_dir)
        export_json(results, data_dir, json_output_dir)

        # Step 2: Run npm build
        _logger.info("Running npm build in %s", SITE_DIR)
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(SITE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            _logger.error("npm build failed:\n%s\n%s", result.stdout, result.stderr)
            msg = f"npm build failed with exit code {result.returncode}"
            raise RuntimeError(msg)
        _logger.info("npm build succeeded")

        # Step 3: Copy dist/ to output directory
        dist_dir = SITE_DIR / "dist"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        shutil.copytree(str(dist_dir), str(self.output_dir))
        _logger.info("Copied dist/ to %s", self.output_dir)

        # Step 4: Create 404.html for SPA routing
        index_html = self.output_dir / "index.html"
        four_oh_four = self.output_dir / "404.html"
        if index_html.exists():
            shutil.copy2(str(index_html), str(four_oh_four))
            _logger.info("Created 404.html for SPA routing")
