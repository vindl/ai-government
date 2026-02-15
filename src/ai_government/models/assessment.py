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


class MinistryCounterProposal(BaseModel):
    """A ministry's alternative proposal for a government decision."""

    title: str = Field(description="Title of the counter-proposal")
    summary: str = Field(description="Brief summary of what the ministry would do differently")
    key_changes: list[str] = Field(default_factory=list, description="Concrete changes proposed")
    expected_benefits: list[str] = Field(
        default_factory=list, description="Expected benefits of this alternative"
    )
    estimated_feasibility: str = Field(
        default="", description="How feasible this alternative is"
    )


class Assessment(BaseModel):
    """A ministry agent's assessment of a government decision."""

    ministry: str = Field(description="Name of the assessing ministry")
    decision_id: str = Field(description="ID of the decision being assessed")
    verdict: Verdict = Field(description="Overall verdict")
    score: int = Field(ge=1, le=10, description="Score from 1 (worst) to 10 (best)")
    summary: str = Field(description="One-paragraph summary of the assessment")
    executive_summary: str | None = Field(
        default=None,
        description="2-3 sentence executive summary distilling verdict, top concerns, and key recommendation"
    )
    reasoning: str = Field(description="Detailed reasoning behind the assessment")
    key_concerns: list[str] = Field(default_factory=list, description="Key concerns identified")
    recommendations: list[str] = Field(default_factory=list, description="Recommendations for improvement")
    counter_proposal: MinistryCounterProposal | None = Field(
        default=None, description="Ministry's alternative proposal"
    )


class ParliamentDebate(BaseModel):
    """Synthesized parliamentary debate across all ministry assessments."""

    decision_id: str = Field(description="ID of the decision debated")
    consensus_summary: str = Field(description="Summary of where ministries agree")
    disagreements: list[str] = Field(default_factory=list, description="Key points of disagreement")
    overall_verdict: Verdict = Field(description="Parliament's collective verdict")
    debate_transcript: str = Field(description="Simulated debate transcript")


class CounterProposal(BaseModel):
    """Unified counter-proposal synthesized from all ministry alternatives."""

    decision_id: str = Field(description="ID of the decision this counter-proposal addresses")
    title: str = Field(description="Title of the unified counter-proposal")
    executive_summary: str = Field(description="Executive summary of the alternative approach")
    detailed_proposal: str = Field(description="Full detailed proposal text")
    ministry_contributions: list[str] = Field(
        default_factory=list, description="Which ministries contributed"
    )
    key_differences: list[str] = Field(
        default_factory=list, description="Key differences from the original"
    )
    implementation_steps: list[str] = Field(
        default_factory=list, description="Steps to implement this alternative"
    )
    risks_and_tradeoffs: list[str] = Field(
        default_factory=list, description="Risks and tradeoffs of this approach"
    )


class CriticReport(BaseModel):
    """Independent critic's report on a decision and its assessments."""

    decision_id: str = Field(description="ID of the decision reviewed")
    decision_score: int = Field(ge=1, le=10, description="Critic's score for the decision itself")
    assessment_quality_score: int = Field(ge=1, le=10, description="How well the ministries analyzed it")
    blind_spots: list[str] = Field(default_factory=list, description="What the ministries missed")
    overall_analysis: str = Field(description="Critic's independent analysis")
    headline: str = Field(description="Punchy headline for the scorecard")
