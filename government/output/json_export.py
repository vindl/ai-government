"""Export analysis data as static JSON files for the React site."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import markdown as md

if TYPE_CHECKING:
    from government.models.override import HumanOverride, HumanSuggestion, PRMerge
    from government.orchestrator import SessionResult

from government.output.html import _verdict_label, _verdict_label_mne
from government.output.site_builder import (
    _parse_announcement,
    load_overrides_from_file,
    load_pr_merges_from_file,
    load_suggestions_from_file,
)

_logger = logging.getLogger(__name__)

SITE_DIR = Path(__file__).resolve().parent.parent.parent / "site"
CONTENT_DIR = SITE_DIR / "content"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


def _read_md_pair(en_name: str, mne_name: str) -> dict[str, str]:
    """Read an EN/MNE markdown pair from docs/ and render to HTML."""
    en_path = DOCS_DIR / en_name
    mne_path = DOCS_DIR / mne_name
    en_html = ""
    mne_html = ""
    if en_path.exists():
        en_html = md.markdown(en_path.read_text(encoding="utf-8"), extensions=["tables"])
    if mne_path.exists():
        mne_html = md.markdown(mne_path.read_text(encoding="utf-8"), extensions=["tables"])
    return {"en": en_html, "mne": mne_html}


def _build_analysis_summary(result: SessionResult) -> dict[str, Any]:
    """Build a summary object for the analyses index."""
    critic = result.critic_report
    decision = result.decision
    overall_verdict = result.debate.overall_verdict if result.debate else None
    return {
        "id": decision.id,
        "title": decision.title,
        "title_mne": decision.title_mne,
        "summary": decision.summary,
        "summary_mne": decision.summary_mne,
        "date": decision.date.isoformat(),
        "category": decision.category,
        "source_url": decision.source_url,
        "decision_score": critic.decision_score if critic else None,
        "headline": critic.headline if critic else "",
        "headline_mne": critic.headline_mne if critic else "",
        "overall_verdict": overall_verdict,
        "verdict_label": _verdict_label(overall_verdict) if overall_verdict else "",
        "verdict_label_mne": _verdict_label_mne(overall_verdict) if overall_verdict else "",
        "issue_number": result.issue_number,
    }


def _build_transparency(
    overrides: list[HumanOverride],
    suggestions: list[HumanSuggestion],
    pr_merges: list[PRMerge],
) -> dict[str, Any]:
    """Build the transparency JSON payload."""
    interventions: list[dict[str, Any]] = []

    for o in overrides:
        interventions.append({
            "type": "override",
            "timestamp": o.timestamp.isoformat(),
            "issue_number": o.issue_number,
            "pr_number": o.pr_number,
            "issue_title": o.issue_title,
            "actor": o.actor,
            "ai_verdict": o.ai_verdict,
            "human_action": o.human_action,
            "rationale": o.rationale,
        })

    for s in suggestions:
        interventions.append({
            "type": "suggestion",
            "timestamp": s.timestamp.isoformat(),
            "issue_number": s.issue_number,
            "issue_title": s.issue_title,
            "status": s.status,
            "creator": s.creator,
        })

    for m in pr_merges:
        interventions.append({
            "type": "pr_merge",
            "timestamp": m.timestamp.isoformat(),
            "pr_number": m.pr_number,
            "pr_title": m.pr_title,
            "actor": m.actor,
            "issue_number": m.issue_number,
        })

    # Sort newest first
    interventions.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"interventions": interventions, "total": len(interventions)}


def _build_announcements() -> list[dict[str, Any]]:
    """Parse announcement markdown files into JSON-safe dicts."""
    announcements_dir = CONTENT_DIR / "announcements"
    result: list[dict[str, Any]] = []
    if not announcements_dir.exists():
        return result

    for path in sorted(announcements_dir.glob("*.md"), reverse=True):
        if path.stem.endswith("_mne"):
            continue
        ann = _parse_announcement(path)
        # Convert Markup to str for JSON serialization
        entry: dict[str, Any] = {
            "date": ann["date"],
            "title": ann["title"],
            "html": str(ann["html"]),
        }
        # Look for Montenegrin companion
        mne_path = path.with_name(f"{path.stem}_mne.md")
        if mne_path.exists():
            mne = _parse_announcement(mne_path)
            entry["title_mne"] = mne["title"]
            entry["html_mne"] = str(mne["html"])
        else:
            entry["title_mne"] = entry["title"]
            entry["html_mne"] = entry["html"]
        result.append(entry)

    return result


def export_json(
    results: list[SessionResult],
    data_dir: Path | None,
    output_dir: Path,
) -> None:
    """Export all data as static JSON files into output_dir.

    Args:
        results: Loaded SessionResult objects.
        data_dir: Directory containing overrides/suggestions/pr_merges JSON.
        output_dir: Target directory (typically site/public/data/).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    analyses_dir = output_dir / "analyses"
    analyses_dir.mkdir(parents=True, exist_ok=True)

    # Sort by date descending
    sorted_results = sorted(results, key=lambda r: r.decision.date, reverse=True)

    # 1. Analyses index
    index = [_build_analysis_summary(r) for r in sorted_results]
    _write_json(output_dir / "analyses-index.json", index)
    _logger.info("Wrote analyses-index.json (%d analyses)", len(index))

    # 2. Individual analysis files
    for result in sorted_results:
        data = json.loads(result.model_dump_json())
        _write_json(analyses_dir / f"{result.decision.id}.json", data)
    _logger.info("Wrote %d individual analysis files", len(sorted_results))

    # 3. Documentation pages
    _write_json(
        output_dir / "constitution.json",
        _read_md_pair("CONSTITUTION.md", "CONSTITUTION_MNE.md"),
    )
    _write_json(
        output_dir / "architecture.json",
        _read_md_pair("DECISIONS.md", "DECISIONS_MNE.md"),
    )
    _write_json(
        output_dir / "cabinet.json",
        _read_md_pair("CABINET.md", "CABINET_MNE.md"),
    )
    _write_json(
        output_dir / "challenges.json",
        _read_md_pair("CHALLENGES.md", "CHALLENGES_MNE.md"),
    )
    _logger.info("Wrote documentation JSON files")

    # 4. Transparency
    if data_dir is not None:
        overrides = load_overrides_from_file(data_dir)
        suggestions = load_suggestions_from_file(data_dir)
        pr_merges = load_pr_merges_from_file(data_dir)
        _write_json(
            output_dir / "transparency.json",
            _build_transparency(overrides, suggestions, pr_merges),
        )
        _logger.info("Wrote transparency.json")

    # 5. Announcements
    announcements = _build_announcements()
    _write_json(output_dir / "announcements.json", announcements)
    _logger.info("Wrote announcements.json (%d announcements)", len(announcements))


def _write_json(path: Path, data: Any) -> None:
    """Write JSON data to a file."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
