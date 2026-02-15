"""Bilingual localization for site output.

Provides Montenegrin translations of UI labels and verdict strings.
Content translations (headlines, summaries) are stored on the Pydantic models
as ``*_mne`` fields and populated by the translation step in the pipeline.
"""

from __future__ import annotations

# Static UI label translations — Montenegrin (Latin script)
UI_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "decision_score": "Decision Score",
        "assessment_quality": "Assessment Quality",
        "ministry_verdicts": "Ministry Verdicts",
        "detailed_analyses": "Detailed Analyses",
        "ministry_of": "Ministry of",
        "executive_summary": "Executive Summary",
        "read_full_analysis": "Read full analysis",
        "key_concerns": "Key Concerns",
        "recommendations": "Recommendations",
        "counter_proposal_label": "Counter-proposal",
        "expected_benefits": "Expected benefits",
        "feasibility": "Feasibility",
        "parliamentary_debate": "Parliamentary Debate",
        "consensus": "Consensus",
        "disagreements": "Disagreements",
        "transcript": "Transcript",
        "independent_critical_analysis": "Independent Critical Analysis",
        "blind_spots": "Blind Spots",
        "ai_counter_proposal": "AI Government Counter-proposal",
        "key_differences": "Key Differences",
        "implementation_steps": "Implementation Steps",
        "risks_and_tradeoffs": "Risks and Trade-offs",
        "ministry_contributions": "Ministry Contributions",
        "error_report": "Found an error in this analysis?",
        "report_error": "Report an error",
        "date": "Date",
        "category": "Category",
        "source": "Source",
        "lang_toggle_label": "English",
    },
    "mne": {
        "decision_score": "Ocjena odluke",
        "assessment_quality": "Kvalitet analize",
        "ministry_verdicts": "Ocjene ministarstava",
        "detailed_analyses": "Detaljne analize",
        "ministry_of": "Ministarstvo",
        "executive_summary": "Kratak pregled",
        "read_full_analysis": "Pročitajte cijelu analizu",
        "key_concerns": "Ključne zabrinutosti",
        "recommendations": "Preporuke",
        "counter_proposal_label": "Kontraprijedlog",
        "expected_benefits": "Očekivane koristi",
        "feasibility": "Izvodljivost",
        "parliamentary_debate": "Parlamentarna debata",
        "consensus": "Konsenzus",
        "disagreements": "Neslaganja",
        "transcript": "Transkript",
        "independent_critical_analysis": "Nezavisna kritička analiza",
        "blind_spots": "Slijepe tačke",
        "ai_counter_proposal": "Kontraprijedlog AI Vlade",
        "key_differences": "Ključne razlike",
        "implementation_steps": "Koraci implementacije",
        "risks_and_tradeoffs": "Rizici i kompromisi",
        "ministry_contributions": "Doprinosi ministarstava",
        "error_report": "Pronašli ste grešku u ovoj analizi?",
        "report_error": "Prijavite grešku",
        "date": "Datum",
        "category": "Kategorija",
        "source": "Izvor",
        "lang_toggle_label": "Crnogorski",
    },
}

VERDICT_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "strongly_positive": "Strongly Positive",
        "positive": "Positive",
        "neutral": "Neutral",
        "negative": "Negative",
        "strongly_negative": "Strongly Negative",
    },
    "mne": {
        "strongly_positive": "Izrazito pozitivno",
        "positive": "Pozitivno",
        "neutral": "Neutralno",
        "negative": "Negativno",
        "strongly_negative": "Izrazito negativno",
    },
}


def verdict_label(verdict_value: str, lang: str = "en") -> str:
    """Return a human-readable verdict label for the given language."""
    labels = VERDICT_LABELS.get(lang, VERDICT_LABELS["en"])
    return labels.get(verdict_value, verdict_value)


def ui_label(key: str, lang: str = "en") -> str:
    """Return a UI label string for the given language."""
    labels = UI_LABELS.get(lang, UI_LABELS["en"])
    return labels.get(key, key)
