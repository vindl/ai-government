"""HTML helper functions — verdict labels, CSS classes, ministry name translations."""

from __future__ import annotations


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
    "Tourism": "turizma",
    "Environment": "ekologije",
}


def _ministry_name_mne(ministry_name: str) -> str:
    """Return the Montenegrin genitive form of a ministry name."""
    return _MINISTRY_NAME_MNE.get(ministry_name, ministry_name)
