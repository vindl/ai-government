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
    # Montenegrin translations (populated by localization step)
    title_mne: str = Field(default="", description="Montenegrin translation of title")
    summary_mne: str = Field(default="", description="Montenegrin translation of summary")
    key_changes_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of key_changes"
    )
    expected_benefits_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of expected_benefits"
    )
    estimated_feasibility_mne: str = Field(
        default="", description="Montenegrin translation of estimated_feasibility"
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
    # Montenegrin translations (populated by localization step)
    summary_mne: str = Field(default="", description="Montenegrin translation of summary")
    executive_summary_mne: str | None = Field(
        default=None, description="Montenegrin translation of executive_summary"
    )
    key_concerns_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of key_concerns"
    )
    recommendations_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of recommendations"
    )


class ParliamentDebate(BaseModel):
    """Synthesized parliamentary debate across all ministry assessments."""

    decision_id: str = Field(description="ID of the decision debated")
    consensus_summary: str = Field(description="Summary of where ministries agree")
    disagreements: list[str] = Field(default_factory=list, description="Key points of disagreement")
    overall_verdict: Verdict = Field(description="Parliament's collective verdict")
    debate_transcript: str = Field(description="Simulated debate transcript")
    # Montenegrin translations (populated by localization step)
    consensus_summary_mne: str = Field(default="", description="Montenegrin translation of consensus_summary")
    disagreements_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of disagreements"
    )


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
    # Montenegrin translations (populated by localization step)
    title_mne: str = Field(default="", description="Montenegrin translation of title")
    executive_summary_mne: str = Field(default="", description="Montenegrin translation of executive_summary")
    detailed_proposal_mne: str = Field(default="", description="Montenegrin translation of detailed_proposal")
    ministry_contributions_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of ministry_contributions"
    )
    key_differences_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of key_differences"
    )
    implementation_steps_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of implementation_steps"
    )
    risks_and_tradeoffs_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of risks_and_tradeoffs"
    )


class CriticReport(BaseModel):
    """Independent critic's report on a decision and its assessments."""

    decision_id: str = Field(description="ID of the decision reviewed")
    decision_score: int = Field(ge=1, le=10, description="Critic's score for the decision itself")
    assessment_quality_score: int = Field(ge=1, le=10, description="How well the ministries analyzed it")
    blind_spots: list[str] = Field(default_factory=list, description="What the ministries missed")
    overall_analysis: str = Field(description="Critic's independent analysis")
    headline: str = Field(description="Punchy headline for the scorecard")
    # Montenegrin translations (populated by localization step)
    headline_mne: str = Field(default="", description="Montenegrin translation of headline")
    overall_analysis_mne: str = Field(default="", description="Montenegrin translation of overall_analysis")
    blind_spots_mne: list[str] = Field(
        default_factory=list, description="Montenegrin translation of blind_spots"
    )
