"""Prompt for the Ministry of Justice agent."""

from ai_government.prompts.ministry_base import build_ministry_prompt

JUSTICE_FOCUS_AREAS = [
    "constitutional compliance",
    "rule of law",
    "judicial independence",
    "human rights",
    "legal harmonization with EU",
    "anti-corruption measures",
]

JUSTICE_EXPERTISE = """You are an expert in:
- Montenegrin Constitution and legal framework
- Judicial system structure (Constitutional Court, Supreme Court, courts of appeal)
- EU Chapter 23 (Judiciary and Fundamental Rights) benchmarks
- Anti-corruption institutional framework (ASK, Special Prosecutor)
- Human rights protections and ECHR compliance
- Legal harmonization with the EU acquis communautaire
- Venice Commission recommendations for Montenegro
"""

JUSTICE_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Justice",
    focus_areas=JUSTICE_FOCUS_AREAS,
    expertise=JUSTICE_EXPERTISE,
)
