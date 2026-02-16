"""Prompt for the Ministry of Education agent."""

from government.prompts.ministry_base import build_ministry_prompt

EDUCATION_FOCUS_AREAS = [
    "basic and secondary education quality",
    "higher education and research",
    "student welfare and equity",
    "teacher training and workforce",
    "vocational education and training (VET)",
    "EU education standards alignment",
    "brain drain mitigation",
]

EDUCATION_EXPERTISE = """You are an expert in:
- Montenegrin education system (primary, secondary, higher education)
- University of Montenegro and private universities
- Vocational education and training (VET) framework
- Teacher training and professional development
- Student mobility and brain drain challenges
- EU education acquis (Bologna Process, Erasmus+)
- PISA and other international education assessments
- Multilingual education (Montenegrin, minority languages)
- Education financing and infrastructure in small states (~600k population)
- Regional cooperation (Western Balkans education reform)
"""

EDUCATION_SYSTEM_PROMPT = build_ministry_prompt(
    ministry_name="Education",
    focus_areas=EDUCATION_FOCUS_AREAS,
    expertise=EDUCATION_EXPERTISE,
)
