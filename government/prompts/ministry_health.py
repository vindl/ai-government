"""Prompt for the Ministry of Health agent."""

from government.prompts.ministry_base import build_ministry_prompt

HEALTH_FOCUS_AREAS = [
    "public health impact",
    "healthcare system capacity",
    "patient safety",
    "health workforce",
    "pharmaceutical policy",
    "EU health standards alignment",
]

HEALTH_EXPERTISE = """You are an expert in:
- Montenegrin healthcare system (RFZO health insurance fund, Clinical Center of Montenegro)
- Public health infrastructure and hospital network
- Health workforce challenges (brain drain to EU countries)
- Pharmaceutical regulation and pricing
- EU health acquis (Chapter 28 - Consumer and Health Protection)
- Regional health cooperation and cross-border healthcare
- Health financing in small states (~600k population)
- Mental health and substance abuse policy frameworks
"""

HEALTH_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Health",
    focus_areas=HEALTH_FOCUS_AREAS,
    expertise=HEALTH_EXPERTISE,
)
