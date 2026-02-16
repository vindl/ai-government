"""Data models for human override tracking and transparency reporting."""

from __future__ import annotations

import datetime  # noqa: TC003  # Pydantic requires runtime import for datetime fields
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HumanOverride(BaseModel):
    """Record of a human override in the AI pipeline.

    Captures when and how a human intervened to override an AI decision.
    Published in the transparency report per Constitution Article 5 and 22.
    """

    timestamp: datetime.datetime = Field(
        description="When the override occurred (UTC)",
    )
    issue_number: int = Field(description="GitHub issue number")
    pr_number: int | None = Field(
        default=None, description="GitHub PR number (if applicable)"
    )
    override_type: Literal["reopened", "comment", "pr_comment"] = Field(
        description="How the override was triggered"
    )
    actor: str = Field(description="GitHub username of the person who overrode")
    issue_title: str = Field(description="Issue title")
    ai_verdict: str = Field(
        description="What the AI proposed (e.g., 'Rejected', 'Changes requested')"
    )
    human_action: str = Field(
        description="What the human did (e.g., 'Reopened and moved to backlog', 'Approved')"
    )
    rationale: str | None = Field(
        default=None,
        description="Brief explanation from the override comment (optional)",
    )

    model_config = ConfigDict(frozen=True)


class PRMerge(BaseModel):
    """Record of a human merging an AI-generated pull request.

    Tracks when humans review and approve AI code for deployment.
    Published in the transparency report per Constitution Article 5 and 22.
    """

    timestamp: datetime.datetime = Field(
        description="When the PR was merged (UTC)",
    )
    pr_number: int = Field(description="GitHub PR number")
    pr_title: str = Field(description="PR title")
    actor: str = Field(description="GitHub username who merged the PR")
    issue_number: int | None = Field(
        default=None, description="Linked issue number (if any)"
    )

    model_config = ConfigDict(frozen=True)


class HumanSuggestion(BaseModel):
    """Record of a task directly filed by a human operator.

    Tracks human-directed work to demonstrate transparency about what
    humans are asking the AI to do. Published in the transparency report
    per Constitution Article 5 and 22.
    """

    timestamp: datetime.datetime = Field(
        description="When the issue was created (UTC)",
    )
    issue_number: int = Field(description="GitHub issue number")
    issue_title: str = Field(description="Issue title")
    status: Literal["open", "closed"] = Field(
        description="Current issue state (open/closed)"
    )
    creator: str = Field(description="GitHub username who created the issue")

    model_config = ConfigDict(frozen=True)
