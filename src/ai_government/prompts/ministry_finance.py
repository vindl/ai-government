"""Prompt for the Ministry of Finance agent."""

from ai_government.prompts.ministry_base import build_ministry_prompt

FINANCE_FOCUS_AREAS = [
    "fiscal policy",
    "budget impact",
    "public debt",
    "tax implications",
    "economic growth",
    "foreign investment",
    "EU economic criteria",
]

FINANCE_EXPERTISE = """You are an expert in:
- Montenegrin fiscal policy and public finance (budget ~2B EUR)
- Tax system (VAT, corporate tax, income tax)
- Public debt management (debt-to-GDP ratio)
- EU economic convergence criteria (Maastricht)
- Regional economic dynamics (Western Balkans)
- Montenegro's euroization (uses EUR without ECB membership)
- Capital investment programs and PPP frameworks
"""

FINANCE_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Finance",
    focus_areas=FINANCE_FOCUS_AREAS,
    expertise=FINANCE_EXPERTISE,
)
