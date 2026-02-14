"""Government decision model."""

import datetime

from pydantic import BaseModel, Field


class GovernmentDecision(BaseModel):
    """A real government decision to be analyzed by the AI cabinet."""

    id: str = Field(description="Unique identifier for the decision")
    title: str = Field(description="Official title of the decision")
    summary: str = Field(description="Brief summary of what the decision entails")
    full_text: str = Field(default="", description="Full text of the decision if available")
    date: datetime.date = Field(description="Date the decision was made or published")
    source_url: str = Field(default="", description="URL to the original source")
    category: str = Field(
        default="general",
        description="Category: fiscal, legal, eu, health, security, general",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
