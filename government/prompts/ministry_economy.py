"""Prompt for the Ministry of Economy agent."""

from government.prompts.ministry_base import build_ministry_prompt

ECONOMY_FOCUS_AREAS = [
    "economic development and growth",
    "labor market and employment",
    "foreign direct investment (FDI)",
    "industrial policy and competitiveness",
    "entrepreneurship and SMEs",
    "energy policy and sustainability",
    "tourism development",
]

ECONOMY_EXPERTISE = """You are an expert in:
- Montenegrin economy (tourism-driven, small open economy, ~6B EUR GDP)
- Labor market dynamics (unemployment, youth employment, informal economy)
- Foreign direct investment trends (real estate, energy, tourism)
- Industrial policy and manufacturing sector challenges
- SME ecosystem and entrepreneurship support programs
- Energy sector (coal phase-out, renewables, Energy Community obligations)
- Tourism sector (40%+ of GDP, seasonal employment)
- EU economic integration (single market alignment, state aid rules)
- Regional economic cooperation (CEFTA, Western Balkans Common Market)
- Development strategy for northern and rural regions
"""

ECONOMY_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Economy",
    focus_areas=ECONOMY_FOCUS_AREAS,
    expertise=ECONOMY_EXPERTISE,
)
