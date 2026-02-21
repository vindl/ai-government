"""Telemetry models for cycle instrumentation and JSONL I/O."""

from __future__ import annotations

import json
import traceback as _tb
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_MAX_AGE_DAYS = 30


class CyclePhaseResult(BaseModel):
    """Result of a single phase within a cycle."""

    phase: str = Field(description="Phase identifier (A, B, C, D, E, F)")
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

    # Phase F — Research Scout
    research_scout_ran: bool = False
    research_scout_issues_filed: int = 0

    # Yield — did this cycle produce a tangible outcome?
    cycle_yielded: bool = False

    # Meta
    human_overrides: int = 0
    tweet_posted: bool = False
    tweet_metrics_collected: int = 0  # number of tweets with metrics fetched
    phases: list[CyclePhaseResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Conductor
    conductor_reasoning: str = ""
    conductor_actions: list[str] = Field(default_factory=list)
    conductor_fallback: bool = False  # True if recovery agent was used
    conductor_replans: int = 0  # number of re-plan rounds in this cycle

    # Flags
    dry_run: bool = False


class ErrorEntry(BaseModel):
    """One structured runtime error, serialized as JSONL."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    step: str
    issue_number: int | None = None
    pr_number: int | None = None
    error_type: str = ""
    message: str = ""
    traceback: str = ""

    @classmethod
    def from_exception(
        cls,
        step: str,
        exc: BaseException,
        *,
        issue_number: int | None = None,
        pr_number: int | None = None,
    ) -> ErrorEntry:
        """Build an ErrorEntry from a caught exception."""
        return cls(
            step=step,
            issue_number=issue_number,
            pr_number=pr_number,
            error_type=type(exc).__name__,
            message=str(exc),
            traceback="".join(_tb.format_exception(exc)),
        )


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------


def _append_jsonl_rolling(path: Path, entry: str, *, max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> None:
    """Append a JSONL entry and prune entries older than *max_age_days*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                ts = obj.get("timestamp") or obj.get("started_at", "")
                if ts and datetime.fromisoformat(ts) >= cutoff:
                    lines.append(line)
            except (json.JSONDecodeError, ValueError):
                lines.append(line)  # keep unparseable lines
    lines.append(entry)
    path.write_text("\n".join(lines) + "\n")


def append_telemetry(path: Path, entry: CycleTelemetry, *, max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> None:
    """Append a single telemetry entry as one JSON line, pruning old entries."""
    _append_jsonl_rolling(path, entry.model_dump_json(), max_age_days=max_age_days)


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


def append_error(path: Path, entry: ErrorEntry, *, max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> None:
    """Append a single error entry as one JSON line, pruning old entries."""
    _append_jsonl_rolling(path, entry.model_dump_json(), max_age_days=max_age_days)


def load_errors(path: Path, *, last_n: int = 0) -> list[ErrorEntry]:
    """Load error entries from a JSONL file.

    Args:
        path: Path to the JSONL file.
        last_n: If > 0, return only the last N entries.
    """
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    if last_n > 0:
        lines = lines[-last_n:]
    entries: list[ErrorEntry] = []
    for line in lines:
        line = line.strip()
        if line:
            entries.append(ErrorEntry.model_validate_json(line))
    return entries
