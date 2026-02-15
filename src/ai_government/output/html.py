"""HTML helper functions for Jinja2 templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ai_government.output.localization import verdict_label as _loc_verdict_label

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "site" / "templates"


def _verdict_label(verdict_value: str) -> str:
    return _loc_verdict_label(verdict_value, lang="en")


def _verdict_label_mne(verdict_value: str) -> str:
    return _loc_verdict_label(verdict_value, lang="mne")


def _verdict_css_class(verdict_value: str) -> str:
    mapping = {
        "strongly_positive": "verdict-strong-pos",
        "positive": "verdict-pos",
        "neutral": "verdict-neutral",
        "negative": "verdict-neg",
        "strongly_negative": "verdict-strong-neg",
    }
    return mapping.get(verdict_value, "")


def _create_env(templates_dir: Path | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir or TEMPLATES_DIR)),
        autoescape=True,
    )
    env.filters["verdict_label"] = _verdict_label
    env.filters["verdict_label_mne"] = _verdict_label_mne
    env.filters["verdict_css_class"] = _verdict_css_class
    return env
