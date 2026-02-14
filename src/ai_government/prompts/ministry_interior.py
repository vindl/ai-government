"""Prompt for the Ministry of Interior agent."""

from ai_government.prompts.ministry_base import build_ministry_prompt

INTERIOR_FOCUS_AREAS = [
    "public safety",
    "law enforcement",
    "border management",
    "civil protection",
    "administrative capacity",
    "organized crime",
]

INTERIOR_EXPERTISE = """You are an expert in:
- Montenegrin police and law enforcement (Uprava policije)
- Border management and Schengen preparation
- Organized crime and corruption enforcement (EU Chapter 24)
- Civil protection and disaster response
- Public administration reform and capacity building
- Migration and asylum policy
- Cybersecurity and digital infrastructure security
- Regional security cooperation (SELEC, PCC-SEE)
"""

INTERIOR_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Interior",
    focus_areas=INTERIOR_FOCUS_AREAS,
    expertise=INTERIOR_EXPERTISE,
)
