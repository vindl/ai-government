"""HTML scorecard renderer using Jinja2 templates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from ai_government.orchestrator import SessionResult

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "site" / "templates"


def _verdict_label(verdict_value: str) -> str:
    mapping = {
        "strongly_positive": "Strongly Positive",
        "positive": "Positive",
        "neutral": "Neutral",
        "negative": "Negative",
        "strongly_negative": "Strongly Negative",
    }
    return mapping.get(verdict_value, verdict_value)


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
    env.filters["verdict_css_class"] = _verdict_css_class
    return env


def render_scorecard_html(result: SessionResult, *, templates_dir: Path | None = None) -> str:
    """Render a session result as an HTML scorecard page."""
    env = _create_env(templates_dir)
    template = env.get_template("scorecard.html")
    return template.render(result=result)
