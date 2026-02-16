"""HTML helper functions for Jinja2 templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "site" / "templates"


def _verdict_label(verdict_value: str) -> str:
    mapping = {
        "strongly_positive": "Strongly Positive",
        "positive": "Positive",
        "neutral": "Neutral",
        "negative": "Negative",
        "strongly_negative": "Strongly Negative",
    }
    return mapping.get(verdict_value, verdict_value)


def _verdict_label_mne(verdict_value: str) -> str:
    mapping = {
        "strongly_positive": "Izrazito pozitivno",
        "positive": "Pozitivno",
        "neutral": "Neutralno",
        "negative": "Negativno",
        "strongly_negative": "Izrazito negativno",
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


_MINISTRY_NAME_MNE: dict[str, str] = {
    "Finance": "finansija",
    "Justice": "pravde",
    "EU Integration": "evropskih integracija",
    "Health": "zdravlja",
    "Interior": "unutrašnjih poslova",
    "Education": "prosvjete",
    "Economy": "ekonomije",
}


def _ministry_name_mne(ministry_name: str) -> str:
    """Return the Montenegrin genitive form of a ministry name."""
    return _MINISTRY_NAME_MNE.get(ministry_name, ministry_name)


def _create_env(templates_dir: Path | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir or TEMPLATES_DIR)),
        autoescape=True,
    )
    env.filters["verdict_label"] = _verdict_label
    env.filters["verdict_label_mne"] = _verdict_label_mne
    env.filters["verdict_css_class"] = _verdict_css_class
    env.filters["ministry_name_mne"] = _ministry_name_mne
    return env
