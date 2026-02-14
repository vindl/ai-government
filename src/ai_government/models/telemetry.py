"""Telemetry models for cycle instrumentation and JSONL I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


class CyclePhaseResult(BaseModel):
    """Result of a single phase within a cycle."""

    phase: str = Field(description="Phase identifier (A, B, C, D, E)")
    success: bool = Field(default=True)
    duration_seconds: float = Field(default=0.0)
    detail: str = Field(default="")


class CycleTelemetry(BaseModel):
    """One telemetry entry per main-loop cycle, serialized as JSONL."""

    cycle: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_seconds: float = 0.0

    # Phase A — government decision analysis
    decisions_found: int = 0
    analysis_issues_created: int = 0

    # Phase B — self-improvement (propose + debate)
    proposals_made: int = 0
    proposals_accepted: int = 0
    proposals_rejected: int = 0
    human_suggestions_ingested: int = 0

    # Phase C — execution
    picked_issue_number: int | None = None
    picked_issue_type: str | None = None
    execution_success: bool | None = None

    # Phase D — Project Director
    director_ran: bool = False
    director_issues_filed: int = 0

    # Phase E — Strategic Director
    strategic_director_ran: bool = False
    strategic_director_issues_filed: int = 0

    # Yield — did this cycle produce a tangible outcome?
    cycle_yielded: bool = False

    # Meta
    human_overrides: int = 0
    tweet_posted: bool = False
    phases: list[CyclePhaseResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Flags
    dry_run: bool = False
    skip_analysis: bool = False
    skip_improve: bool = False


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------


def append_telemetry(path: Path, entry: CycleTelemetry) -> None:
    """Append a single telemetry entry as one JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


def load_telemetry(path: Path, *, last_n: int = 0) -> list[CycleTelemetry]:
    """Load telemetry entries from a JSONL file.

    Args:
        path: Path to the JSONL file.
        last_n: If > 0, return only the last N entries.
    """
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    if last_n > 0:
        lines = lines[-last_n:]
    entries: list[CycleTelemetry] = []
    for line in lines:
        line = line.strip()
        if line:
            entries.append(CycleTelemetry.model_validate_json(line))
    return entries
