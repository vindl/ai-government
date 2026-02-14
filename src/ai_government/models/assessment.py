"""Assessment and verdict models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    """Overall verdict on a government decision."""

    STRONGLY_POSITIVE = "strongly_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    STRONGLY_NEGATIVE = "strongly_negative"


class Assessment(BaseModel):
    """A ministry agent's assessment of a government decision."""

    ministry: str = Field(description="Name of the assessing ministry")
    decision_id: str = Field(description="ID of the decision being assessed")
    verdict: Verdict = Field(description="Overall verdict")
    score: int = Field(ge=1, le=10, description="Score from 1 (worst) to 10 (best)")
    summary: str = Field(description="One-paragraph summary of the assessment")
    reasoning: str = Field(description="Detailed reasoning behind the assessment")
    key_concerns: list[str] = Field(default_factory=list, description="Key concerns identified")
    recommendations: list[str] = Field(default_factory=list, description="Recommendations for improvement")


class ParliamentDebate(BaseModel):
    """Synthesized parliamentary debate across all ministry assessments."""

    decision_id: str = Field(description="ID of the decision debated")
    consensus_summary: str = Field(description="Summary of where ministries agree")
    disagreements: list[str] = Field(default_factory=list, description="Key points of disagreement")
    overall_verdict: Verdict = Field(description="Parliament's collective verdict")
    debate_transcript: str = Field(description="Simulated debate transcript")


class CriticReport(BaseModel):
    """Independent critic's report on a decision and its assessments."""

    decision_id: str = Field(description="ID of the decision reviewed")
    decision_score: int = Field(ge=1, le=10, description="Critic's score for the decision itself")
    assessment_quality_score: int = Field(ge=1, le=10, description="How well the ministries analyzed it")
    blind_spots: list[str] = Field(default_factory=list, description="What the ministries missed")
    overall_analysis: str = Field(description="Critic's independent analysis")
    headline: str = Field(description="Punchy headline for the scorecard")
