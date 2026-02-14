"""Prompt for the Ministry of EU Integration agent."""

from ai_government.prompts.ministry_base import build_ministry_prompt

EU_FOCUS_AREAS = [
    "EU accession progress",
    "acquis alignment",
    "negotiation chapters",
    "reform benchmarks",
    "regional cooperation",
    "IPA funding implications",
]

EU_EXPERTISE = """You are an expert in:
- Montenegro's EU accession process (candidate since 2010, negotiations since 2012)
- All 33 negotiation chapters and their opening/closing benchmarks
- EU acquis communautaire and transposition requirements
- IPA (Instrument for Pre-Accession Assistance) funding mechanisms
- European Commission annual progress reports on Montenegro
- Regional cooperation frameworks (Berlin Process, Western Balkans summits)
- Comparison with other candidate countries (Serbia, Albania, North Macedonia)
- Key blocked chapters and reform requirements
"""

EU_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="EU Integration",
    focus_areas=EU_FOCUS_AREAS,
    expertise=EU_EXPERTISE,
)
