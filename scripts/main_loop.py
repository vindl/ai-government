#!/usr/bin/env python3
"""Unified main loop for the AI Government project.

Runs an indefinite cycle with three phases:
  Phase A: Check for new government decisions → create analysis issues
  Phase B: Self-improvement — propose improvements → debate/triage
  Phase C: Pick from unified backlog → execute (routes by task type)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import anyio
import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from government.agents.json_parsing import retry_prompt
from government.config import SessionConfig
from government.models.override import HumanOverride, HumanSuggestion, PRMerge
from government.models.telemetry import (
    CyclePhaseResult,
    CycleTelemetry,
    ErrorEntry,
    append_error,
    append_telemetry,
    load_errors,
    load_telemetry,
)
from government.orchestrator import Orchestrator, SessionResult
from government.output.scorecard import render_scorecard
from government.output.site_builder import load_results_from_dir, save_result_json
from government.output.twitter import (
    load_unposted_from_dir,
    post_tweet_backlog,
    try_post_analysis,
)
from government.session import load_decisions
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from government.models.decision import GovernmentDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_COOLDOWN_SECONDS = 60
AGENT_TIMEOUT_SECONDS = 600  # 10 minutes — kill hung SDK subprocesses
DEFAULT_PROPOSALS_PER_CYCLE = 1
DEFAULT_MAX_PR_ROUNDS = 0  # 0 = unlimited
DEFAULT_DIRECTOR_INTERVAL = 5
DEFAULT_STRATEGIC_DIRECTOR_INTERVAL = 10
DIRECTOR_MAX_TURNS = 10
STRATEGIC_DIRECTOR_MAX_TURNS = 10
EDITORIAL_DIRECTOR_MAX_TURNS = 8
ERROR_PATTERN_WINDOW = 5
ERROR_PATTERN_THRESHOLD = 3
CIRCUIT_BREAKER_THRESHOLD = 3
MAX_BACKOFF_SECONDS = 1800  # 30 minutes
SDK_RETRY_ATTEMPTS = 3  # retries *after* the first attempt (4 total tries)
SDK_RETRY_BASE_DELAY = 5  # seconds between retries (exponential: 5, 10, 20)

# Signatures that indicate a transient SDK/API outage (not a code bug).
# These should NOT trigger the circuit breaker.
SDK_TRANSIENT_SIGNATURES = frozenset({
    "Command failed with exit code 1",
    "exit code: 1",
    "timed out",
})

LABEL_PROPOSED = "self-improve:proposed"
LABEL_BACKLOG = "self-improve:backlog"
LABEL_REJECTED = "self-improve:rejected"
LABEL_IN_PROGRESS = "self-improve:in-progress"
LABEL_DONE = "self-improve:done"
LABEL_FAILED = "self-improve:failed"
LABEL_URGENT = "priority:urgent"
LABEL_HUMAN = "human-suggestion"
LABEL_DIRECTOR = "director-suggestion"
LABEL_STRATEGY = "strategy-suggestion"
LABEL_EDITORIAL = "editorial-quality"
LABEL_TASK_ANALYSIS = "task:analysis"
LABEL_TASK_CODE = "task:code-change"
LABEL_CI_FAILURE = "ci-failure"
LABEL_TASK_FIX = "task:fix"
LABEL_GAP_CONTENT = "gap:content"
LABEL_GAP_TECHNICAL = "gap:technical"
LABEL_RESEARCH_SCOUT = "research-scout"

ALL_LABELS: dict[str, str] = {
    LABEL_PROPOSED: "808080",    # gray
    LABEL_BACKLOG: "0e8a16",     # green
    LABEL_REJECTED: "e67e22",    # orange
    LABEL_IN_PROGRESS: "fbca04",  # yellow
    LABEL_DONE: "6f42c1",       # purple
    LABEL_FAILED: "d73a4a",     # red
    LABEL_URGENT: "e11d48",     # urgent red (drop everything)
    LABEL_HUMAN: "0075ca",      # blue
    LABEL_DIRECTOR: "d876e3",    # purple (sage)
    LABEL_STRATEGY: "f9a825",    # amber (reserved for #83)
    LABEL_EDITORIAL: "c5def5",   # pale blue
    LABEL_TASK_ANALYSIS: "1d76db",  # light blue
    LABEL_TASK_CODE: "5319e7",      # violet
    LABEL_CI_FAILURE: "b60205",     # red (CI failure)
    LABEL_TASK_FIX: "ff6347",       # tomato (high-priority fix task)
    LABEL_GAP_CONTENT: "c2e0c6",    # light green (content gap observation)
    LABEL_GAP_TECHNICAL: "d4c5f9",  # light purple (technical gap observation)
    LABEL_RESEARCH_SCOUT: "40e0d0",  # turquoise (research scout)
    # Analysis lifecycle labels (separate from self-improve:*)
    "analysis:pending": "c5def5",      # pale blue
    "analysis:in-progress": "fbca04",  # yellow
    "analysis:done": "6f42c1",         # purple
    "analysis:failed": "d73a4a",       # red
}

# Unset CLAUDECODE so spawned SDK subprocesses don't refuse to launch.
# Also clear ANTHROPIC_API_KEY so the subprocess uses OAuth.
SDK_ENV = {"CLAUDECODE": "", "ANTHROPIC_API_KEY": ""}

PROPOSE_MAX_TURNS = 10
DEBATE_MAX_TURNS = 5
PROPOSE_TOOLS = ["Bash", "Read", "Glob", "Grep"]

PRIVILEGED_PERMISSIONS = {"admin", "maintain"}

SEED_DECISIONS_PATH = PROJECT_ROOT / "data" / "seed" / "sample_decisions.json"
TELEMETRY_PATH = PROJECT_ROOT / "output" / "data" / "telemetry.jsonl"
ERRORS_PATH = PROJECT_ROOT / "output" / "data" / "errors.jsonl"
DATA_DIR = PROJECT_ROOT / "output" / "data"

NEWS_SCOUT_MAX_TURNS = 20
NEWS_SCOUT_TOOLS = ["WebSearch", "WebFetch"]
NEWS_SCOUT_STATE_PATH = PROJECT_ROOT / "output" / "news_scout_state.json"
NEWS_SCOUT_MAX_DECISIONS = 3
ANALYSIS_STATE_PATH = PROJECT_ROOT / "output" / "analysis_state.json"
CONDUCTOR_JOURNAL_PATH = PROJECT_ROOT / "output" / "data" / "conductor_journal.jsonl"

RESEARCH_SCOUT_MAX_TURNS = 15
RESEARCH_SCOUT_TOOLS = ["WebSearch", "WebFetch"]
RESEARCH_SCOUT_STATE_PATH = PROJECT_ROOT / "output" / "research_scout_state.json"
RESEARCH_SCOUT_MAX_ISSUES = 5
DEFAULT_RESEARCH_SCOUT_INTERVAL_DAYS = 1

# Analysis rate limiting — can be overridden via CLI or env vars
DEFAULT_MAX_ANALYSES_PER_DAY = int(os.getenv("LOOP_MAX_ANALYSES_PER_DAY", "5"))
DEFAULT_MIN_ANALYSIS_GAP_HOURS = int(os.getenv("LOOP_MIN_ANALYSIS_GAP_HOURS", "2"))

log = logging.getLogger("main_loop")

# Lazy-resolve at first use to avoid import-time coupling with pr_workflow.
_InfrastructureError: type[Exception] | None = None


def _get_infrastructure_error() -> type[Exception]:
    """Import InfrastructureError from pr_workflow on first use."""
    global _InfrastructureError  # noqa: PLW0603
    if _InfrastructureError is None:
        from pr_workflow import InfrastructureError
        _InfrastructureError = InfrastructureError
    return _InfrastructureError


# ---------------------------------------------------------------------------
# Structured error logging
# ---------------------------------------------------------------------------


def _log_error(
    step: str,
    exc: BaseException,
    *,
    issue_number: int | None = None,
    pr_number: int | None = None,
) -> None:
    """Persist a runtime error to the structured error log (errors.jsonl)."""
    try:
        entry = ErrorEntry.from_exception(
            step,
            exc,
            issue_number=issue_number,
            pr_number=pr_number,
        )
        append_error(ERRORS_PATH, entry)
    except Exception:
        # Never let error logging itself break the main loop
        log.debug("Failed to persist error entry", exc_info=True)


# ---------------------------------------------------------------------------
# Agent output schemas (for structured validation)
# ---------------------------------------------------------------------------


class ProposalOutput(BaseModel):
    """Validated output from PM agent."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    domain: str = Field(default="dev")


class DirectorOutput(BaseModel):
    """Validated output from Director agent."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)


class StrategicDirectorOutput(BaseModel):
    """Validated output from Strategic Director agent."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)


class EditorialReview(BaseModel):
    """Validated output from Editorial Director agent."""

    approved: bool
    quality_score: int = Field(ge=1, le=10)
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    engagement_insights: list[str] = Field(default_factory=list)


class NewsScoutState(BaseModel):
    """Tracks when news was last fetched to enforce once-per-day."""

    last_fetch_date: str = ""  # YYYY-MM-DD


class AnalysisState(BaseModel):
    """Tracks analysis rate limiting: daily cap and minimum gap between analyses."""

    analyses_completed_today: int = 0
    last_analysis_date: str = ""  # YYYY-MM-DD
    last_analysis_completed_at: str = ""  # ISO 8601 timestamp


class ResearchScoutState(BaseModel):
    """Tracks when the Research Scout last ran to enforce weekly cadence."""

    last_fetch_date: str = ""  # YYYY-MM-DD


class ResearchScoutOutput(BaseModel):
    """Validated output from Research Scout agent."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)


class ConductorAction(BaseModel):
    """A single action decided by the Conductor agent."""

    action: Literal[
        "fetch_news", "propose", "debate", "pick_and_execute",
        "director", "strategic_director", "research_scout",
        "post_pending_tweets",
        "cooldown", "halt", "file_issue", "skip_cycle",
    ]
    reason: str
    issue_number: int | None = None   # required for pick_and_execute
    title: str | None = None          # file_issue
    description: str | None = None    # file_issue
    seconds: int | None = None        # cooldown duration


class ConductorPlan(BaseModel):
    """Structured output from the Conductor agent."""

    reasoning: str
    actions: list[ConductorAction] = Field(max_length=6)
    suggested_cooldown_seconds: int = Field(default=60, ge=10, le=3600)
    notes_for_next_cycle: str = ""  # Brief observations to carry forward


_repo_nwo: str | None = None


# ---------------------------------------------------------------------------
# SDK helpers
# ---------------------------------------------------------------------------


EffortLevel = Literal["low", "medium", "high", "max"]


def _sdk_options(
    *,
    system_prompt: str,
    model: str,
    max_turns: int,
    allowed_tools: list[str],
    effort: EffortLevel | None = None,
) -> ClaudeAgentOptions:
    # Agents WITH tools: use SystemPromptPreset with "append" so they get
    # built-in tool instructions, safety guards, and CLAUDE.md project context.
    # Agents WITHOUT tools: replace the system prompt entirely (no point loading
    # tool instructions they can't use).
    if allowed_tools:
        return ClaudeAgentOptions(
            system_prompt={"type": "preset", "preset": "claude_code", "append": system_prompt},
            model=model,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            cwd=PROJECT_ROOT,
            env=SDK_ENV,
            setting_sources=["project"],
            effort=effort,
        )
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        cwd=PROJECT_ROOT,
        env=SDK_ENV,
        effort=effort,
    )


async def _collect_agent_output(
    stream: AsyncIterator[claude_agent_sdk.Message],
    *,
    timeout_seconds: float = AGENT_TIMEOUT_SECONDS,
) -> str:
    text_parts: list[str] = []

    async def _drain() -> None:
        async for message in stream:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)

    with anyio.fail_after(timeout_seconds):
        await _drain()
    return "\n".join(text_parts)


async def _collect_structured_output(
    stream: AsyncIterator[claude_agent_sdk.Message],
    *,
    timeout_seconds: float = AGENT_TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """Collect structured output from an SDK stream.

    Extracts JSON from result text via prompt-based format instructions.
    Also accepts structured_output if the SDK provides it.
    """
    from government.agents.base import collect_structured_or_text, parse_structured_or_text

    state: dict[str, Any] = {}

    async def _drain() -> None:
        async for message in stream:
            collect_structured_or_text(message, state)

    with anyio.fail_after(timeout_seconds):
        await _drain()
    return parse_structured_or_text(state)


async def _run_sdk_with_retry(
    prompt: str,
    opts: ClaudeAgentOptions,
    *,
    retries: int = SDK_RETRY_ATTEMPTS,
    base_delay: float = SDK_RETRY_BASE_DELAY,
) -> str:
    """Run an SDK query with retries for transient errors.

    Wraps ``claude_agent_sdk.query()`` + ``_collect_agent_output()``.
    On transient SDK failures (exit code 1, timeout), retries up to
    ``retries`` times with exponential backoff before re-raising.
    """
    last_exc: Exception | None = None
    for attempt in range(1 + retries):
        try:
            stream = claude_agent_sdk.query(prompt=prompt, options=opts)
            return await _collect_agent_output(stream)
        except Exception as exc:
            last_exc = exc
            if not _is_sdk_transient_error(exc):
                raise
            if attempt < retries:
                delay = base_delay * (2 ** attempt)
                log.warning(
                    "SDK transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    1 + retries,
                    delay,
                    exc,
                )
                await anyio.sleep(delay)
            else:
                log.warning(
                    "SDK transient error (attempt %d/%d), giving up: %s",
                    attempt + 1,
                    1 + retries,
                    exc,
                )
    # Should be unreachable, but satisfy the type checker
    assert last_exc is not None
    raise last_exc


async def _run_sdk_for_json_array(
    prompt: str,
    opts: ClaudeAgentOptions,
    *,
    agent_name: str = "agent",
) -> list[dict[str, str]]:
    """Run SDK query, parse JSON array, retry with context on failure.

    Combines ``_run_sdk_with_retry()`` (transient-error retry) with a
    JSON-specific retry: if the first response doesn't contain a valid
    JSON array, re-sends the original prompt with an explicit JSON-only
    instruction appended.
    """
    output = await _run_sdk_with_retry(prompt, opts)
    raw = _parse_json_array(output)
    if raw:
        return raw

    log.warning("%s: no parseable JSON array, retrying with context", agent_name)
    output = await _run_sdk_with_retry(retry_prompt(prompt), opts)
    raw = _parse_json_array(output)
    if not raw:
        log.warning("%s: retry also produced no parseable JSON array", agent_name)
    return raw


def _parse_structured_text(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from agent text output."""
    from government.agents.json_parsing import extract_json

    if not text:
        return None
    return extract_json(text)


# ---------------------------------------------------------------------------
# Git / GitHub helpers
# ---------------------------------------------------------------------------


_GH_TIMEOUT_SECONDS = 30


def _run_gh(
    args: list[str], *, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log.debug("Running: %s", " ".join(args))
    try:
        result = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True, cwd=PROJECT_ROOT, check=False,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ds: %s", _GH_TIMEOUT_SECONDS, " ".join(args))
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="timeout")
    if check and result.returncode != 0:
        log.error("Command failed: %s\nstderr: %s", " ".join(args), result.stderr.strip())
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result


# GitHub API body limit is 65,535 characters.  OS ARG_MAX can also bite
# on long --body arguments.  Use --body-file via a temp file above this
# conservative threshold.
_GH_BODY_MAX = 60_000


def _gh_comment(
    issue_number: int,
    body: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Post a comment on an issue, using --body-file for large bodies."""
    if len(body) <= _GH_BODY_MAX:
        return _run_gh(
            ["gh", "issue", "comment", str(issue_number), "--body", body],
            check=check,
        )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False,
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name
    try:
        return _run_gh(
            ["gh", "issue", "comment", str(issue_number),
             "--body-file", tmp_path],
            check=check,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _gh_create_issue(
    *,
    title: str,
    body: str,
    labels: str,
) -> subprocess.CompletedProcess[str]:
    """Create a GitHub issue, using --body-file for large bodies."""
    cmd: list[str] = ["gh", "issue", "create", "--title", title]
    if len(body) <= _GH_BODY_MAX:
        cmd += ["--body", body]
        cmd += ["--label", labels]
        return _run_gh(cmd)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False,
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name
    try:
        cmd += ["--body-file", tmp_path]
        cmd += ["--label", labels]
        return _run_gh(cmd)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _get_repo_nwo() -> str:
    """Return 'owner/repo' for the current repository, cached after first call."""
    global _repo_nwo  # noqa: PLW0603
    if _repo_nwo is None:
        result = _run_gh([
            "gh", "repo", "view", "--json", "owner,name",
            "-q", '.owner.login + "/" + .name',
        ])
        _repo_nwo = result.stdout.strip()
    return _repo_nwo


def _is_privileged_user(username: str) -> bool:
    """Check if *username* has admin or maintain permission on this repo."""
    nwo = _get_repo_nwo()
    result = _run_gh(
        ["gh", "api", f"repos/{nwo}/collaborators/{username}/permission"],
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return data.get("permission", "") in PRIVILEGED_PERMISSIONS


def _is_issue_open(issue_number: int) -> bool:
    """Check if an issue is currently open."""
    result = _run_gh(
        ["gh", "issue", "view", str(issue_number), "--json", "state"],
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return data.get("state", "").upper() == "OPEN"


def _ensure_labels() -> None:
    """Create all labels idempotently."""
    for label, color in ALL_LABELS.items():
        _run_gh(
            ["gh", "label", "create", label, "--color", color, "--force"],
            check=False,
        )
    log.info("Labels ensured")


def ensure_github_resources_exist() -> None:
    """Create labels."""
    _ensure_labels()


def create_proposal_issue(title: str, body: str, *, domain: str = "N/A") -> int:
    """Create a GitHub Issue with the proposed label. Returns issue number."""
    ai_body = f"Written by PM agent:\n\n{body}"
    result = _gh_create_issue(title=title, body=ai_body, labels=LABEL_PROPOSED)
    # gh issue create prints the URL; extract number from it
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def create_director_issue(title: str, body: str) -> int:
    """Create a GitHub Issue from the Project Director. Returns issue number."""
    ai_body = f"Written by Project Director agent:\n\n{body}"
    result = _gh_create_issue(
        title=title, body=ai_body,
        labels=f"{LABEL_DIRECTOR},{LABEL_BACKLOG},{LABEL_TASK_CODE}",
    )
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def create_strategic_director_issue(title: str, body: str) -> int:
    """Create a GitHub Issue from the Strategic Director. Returns issue number."""
    ai_body = f"Written by Strategic Director agent:\n\n{body}"
    result = _gh_create_issue(
        title=title, body=ai_body,
        labels=f"{LABEL_STRATEGY},{LABEL_BACKLOG},{LABEL_TASK_CODE}",
    )
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def create_research_scout_issue(title: str, body: str) -> int:
    """Create a GitHub Issue from the Research Scout. Returns issue number."""
    ai_body = f"Written by Research Scout agent:\n\n{body}"
    result = _gh_create_issue(
        title=title, body=ai_body,
        labels=f"{LABEL_RESEARCH_SCOUT},{LABEL_BACKLOG},{LABEL_TASK_CODE}",
    )
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def create_ci_failure_issue(run_id: str, failure_summary: str) -> int:
    """Create a GitHub Issue for a CI failure on main. Returns issue number."""
    body = f"""CI failure detected on main branch.

**Run ID**: {run_id}
**Run URL**: https://github.com/{_get_repo_nwo()}/actions/runs/{run_id}

## Failure Summary

{failure_summary}

## Next Steps

This issue has been automatically created and labeled with `{LABEL_CI_FAILURE}`,
`{LABEL_BACKLOG}`, and `{LABEL_TASK_FIX}` for high-priority handling.

The coder agent should:
1. Review the failure logs (linked above)
2. Fix the issue (lint errors, type errors, test failures, or build issues)
3. Ensure all checks pass locally before pushing
4. Close this issue once main is green again
"""
    result = _gh_create_issue(
        title=f"CI failure on main (run {run_id})",
        body=body,
        labels=f"{LABEL_CI_FAILURE},{LABEL_BACKLOG},{LABEL_TASK_FIX}",
    )
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def _find_latest_completed_run(
    runs: list[dict[str, object]],
) -> dict[str, object] | None:
    """Return the most recent completed run from a list, or None if none are completed."""
    for run in runs:
        if run.get("status") == "completed":
            return run
    return None


def _fetch_recent_ci_runs() -> list[dict[str, object]] | None:
    """Fetch up to 5 recent CI runs on main. Returns None on error."""
    result = _run_gh([
        "gh", "run", "list",
        "--branch", "main",
        "--limit", "5",
        "--json", "databaseId,conclusion,status",
    ], check=False)

    if result.returncode != 0:
        log.warning("Failed to fetch CI runs: %s", result.stderr.strip())
        return None

    runs: list[dict[str, object]] = (
        json.loads(result.stdout) if result.stdout.strip() else []
    )
    return runs


def is_ci_passing() -> bool:
    """Return True if the most recent completed CI run on main passed.

    Returns True (optimistic) if there are no runs, no completed runs,
    or on error — so the loop isn't blocked by transient failures.
    """
    runs = _fetch_recent_ci_runs()
    if runs is None or not runs:
        return True

    completed = _find_latest_completed_run(runs)
    if completed is None:
        # All runs are in-progress — optimistically allow
        return True

    return completed.get("conclusion") == "success"


def check_ci_health() -> int:
    """Check CI status on main branch. If failed, file an issue. Returns number of issues created."""
    # Get recent workflow runs on main (up to 5)
    runs = _fetch_recent_ci_runs()

    if runs is None:
        return 0

    if not runs:
        log.info("No CI runs found on main branch")
        return 0

    # Find the most recent *completed* run, skipping in-progress ones
    completed_run = _find_latest_completed_run(runs)
    if completed_run is None:
        log.info("All %d recent CI runs are still in progress", len(runs))
        return 0

    run_id = str(completed_run["databaseId"])
    conclusion = completed_run.get("conclusion")

    # If the run succeeded, nothing to do
    if conclusion == "success":
        log.info("Latest completed CI run %s succeeded", run_id)
        return 0

    # Check if we already have an open issue for this run
    existing_issues_result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_CI_FAILURE,
        "--state", "open",
        "--json", "number,title,body",
        "--limit", "20",
    ], check=False)

    if existing_issues_result.returncode == 0:
        existing_issues = (
            json.loads(existing_issues_result.stdout)
            if existing_issues_result.stdout.strip()
            else []
        )
        for issue in existing_issues:
            # Check if the issue body mentions this run ID
            if run_id in issue.get("body", ""):
                log.info("CI failure issue already exists for run %s (issue #%d)", run_id, issue["number"])
                return 0

    # CI failed — fetch failure logs
    log.warning("CI run %s failed with conclusion=%s", run_id, conclusion)

    logs_result = _run_gh([
        "gh", "run", "view", run_id,
        "--log-failed",
    ], check=False)

    if logs_result.returncode != 0:
        failure_summary = f"Failed to fetch logs: {logs_result.stderr.strip()}"
    else:
        # Truncate logs to avoid huge issue bodies
        raw_logs = logs_result.stdout.strip()
        if len(raw_logs) > 5000:
            failure_summary = f"```\n{raw_logs[:5000]}\n... (truncated)\n```"
        else:
            failure_summary = f"```\n{raw_logs}\n```"

    # Create the issue
    issue_number = create_ci_failure_issue(run_id, failure_summary)
    log.info("Created CI failure issue #%d for run %s", issue_number, run_id)
    return 1


def post_debate_comment(
    issue_number: int,
    advocate_arg: str,
    skeptic_challenge: str,
    advocate_rebuttal: str,
    skeptic_verdict: str,
    verdict: str,
) -> None:
    """Post the full debate as a comment on the issue."""
    body = (
        f"## \U0001f916 AI Triage Debate\n\n"
        f"### Round 1 — Proposal & Feedback\n\n"
        f"**Written by PM agent:**\n{advocate_arg}\n\n"
        f"**Written by Critic agent:**\n{skeptic_challenge}\n\n"
        f"### Round 2 — Refinement & Verdict\n\n"
        f"**Written by PM agent (refined):**\n{advocate_rebuttal}\n\n"
        f"**Written by Critic agent (verdict):**\n{skeptic_verdict}\n\n"
        f"### Result: **{verdict}**"
    )
    _gh_comment(issue_number, body)


def accept_issue(issue_number: int) -> None:
    """Move issue from proposed to backlog."""
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_PROPOSED,
             "--add-label", LABEL_BACKLOG])


def reject_issue(issue_number: int) -> None:
    """Label as rejected and close."""
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_PROPOSED,
             "--add-label", LABEL_REJECTED])
    _run_gh(["gh", "issue", "close", str(issue_number),
             "--comment", "Written by Triage agent: Rejected by triage debate. See debate above."])


def _issue_has_debate_comment(issue_number: int) -> bool:
    """Check if an issue already has a debate comment."""
    nwo = _get_repo_nwo()
    result = _run_gh(
        ["gh", "api", f"repos/{nwo}/issues/{issue_number}/comments"],
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        comments = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return any("AI Triage Debate" in c.get("body", "") for c in comments)


def list_backlog_issues() -> list[dict[str, Any]]:
    """Return backlog issues, oldest first.

    Excludes gap observation issues (gap:content, gap:technical) which are
    director input, not executable tasks.
    """
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_BACKLOG,
        "--state", "open",
        "--json", "number,title,body,labels,createdAt",
        "--limit", "50",
    ])
    issues: list[dict[str, Any]] = json.loads(result.stdout) if result.stdout.strip() else []
    # Filter out gap observation issues — they're director input, not coder tasks
    gap_labels = {LABEL_GAP_CONTENT, LABEL_GAP_TECHNICAL}
    issues = [
        i for i in issues
        if not any(
            lbl.get("name") in gap_labels
            for lbl in i.get("labels", [])
        )
    ]
    issues.sort(key=lambda i: i.get("createdAt", ""))
    return issues


def list_human_suggestions() -> list[dict[str, Any]]:
    """Return human-suggestion issues pending triage."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_HUMAN,
        "--state", "open",
        "--json", "number,title,body,createdAt,author",
        "--limit", "50",
    ])
    return json.loads(result.stdout) if result.stdout.strip() else []


def process_human_overrides() -> int:
    """Find reopened rejected issues or issues with HUMAN OVERRIDE comments.

    A human can override the AI triage by either:
    1. Reopening a closed rejected issue (label: self-improve:rejected, state: open)
    2. Adding a comment containing "HUMAN OVERRIDE" on any issue

    Overridden issues are moved straight to backlog, skipping debate.
    Returns the number of issues overridden.
    """
    count = 0

    # Case 1: Reopened rejected issues (human reopened a closed+rejected issue)
    nwo = _get_repo_nwo()
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_REJECTED,
        "--state", "open",
        "--json", "number,title",
        "--limit", "50",
    ])
    reopened = json.loads(result.stdout) if result.stdout.strip() else []
    for issue in reopened:
        n = issue["number"]
        # Find who reopened the issue
        events_result = _run_gh(
            ["gh", "api", f"repos/{nwo}/issues/{n}/events"],
            check=False,
        )
        if events_result.returncode != 0:
            log.warning("Could not fetch events for #%d, skipping", n)
            continue
        try:
            events = json.loads(events_result.stdout)
        except json.JSONDecodeError:
            log.warning("Could not parse events for #%d, skipping", n)
            continue
        # Find the most recent "reopened" event
        reopen_events = [e for e in events if e.get("event") == "reopened"]
        if not reopen_events:
            log.warning("No reopen event found for #%d, skipping", n)
            continue
        actor_login = reopen_events[-1].get("actor", {}).get("login", "")
        if not _is_privileged_user(actor_login):
            log.warning(
                "Ignoring override on #%d by %s (not a repo admin)", n, actor_login,
            )
            continue
        _run_gh(["gh", "issue", "edit", str(n),
                 "--remove-label", LABEL_REJECTED,
                 "--add-label", LABEL_BACKLOG])
        _gh_comment(n,
                    f"Written by Triage agent: Issue reopened by @{actor_login} — "
                    "moved to backlog via human override.")
        log.info("Human override (reopened): #%d %s (by %s)", n, issue["title"], actor_login)
        count += 1

    # Case 2: HUMAN OVERRIDE in comments on any open issue with proposed/rejected label
    for label in (LABEL_PROPOSED, LABEL_REJECTED):
        result = _run_gh([
            "gh", "issue", "list",
            "--label", label,
            "--state", "all",
            "--json", "number,title",
            "--limit", "50",
        ], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        issues = json.loads(result.stdout)
        for issue in issues:
            n = issue["number"]
            # Fetch comments via REST API to get per-comment author info
            comments_result = _run_gh(
                ["gh", "api", f"repos/{nwo}/issues/{n}/comments"],
                check=False,
            )
            if comments_result.returncode != 0:
                continue
            try:
                comments = json.loads(comments_result.stdout)
            except json.JSONDecodeError:
                continue
            # Find a privileged HUMAN OVERRIDE comment
            override_user = None
            for c in comments:
                if "HUMAN OVERRIDE" in c.get("body", ""):
                    commenter = c.get("user", {}).get("login", "")
                    if _is_privileged_user(commenter):
                        override_user = commenter
                        break
                    log.warning(
                        "Ignoring override on #%d by %s (not a repo admin)",
                        n, commenter,
                    )
            if override_user is None:
                continue
            # Check it's not already in backlog/in-progress/done
            already = _run_gh([
                "gh", "issue", "view", str(n),
                "--json", "labels", "-q",
                ".labels[].name",
            ], check=False)
            label_names = already.stdout.strip()
            if LABEL_BACKLOG in label_names or LABEL_IN_PROGRESS in label_names:
                continue
            # Move to backlog
            _run_gh(["gh", "issue", "edit", str(n),
                     "--remove-label", label,
                     "--add-label", LABEL_BACKLOG])
            # Reopen if closed
            _run_gh(["gh", "issue", "reopen", str(n)], check=False)
            _gh_comment(n,
                        f"Written by Triage agent: HUMAN OVERRIDE by @{override_user} — "
                        "moved to backlog.")
            log.info(
                "Human override (comment): #%d %s (by %s)",
                n, issue["title"], override_user,
            )
            count += 1

    return count


def collect_override_records() -> list[HumanOverride]:
    """Collect all human override records from GitHub for transparency reporting.

    Scans all closed issues/PRs with override-related comments and reopened
    rejected issues to build a complete transparency log.
    """
    overrides: list[HumanOverride] = []
    nwo = _get_repo_nwo()

    # Scan all closed issues with HUMAN OVERRIDE comments
    result = _run_gh(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--json",
            "number,title,state,labels,createdAt",
            "--limit",
            "200",
        ],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        log.warning("Could not fetch issues for override collection")
        return overrides

    issues = json.loads(result.stdout)

    for issue in issues:
        n = issue["number"]
        label_names = [lbl["name"] for lbl in issue.get("labels", [])]

        # Fetch events to detect reopenings
        events_result = _run_gh(
            ["gh", "api", f"repos/{nwo}/issues/{n}/events"], check=False
        )
        events = []
        if events_result.returncode == 0 and events_result.stdout.strip():
            events = json.loads(events_result.stdout)

        # Fetch comments for HUMAN OVERRIDE markers
        comments_result = _run_gh(
            ["gh", "api", f"repos/{nwo}/issues/{n}/comments"], check=False
        )
        comments = []
        if comments_result.returncode == 0 and comments_result.stdout.strip():
            comments = json.loads(comments_result.stdout)

        # Case 1: Reopened after rejection
        reopen_events = [e for e in events if e.get("event") == "reopened"]
        labeled_rejected = [
            e
            for e in events
            if e.get("event") == "labeled"
            and e.get("label", {}).get("name") == LABEL_REJECTED
        ]

        if reopen_events and labeled_rejected:
            # Find reopen events that happened after rejection
            for reopen_ev in reopen_events:
                reopen_time = reopen_ev.get("created_at", "")
                actor_login = reopen_ev.get("actor", {}).get("login", "unknown")

                if not _is_privileged_user(actor_login):
                    continue

                # Check if this reopen happened after a rejection
                rejection_time = max(
                    (e.get("created_at", "") for e in labeled_rejected), default=""
                )
                if reopen_time > rejection_time:
                    # Extract rationale from subsequent comments
                    rationale = None
                    for c in comments:
                        if (
                            "human override" in c.get("body", "").lower()
                            and c.get("created_at", "") >= reopen_time
                        ):
                            body = c.get("body", "")
                            # Try to extract rationale after the override marker
                            if "—" in body:
                                rationale = body.split("—", 1)[1].strip()[:200]
                            break

                    try:
                        timestamp = datetime.fromisoformat(
                            reopen_time.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        timestamp = datetime.now(UTC)

                    overrides.append(
                        HumanOverride(
                            timestamp=timestamp,
                            issue_number=n,
                            pr_number=None,
                            override_type="reopened",
                            actor=actor_login,
                            issue_title=issue["title"],
                            ai_verdict="Rejected by AI triage",
                            human_action="Reopened and moved to backlog",
                            rationale=rationale,
                        )
                    )

        # Case 2: Explicit HUMAN OVERRIDE comment
        for c in comments:
            body = c.get("body", "")
            if "HUMAN OVERRIDE" not in body:
                continue

            commenter = c.get("user", {}).get("login", "unknown")
            if not _is_privileged_user(commenter):
                continue

            created_at = c.get("created_at", "")
            try:
                timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(UTC)

            # Determine AI verdict from labels or previous state
            ai_verdict = "AI rejected/proposed changes"
            if LABEL_REJECTED in label_names:
                ai_verdict = "Rejected by AI triage"
            elif LABEL_PROPOSED in label_names:
                ai_verdict = "Awaiting AI debate"

            # Extract rationale
            rationale = None
            if "—" in body:
                rationale = body.split("—", 1)[1].strip()[:200]
            elif "\n" in body:
                lines = body.split("\n")
                if len(lines) > 1:
                    rationale = lines[1].strip()[:200]

            overrides.append(
                HumanOverride(
                    timestamp=timestamp,
                    issue_number=n,
                    pr_number=None,
                    override_type="comment",
                    actor=commenter,
                    issue_title=issue["title"],
                    ai_verdict=ai_verdict,
                    human_action="Moved to backlog via override",
                    rationale=rationale,
                )
            )

    # Sort by timestamp descending (newest first)
    overrides.sort(key=lambda o: o.timestamp, reverse=True)
    return overrides


def save_override_records(overrides: list[HumanOverride]) -> Path:
    """Save override records to JSON file for site builder."""
    output_dir = PROJECT_ROOT / "output" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "overrides.json"

    data = [o.model_dump(mode="json") for o in overrides]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Saved %d override records to %s", len(overrides), path)
    return path


def collect_human_suggestions() -> list[HumanSuggestion]:
    """Collect all human-suggested issues for transparency reporting.

    Scans all issues (open and closed) with the human-suggestion label to track
    human-directed work.
    """
    suggestions: list[HumanSuggestion] = []

    # Fetch all issues with human-suggestion label
    result = _run_gh(
        [
            "gh",
            "issue",
            "list",
            "--label",
            LABEL_HUMAN,
            "--state",
            "all",
            "--json",
            "number,title,state,createdAt,author",
            "--limit",
            "200",
        ],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        log.warning("Could not fetch human-suggested issues")
        return suggestions

    issues = json.loads(result.stdout)

    for issue in issues:
        created_at = issue.get("createdAt", "")
        try:
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.now(UTC)

        suggestions.append(
            HumanSuggestion(
                timestamp=timestamp,
                issue_number=issue["number"],
                issue_title=issue["title"],
                status="open" if issue["state"] == "OPEN" else "closed",
                creator=issue.get("author", {}).get("login", "unknown"),
            )
        )

    # Sort by timestamp descending (newest first)
    suggestions.sort(key=lambda s: s.timestamp, reverse=True)
    return suggestions


def save_suggestion_records(suggestions: list[HumanSuggestion]) -> Path:
    """Save human suggestion records to JSON file for site builder."""
    output_dir = PROJECT_ROOT / "output" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "suggestions.json"

    data = [s.model_dump(mode="json") for s in suggestions]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Saved %d human suggestion records to %s", len(suggestions), path)
    return path


def collect_pr_merges() -> list[PRMerge]:
    """Collect merged PRs by privileged users for transparency reporting.

    Tracks human review and approval of AI-generated code as a form
    of human intervention.
    """
    merges: list[PRMerge] = []

    result = _run_gh(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--json",
            "number,title,mergedAt,mergedBy,body",
            "--limit",
            "200",
        ],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        log.warning("Could not fetch merged PRs")
        return merges

    prs = json.loads(result.stdout)

    for pr in prs:
        merged_by = pr.get("mergedBy", {})
        actor_login = merged_by.get("login", "") if merged_by else ""
        if not actor_login or not _is_privileged_user(actor_login):
            continue

        merged_at = pr.get("mergedAt", "")
        try:
            timestamp = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.now(UTC)

        body = pr.get("body", "") or ""

        # Skip AI-authored PRs — they start with "Written by Coder agent"
        if "written by coder agent" in body.lower():
            continue

        # Tag human-initiated PRs on GitHub for visibility
        pr_labels = [label.get("name", "") for label in pr.get("labels", [])]
        if "human-initiated" not in pr_labels:
            _run_gh(
                ["gh", "pr", "edit", str(pr["number"]), "--add-label", "human-initiated"],
                check=False,
            )

        # Extract linked issue number from PR body
        issue_number: int | None = None
        # Match patterns like "Closes #123", "Fixes #45", "Resolves #678"
        issue_match = re.search(
            r"(?:closes|fixes|resolves)\s+#(\d+)", body, re.IGNORECASE
        )
        if issue_match:
            issue_number = int(issue_match.group(1))

        merges.append(
            PRMerge(
                timestamp=timestamp,
                pr_number=pr["number"],
                pr_title=pr["title"],
                actor=actor_login,
                issue_number=issue_number,
            )
        )

    merges.sort(key=lambda m: m.timestamp, reverse=True)
    return merges


def save_pr_merge_records(merges: list[PRMerge]) -> Path:
    """Save PR merge records to JSON file for site builder."""
    output_dir = PROJECT_ROOT / "output" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pr_merges.json"

    data = [m.model_dump(mode="json") for m in merges]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Saved %d PR merge records to %s", len(merges), path)
    return path


def mark_issue_in_progress(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_BACKLOG,
             "--add-label", LABEL_IN_PROGRESS], check=False)


def mark_issue_done(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_DONE], check=False)
    _run_gh(["gh", "issue", "close", str(issue_number)], check=False)


def mark_issue_failed(issue_number: int, reason: str) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_FAILED], check=False)
    _gh_comment(issue_number,
                f"Written by Executor agent: Execution failed: {reason}",
                check=False)


def get_failed_issue_titles() -> list[str]:
    """Return titles of previously failed issues (for dedup).

    DEPRECATED: Use get_all_issue_titles() instead for comprehensive deduplication.
    """
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_FAILED,
        "--state", "all",
        "--json", "title",
        "--limit", "100",
    ])
    issues = json.loads(result.stdout) if result.stdout.strip() else []
    return [i["title"] for i in issues]


def get_all_issue_titles() -> dict[str, list[str]]:
    """Return all issue titles grouped by state for comprehensive deduplication.

    Returns a dict with keys: 'open', 'closed', 'failed' for different context blocks.
    - 'open': Currently open issues (backlog, in-progress, proposed)
    - 'closed': Completed or rejected work
    - 'failed': Previously failed attempts
    """
    result = _run_gh([
        "gh", "issue", "list",
        "--state", "all",
        "--json", "title,state,labels",
        "--limit", "200",
    ])
    issues = json.loads(result.stdout) if result.stdout.strip() else []

    open_titles: list[str] = []
    closed_titles: list[str] = []
    failed_titles: list[str] = []

    for issue in issues:
        title = issue.get("title", "")
        state = issue.get("state", "").upper()
        labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]

        # Categorize by state and labels
        if LABEL_FAILED in labels:
            failed_titles.append(title)
        elif state == "OPEN":
            open_titles.append(title)
        else:  # CLOSED
            closed_titles.append(title)

    return {
        "open": open_titles,
        "closed": closed_titles,
        "failed": failed_titles,
    }


# ---------------------------------------------------------------------------
# Role prompt loading
# ---------------------------------------------------------------------------


def _load_role_prompt(role: str) -> str:
    path = PROJECT_ROOT / "theseus" / role / "CLAUDE.md"
    if path.exists():
        return path.read_text()
    log.warning("Role prompt not found: %s", path)
    return ""


# ---------------------------------------------------------------------------
# Phase A: Government decision analysis
# ---------------------------------------------------------------------------


def _count_pending_analysis_issues() -> int:
    """Count open issues with the task:analysis label."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_TASK_ANALYSIS,
        "--state", "open",
        "--json", "number",
        "--limit", "50",
    ], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    return len(json.loads(result.stdout))


def should_run_analysis(
    max_per_day: int = DEFAULT_MAX_ANALYSES_PER_DAY,
    min_gap_hours: int = DEFAULT_MIN_ANALYSIS_GAP_HOURS,
) -> bool:
    """Check daily cap and minimum gap between analyses."""
    state = _load_analysis_state()
    today = _dt.date.today().isoformat()

    # Reset counter if new day
    if state.last_analysis_date != today:
        return True

    # Check daily cap
    if state.analyses_completed_today >= max_per_day:
        log.info(
            "Analysis rate limit: %d/%d analyses completed today (max reached)",
            state.analyses_completed_today, max_per_day,
        )
        return False

    # Check minimum gap (skip if no gap required)
    if min_gap_hours > 0 and state.last_analysis_completed_at:
        from datetime import timedelta
        last_completed = datetime.fromisoformat(state.last_analysis_completed_at)
        elapsed = datetime.now(UTC) - last_completed
        required_gap = timedelta(hours=min_gap_hours)
        if elapsed < required_gap:
            remaining = required_gap - elapsed
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            log.info(
                "Analysis rate limit: only %dh %dm since last analysis (need %dh gap)",
                hours, minutes, min_gap_hours,
            )
            return False

    return True


def analysis_wait_seconds(
    min_gap_hours: int = DEFAULT_MIN_ANALYSIS_GAP_HOURS,
) -> int:
    """Return seconds until the next analysis is allowed (0 if ready now)."""
    state = _load_analysis_state()
    today = _dt.date.today().isoformat()

    if state.last_analysis_date != today:
        return 0

    if min_gap_hours > 0 and state.last_analysis_completed_at:
        from datetime import timedelta

        last_completed = datetime.fromisoformat(state.last_analysis_completed_at)
        elapsed = datetime.now(UTC) - last_completed
        required_gap = timedelta(hours=min_gap_hours)
        if elapsed < required_gap:
            return int((required_gap - elapsed).total_seconds())

    return 0


def _backlog_has_executable_tasks() -> bool:
    """Return True if the backlog has tasks that can run now.

    Analysis tasks count as executable when the analysis rate limiter allows.
    """
    issues = list_backlog_issues()
    if not issues:
        return False
    # Non-analysis tasks are always executable
    if any(not _issue_has_label(issue, LABEL_TASK_ANALYSIS) for issue in issues):
        return True
    # Analysis tasks are executable when rate limiter allows
    has_analysis = any(_issue_has_label(issue, LABEL_TASK_ANALYSIS) for issue in issues)
    return bool(has_analysis and should_run_analysis())


def should_fetch_news() -> bool:
    """Return True if news has not been fetched today and analysis queue is low enough."""
    # Allow fetching when pending analysis issues are at or below the threshold.
    # Previously this required 0 pending, which created a starvation loop when
    # old analysis issues sat in the backlog and blocked all news ingestion.
    pending = _count_pending_analysis_issues()
    if pending > NEWS_GATE_MAX_PENDING:
        log.info(
            "Skipping News Scout: %d analysis issue(s) still open (max %d)",
            pending,
            NEWS_GATE_MAX_PENDING,
        )
        return False

    today = _dt.date.today().isoformat()
    if not NEWS_SCOUT_STATE_PATH.exists():
        return True
    try:
        state = NewsScoutState.model_validate_json(NEWS_SCOUT_STATE_PATH.read_text())
        return state.last_fetch_date != today
    except Exception:
        return True


def _save_news_scout_state(date_str: str) -> None:
    """Persist last fetch date to disk."""
    NEWS_SCOUT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEWS_SCOUT_STATE_PATH.write_text(
        NewsScoutState(last_fetch_date=date_str).model_dump_json()
    )


def _load_research_scout_state() -> ResearchScoutState:
    """Load Research Scout state from disk, or return empty state if missing/corrupt."""
    if not RESEARCH_SCOUT_STATE_PATH.exists():
        return ResearchScoutState()
    try:
        return ResearchScoutState.model_validate_json(RESEARCH_SCOUT_STATE_PATH.read_text())
    except Exception:
        log.warning("Could not parse research scout state, using empty state")
        return ResearchScoutState()


def _save_research_scout_state(date_str: str) -> None:
    """Persist Research Scout last-run date to disk."""
    RESEARCH_SCOUT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_SCOUT_STATE_PATH.write_text(
        ResearchScoutState(last_fetch_date=date_str).model_dump_json()
    )


def should_run_research_scout(interval_days: int = DEFAULT_RESEARCH_SCOUT_INTERVAL_DAYS) -> bool:
    """Return True if the Research Scout has not run within *interval_days*."""
    today = _dt.date.today()
    if not RESEARCH_SCOUT_STATE_PATH.exists():
        return True
    try:
        state = ResearchScoutState.model_validate_json(RESEARCH_SCOUT_STATE_PATH.read_text())
        if not state.last_fetch_date:
            return True
        last_date = _dt.date.fromisoformat(state.last_fetch_date)
        return (today - last_date).days >= interval_days
    except Exception:
        return True


def _load_analysis_state() -> AnalysisState:
    """Load analysis state from disk, or return empty state if missing/corrupt."""
    if not ANALYSIS_STATE_PATH.exists():
        return AnalysisState()
    try:
        return AnalysisState.model_validate_json(ANALYSIS_STATE_PATH.read_text())
    except Exception:
        log.warning("Could not parse analysis state, using empty state")
        return AnalysisState()


def _save_analysis_state(state: AnalysisState) -> None:
    """Persist analysis state to disk."""
    ANALYSIS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANALYSIS_STATE_PATH.write_text(state.model_dump_json())


def _record_analysis_completion(max_per_day: int = DEFAULT_MAX_ANALYSES_PER_DAY) -> None:
    """Record that an analysis was completed just now."""
    state = _load_analysis_state()
    now = datetime.now(UTC)
    today = _dt.date.today().isoformat()

    # Reset counter if new day
    if state.last_analysis_date != today:
        state.analyses_completed_today = 0
        state.last_analysis_date = today

    state.analyses_completed_today += 1
    state.last_analysis_completed_at = now.isoformat()
    _save_analysis_state(state)
    log.info(
        "Recorded analysis completion: %d/%d today, last at %s",
        state.analyses_completed_today, max_per_day, state.last_analysis_completed_at,
    )


def _generate_decision_id(title: str, date: _dt.date) -> str:
    """Generate a deterministic ID from date + title hash."""
    h = hashlib.sha256(title.encode()).hexdigest()[:8]
    return f"item-{date.isoformat()}-{h}"


def _build_category_distribution_context() -> str:
    """Build a summary of recent analysis category distribution for the news scout.

    Returns a formatted string with category counts, or empty string if no data.
    """
    if not DATA_DIR.exists():
        return ""
    try:
        results = load_results_from_dir(DATA_DIR)
    except Exception:
        log.warning("Failed to load results for category distribution context")
        return ""
    if not results:
        return ""

    category_counts: Counter[str] = Counter()
    for r in results:
        category_counts[r.decision.category or "general"] += 1

    total = sum(category_counts.values())
    overrepresentation_threshold = 40  # percent
    lines = []
    for cat, cnt in category_counts.most_common():
        pct = round(100 * cnt / total)
        marker = " ⚠️ OVER" if pct > overrepresentation_threshold else ""
        lines.append(f"  {cat}: {cnt} ({pct}%){marker}")

    all_categories = [
        "fiscal", "legal", "eu", "health", "security",
        "education", "economy", "tourism", "environment", "general",
    ]
    uncovered = [c for c in all_categories if c not in category_counts]

    # Identify high-resonance categories that are underrepresented
    high_resonance = ["economy", "health", "education", "fiscal", "security"]
    starved = [c for c in high_resonance if category_counts.get(c, 0) == 0]

    parts = [
        f"\n\n## Recent Category Distribution\n\n"
        f"Out of {total} published analyses:\n"
        + "\n".join(lines),
    ]

    if uncovered:
        parts.append(
            "\n\nCategories NOT yet covered: " + ", ".join(uncovered)
        )

    if starved:
        parts.append(
            "\n\n**Priority gaps** (high-resonance categories with ZERO coverage): "
            + ", ".join(starved)
            + ". Actively seek stories in these categories."
        )

    parts.append(
        "\n\nUse this data to diversify coverage. Categories marked ⚠️ OVER "
        "(above 40%) should only be included if the story has exceptionally "
        "high citizen impact AND no alternative from an underrepresented "
        "category exists."
    )

    return "".join(parts)


# ---------------------------------------------------------------------------
# Category diversity enforcement
# ---------------------------------------------------------------------------

CATEGORY_CAP_THRESHOLD = 40  # percent — if a category exceeds this share of
# historical analyses, cap new decisions in that category to MAX_PER_FETCH.
CATEGORY_CAP_MAX_PER_FETCH = 1  # max decisions per overrepresented category
CATEGORY_CAP_MIN_KEPT = 1  # always keep at least this many decisions after cap

# News gate: allow fetching when pending analysis issues are at or below this.
# Setting this > 0 prevents the starvation loop where the queue never refills
# because news fetching is blocked while old analyses sit unprocessed.
NEWS_GATE_MAX_PENDING = 2


def _get_historical_category_distribution() -> Counter[str]:
    """Return a Counter mapping category → count from historical analyses."""
    if not DATA_DIR.exists():
        return Counter()
    try:
        results = load_results_from_dir(DATA_DIR)
    except Exception:
        log.warning("Failed to load results for category cap enforcement")
        return Counter()
    counts: Counter[str] = Counter()
    for r in results:
        counts[r.decision.category or "general"] += 1
    return counts


def _enforce_category_caps(
    decisions: list[GovernmentDecision],
) -> list[GovernmentDecision]:
    """Drop decisions from overrepresented categories, keeping at most
    CATEGORY_CAP_MAX_PER_FETCH per category that exceeds
    CATEGORY_CAP_THRESHOLD% of historical analyses.

    Decisions are kept in their original order; within an overrepresented
    category the first decision encountered is kept.
    """
    hist = _get_historical_category_distribution()
    total = sum(hist.values())

    if total == 0:
        return decisions  # no history → no enforcement

    overrepresented: set[str] = set()
    for cat, cnt in hist.items():
        pct = 100 * cnt / total
        if pct > CATEGORY_CAP_THRESHOLD:
            overrepresented.add(cat)

    if not overrepresented:
        return decisions

    kept: list[GovernmentDecision] = []
    dropped: list[GovernmentDecision] = []
    seen: Counter[str] = Counter()
    for d in decisions:
        cat = d.category or "general"
        if cat in overrepresented:
            seen[cat] += 1
            if seen[cat] > CATEGORY_CAP_MAX_PER_FETCH:
                log.info(
                    "Category cap: dropping '%s' (category '%s' is >%d%% of "
                    "historical analyses)",
                    d.title,
                    cat,
                    CATEGORY_CAP_THRESHOLD,
                )
                dropped.append(d)
                continue
        kept.append(d)

    # Guarantee at least CATEGORY_CAP_MIN_KEPT decisions survive the cap.
    # This prevents starvation when ALL fetched decisions belong to
    # overrepresented categories — at least one still gets through.
    while len(kept) < CATEGORY_CAP_MIN_KEPT and dropped:
        rescued = dropped.pop(0)
        log.info(
            "Category cap: rescuing '%s' to meet minimum of %d kept decision(s)",
            rescued.title,
            CATEGORY_CAP_MIN_KEPT,
        )
        kept.append(rescued)

    return kept


async def step_fetch_news(*, model: str) -> list[GovernmentDecision]:
    """Run the News Scout agent to discover today's government decisions.

    Returns a list of GovernmentDecision objects (empty on failure).
    Non-fatal — logs errors and returns empty list.
    """
    from government.models.decision import GovernmentDecision

    try:
        system_prompt = _load_role_prompt("news-scout")
        today = _dt.date.today()
        prompt = system_prompt.replace("{today}", today.isoformat())
        prompt += _build_category_distribution_context()
        prompt += (
            f"\n\nFind recent Montenegrin government decisions (today is "
            f"{today.isoformat()}, look back up to 3 days)."
        )

        opts = _sdk_options(
            system_prompt=prompt,
            model=model,
            max_turns=NEWS_SCOUT_MAX_TURNS,
            allowed_tools=NEWS_SCOUT_TOOLS,
            effort="low",
        )

        lookback_start = (today - _dt.timedelta(days=2)).isoformat()
        user_prompt = (
            f"Search for Montenegrin government decisions from {lookback_start} to "
            f"{today.isoformat()}. Prefer today's decisions, but include recent ones "
            "if today is quiet. Return a JSON array of the top 3 most significant decisions."
        )

        log.info("Running News Scout agent for %s...", today.isoformat())
        raw = await _run_sdk_for_json_array(
            user_prompt, opts, agent_name="News Scout",
        )
        if not raw:
            log.info("News Scout returned no decisions for %s", today.isoformat())
            return []

        decisions: list[GovernmentDecision] = []
        for item in raw[:NEWS_SCOUT_MAX_DECISIONS]:
            try:
                # Parse date — agent should return YYYY-MM-DD
                item_date = _dt.date.fromisoformat(item.get("date", today.isoformat()))
                decision_id = _generate_decision_id(item.get("title", ""), item_date)
                decision = GovernmentDecision(
                    id=decision_id,
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    full_text=item.get("full_text", ""),
                    date=item_date,
                    source_url=item.get("source_url", ""),
                    category=item.get("category", "general"),
                    tags=item.get("tags", []),
                )
                decisions.append(decision)
            except Exception:
                log.warning("Skipping invalid news item: %s", item)

        log.info("News Scout found %d decisions for %s", len(decisions), today.isoformat())
        decisions = _enforce_category_caps(decisions)
        return decisions
    except Exception:
        log.exception("News Scout failed (non-fatal)")
        return []


def decision_already_tracked(decision_id: str) -> bool:
    """Check if a GitHub Issue already exists for this decision."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_TASK_ANALYSIS,
        "--state", "all",
        "--search", decision_id,
        "--json", "number",
        "--limit", "5",
    ], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return False
    issues = json.loads(result.stdout)
    return len(issues) > 0


def create_analysis_issue(decision: GovernmentDecision) -> int:
    """Create a GitHub Issue for analyzing a government decision.

    Embeds the full GovernmentDecision JSON in the issue body so the
    execution step can parse it directly without re-loading from file.
    """
    title = f"Analyze: {decision.title[:110]}"
    decision_json = decision.model_dump_json(indent=2)
    body = (
        f"**Decision ID**: {decision.id}\n"
        f"**Date**: {decision.date}\n"
        f"**Category**: {decision.category}\n\n"
        f"> {decision.summary}\n\n"
        f"Run full AI cabinet analysis on this decision.\n\n"
        f"<details><summary>Decision JSON</summary>\n\n"
        f"```json\n{decision_json}\n```\n</details>"
    )
    result = _gh_create_issue(
        title=title, body=body,
        labels=f"{LABEL_BACKLOG},{LABEL_TASK_ANALYSIS}",
    )
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


async def step_check_decisions(*, model: str) -> int:
    """Check for new government decisions and create analysis issues.

    Combines news scout results with seed data. Returns the number of
    new issues created.
    """
    all_decisions: list[GovernmentDecision] = []

    # News scout: fetch today's decisions (once per day)
    if should_fetch_news():
        news = await step_fetch_news(model=model)
        if news:
            all_decisions.extend(news)
            _save_news_scout_state(_dt.date.today().isoformat())
            log.info("News Scout returned %d decisions", len(news))
        else:
            log.info("News Scout returned no decisions")

    # Seed data: always load as fallback/supplement
    if SEED_DECISIONS_PATH.exists():
        seed = load_decisions(SEED_DECISIONS_PATH)
        all_decisions.extend(seed)

    if not all_decisions:
        log.info("No pending decisions found")
        return 0

    created = 0
    for decision in all_decisions:
        if decision_already_tracked(decision.id):
            log.debug("Decision %s already tracked", decision.id)
            continue
        issue_num = create_analysis_issue(decision)
        log.info("Created analysis issue #%d for decision %s", issue_num, decision.id)
        created += 1

    return created


async def step_execute_analysis(
    issue: dict[str, Any],
    *,
    model: str,
    dry_run: bool = False,
    telemetry: CycleTelemetry | None = None,
) -> bool:
    """Execute a government decision analysis. Returns True on success."""
    issue_number = issue["number"]
    title = issue["title"]
    body = issue.get("body", "")

    mark_issue_in_progress(issue_number)

    if dry_run:
        log.info("DRY RUN: would analyze issue #%d: %s", issue_number, title)
        _run_gh(["gh", "issue", "edit", str(issue_number),
                 "--remove-label", LABEL_IN_PROGRESS,
                 "--add-label", LABEL_BACKLOG])
        return True

    # Try to parse GovernmentDecision from embedded JSON in issue body
    from government.models.decision import GovernmentDecision

    decision: GovernmentDecision | None = None

    # New path: extract JSON from <details> block
    json_match = re.search(r"```json\n(.*?)\n```", body, re.DOTALL)
    if json_match:
        try:
            decision = GovernmentDecision.model_validate_json(json_match.group(1))
            log.debug("Parsed decision from embedded JSON: %s", decision.id)
        except Exception:
            log.warning("Issue #%d: embedded JSON parse failed, falling back", issue_number)

    # Fallback: extract decision ID and look up in seed data
    if decision is None:
        id_match = re.search(r"\*\*Decision ID\*\*:\s*(\S+)", body)
        if not id_match:
            reason = "Could not parse decision from issue body"
            mark_issue_failed(issue_number, reason)
            log.error("Issue #%d: %s", issue_number, reason)
            return False

        decision_id = id_match.group(1)
        if SEED_DECISIONS_PATH.exists():
            seed = load_decisions(SEED_DECISIONS_PATH)
            decision = next((d for d in seed if d.id == decision_id), None)
        if decision is None:
            reason = f"Decision {decision_id} not found"
            mark_issue_failed(issue_number, reason)
            log.error("Issue #%d: %s", issue_number, reason)
            return False

    try:
        config = SessionConfig(model=model)
        orchestrator = Orchestrator(config)
        results = await orchestrator.run_session([decision])

        if not results:
            reason = "Orchestrator returned no results"
            mark_issue_failed(issue_number, reason)
            return False

        # Pipeline health check — catch systemic failures before publishing
        health = results[0].check_health()
        if not health.passed:
            failure_details = "; ".join(health.failures)
            reason = f"Pipeline health check failed: {failure_details}"
            log.error(
                "Health check failed for issue #%d (%d/%d assessments failed): %s",
                issue_number, health.failed_assessments,
                health.total_assessments, failure_details,
            )
            mark_issue_failed(issue_number, reason)
            _log_error(
                "step_execute_analysis",
                RuntimeError(reason),
                issue_number=issue_number,
            )
            return False

        if health.failures:
            # Some components failed but not enough to block — log warnings
            log.warning(
                "Health check warnings for issue #%d: %s",
                issue_number, "; ".join(health.failures),
            )

        # Translate to Montenegrin (non-fatal — English-only is better than no publish)
        try:
            from government.output.localization import localize_result
            await localize_result(results[0], model="claude-sonnet-4-6")
            log.info("Montenegrin translations populated")
        except Exception:
            log.exception("Localization failed (non-fatal, publishing English-only)")

        # Post scorecard as issue comment
        scorecard = render_scorecard(results[0])
        _gh_comment(issue_number, f"## AI Cabinet Scorecard\n\n{scorecard}")

        # Serialize result to JSON for the static site builder
        data_dir = Path(__file__).resolve().parent.parent / "output" / "data"
        saved = save_result_json(results[0], data_dir)
        log.info("Saved result JSON to %s", saved)

        # Editorial Director review (non-fatal)
        review = None
        try:
            review = await step_editorial_review(
                result=results[0],
                issue_number=issue_number,
                model=model,
            )
        except Exception:
            log.exception("Editorial review failed (non-fatal)")

        # If review failed or was not approved, file a quality issue
        if review is not None and not review.approved:
            log.warning("Editorial Director did not approve analysis #%d (score: %d/10)",
                       issue_number, review.quality_score)
            try:
                quality_issue_num = create_editorial_quality_issue(
                    original_issue=issue_number,
                    review=review,
                    decision_id=results[0].decision.id,
                )
                _gh_comment(issue_number,
                            f"⚠️ Editorial review flagged quality issues. "
                            f"See #{quality_issue_num} for details.\n\n"
                            f"**Quality score**: {review.quality_score}/10\n"
                            f"**Issues**: {len(review.issues)}\n"
                            f"**Recommendations**: {len(review.recommendations)}")
            except Exception:
                log.exception("Failed to create editorial quality issue (non-fatal)")
        elif review is not None:
            log.info("Editorial Director approved analysis #%d (score: %d/10)",
                    issue_number, review.quality_score)

        # Post analysis tweet (non-fatal)
        try:
            if try_post_analysis(results[0]):
                log.info("Posted analysis tweet for %s", results[0].decision.id)
                if telemetry is not None:
                    telemetry.tweet_posted = True
        except Exception:
            log.exception("Analysis tweet failed (non-fatal)")

        mark_issue_done(issue_number)
        _record_analysis_completion()
        log.info("Analysis issue #%d completed successfully", issue_number)
        # Commit output data immediately so it survives crashes in later phases
        _commit_output_data()
        return True
    except Exception as exc:
        reason = f"Analysis failed: {exc}"
        mark_issue_failed(issue_number, reason)
        log.exception("Issue #%d failed", issue_number)
        _log_error("step_execute_analysis", exc, issue_number=issue_number)
        return False


async def step_editorial_review(
    *,
    result: SessionResult,
    issue_number: int,
    model: str,
) -> EditorialReview | None:
    """Run Editorial Director review of a completed analysis.

    Returns EditorialReview if successful, None if review failed.
    """
    system_prompt = _load_role_prompt("editorial-director")

    # Write result JSON to a temp file so the prompt stays small.
    # (Inlining large SessionResult JSON exceeded OS ARG_MAX.)
    result_json = result.model_dump_json(indent=2, exclude_none=True)
    fd, result_file = tempfile.mkstemp(
        suffix=".json", prefix="editorial_review_", dir=PROJECT_ROOT,
    )
    with os.fdopen(fd, "w") as fh:
        fh.write(result_json)

    prompt = f"""Review the analysis for quality and public impact.

The full analysis result is in: {result_file}
Read that file first, then provide your editorial review.

Review criteria:
1. Factual accuracy — are claims supported by the decision text?
2. Narrative quality — clear, engaging, coherent for general readers?
3. Public relevance — addresses citizen concerns, actionable insights?
4. Constitutional alignment — transparency, anti-corruption, fiscal responsibility?

Most analyses should pass. Only block publication for clear factual errors or Constitution violations.
"""

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=EDITORIAL_DIRECTOR_MAX_TURNS,
        allowed_tools=["Read"],
        effort="medium",
    )

    log.info("Running Editorial Director review for issue #%d...", issue_number)
    try:
        output = await _run_sdk_with_retry(prompt, opts)
        review_data = _parse_structured_text(output)

        if review_data is None:
            log.warning(
                "Editorial Director: no structured output, retrying with context",
            )
            output = await _run_sdk_with_retry(retry_prompt(prompt), opts)
            review_data = _parse_structured_text(output)

        if review_data is None:
            log.warning("Editorial Director returned no structured output")
            return None

        review = EditorialReview.model_validate(review_data)

        log.info(
            "Editorial review complete: %s (score: %d/10)",
            "APPROVED" if review.approved else "NEEDS IMPROVEMENT",
            review.quality_score,
        )
        return review

    except Exception:
        log.exception("Editorial review failed for issue #%d", issue_number)
        return None
    finally:
        Path(result_file).unlink(missing_ok=True)


def create_editorial_quality_issue(
    original_issue: int,
    review: EditorialReview,
    decision_id: str,
) -> int:
    """File an editorial quality issue based on review feedback."""
    title = f"Editorial quality issues in analysis: {decision_id}"

    issues_section = "\n".join(f"- {issue}" for issue in review.issues)
    recs_section = "\n".join(f"- {rec}" for rec in review.recommendations)
    strengths_list = "\n".join(f"- {strength}" for strength in review.strengths)
    strengths_section = strengths_list if review.strengths else "None noted"

    body = f"""**Editorial Director flagged quality issues in analysis #{original_issue}**

**Quality Score**: {review.quality_score}/10

**Issues Identified**:
{issues_section}

**Recommendations**:
{recs_section}

**Strengths**:
{strengths_section}

---
Original analysis issue: #{original_issue}
Decision ID: {decision_id}
"""

    result = _gh_create_issue(
        title=title, body=body,
        labels=f"{LABEL_EDITORIAL},{LABEL_BACKLOG}",
    )

    # Parse issue number from output
    match = re.search(r"/issues/(\d+)", result.stdout)
    if match:
        num = int(match.group(1))
        log.info("Created editorial quality issue #%d", num)
        return num

    log.warning("Could not parse issue number from gh output")
    return 0


# ---------------------------------------------------------------------------
# Phase B: Self-improvement (propose + debate)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 1: Propose
# ---------------------------------------------------------------------------


async def step_propose(
    *,
    num_proposals: int,
    model: str,
) -> list[dict[str, str]]:
    """PM agent proposes improvements. Returns list of {title, description, domain}."""
    all_titles = get_all_issue_titles()

    # Build context blocks for different issue categories
    context_blocks = []

    if all_titles["open"]:
        open_list = "\n".join(f"- {t}" for t in all_titles["open"])
        context_blocks.append(
            f"\n\n**Existing open issues** (DO NOT duplicate these):\n{open_list}"
        )

    if all_titles["closed"]:
        closed_list = "\n".join(f"- {t}" for t in all_titles["closed"])
        context_blocks.append(
            f"\n\n**Previously completed or rejected work** (DO NOT re-propose these):\n{closed_list}"
        )

    if all_titles["failed"]:
        failed_list = "\n".join(f"- {t}" for t in all_titles["failed"])
        context_blocks.append(
            f"\n\n**Previously failed proposals** (DO NOT re-propose these):\n{failed_list}"
        )

    existing_issues_context = "".join(context_blocks)

    prompt = f"""You are the PM for the AI Government project. Propose exactly {num_proposals} improvements.

Read these files for context:
- docs/STATUS.md
- docs/ROADMAP.md
- docs/CONTEXT.md
- Browse src/ and scripts/ to understand current implementation

IMPORTANT: Before proposing, check the existing issues listed below to avoid duplicates.
Do NOT propose anything that overlaps with existing open, closed, or failed issues.
{existing_issues_context}

Propose improvements across TWO domains:

1. **Dev fleet & workflow**: tooling, CI, testing, code quality, developer experience
2. **Government simulation**: improving analytical domain coverage, more realistic decision
   models, improving news scout accuracy and expanding sources, improving prompt quality,
   EU accession tracking, Montenegrin language accuracy

Consider:
- What analytical gaps exist in our current domain coverage?
- What real-world data sources should we ingest?
- How can we consolidate or refine analytical domains for complete policy coverage?
- How can we improve based on feedback from previous outputs?

**Issue scoping rules** — every proposal MUST be a single, well-scoped task:
- A coder should be able to implement it in ONE session without extensive exploration.
- List the specific files to change (or create) and what to do in each.
- If a feature touches more than 5 files, break it into smaller issues.
- Include concrete acceptance criteria a reviewer can verify.
- Bad: "Improve language consistency across all agents"
- Good: "Rename English ministry names to Montenegrin in government/agents/ministry_*.py"

Return ONLY a JSON array (no markdown fences) of exactly {num_proposals} objects:
[
  {{
    "title": "Short imperative title (under 80 chars)",
    "description": "2-3 sentences explaining the improvement, why it matters, and \\
acceptance criteria. List specific files to change.",
    "domain": "dev" or "government"
  }}
]
"""

    system_prompt = _load_role_prompt("pm")
    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=PROPOSE_MAX_TURNS,
        allowed_tools=PROPOSE_TOOLS,
        effort="medium",
    )

    log.info("Running PM agent to propose %d improvements...", num_proposals)
    raw = await _run_sdk_for_json_array(prompt, opts, agent_name="PM")
    if not raw:
        log.warning("PM agent returned no parseable proposals")
        return []

    proposals: list[dict[str, str]] = []
    for item in raw[:num_proposals]:
        try:
            validated = ProposalOutput.model_validate(item)
            proposals.append(validated.model_dump())
        except Exception:
            log.warning("Skipping invalid proposal: %s", item)

    log.info("PM proposed %d valid improvements", len(proposals))
    return proposals


def _parse_json_array(text: str) -> list[dict[str, str]]:
    """Extract a JSON array from agent output, tolerating surrounding text."""
    # Try direct parse first
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Find JSON array in the text
    start = text.find("[")
    if start == -1:
        return []
    # Find matching bracket
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(text[start : i + 1])
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
                break
    return []


# ---------------------------------------------------------------------------
# Step 2: Debate
# ---------------------------------------------------------------------------


async def step_debate(
    proposals: list[dict[str, Any]],
    *,
    model: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Debate each proposal. Returns (accepted, rejected) with arguments attached."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for proposal in proposals:
        title = proposal.get("title", "Untitled")
        description = proposal.get("description", "")
        domain = proposal.get("domain", "dev")
        issue_number = proposal.get("issue_number")

        log.info("Debating: %s", title)

        # If this is an AI proposal (no existing issue), create one
        if issue_number is None:
            # Map proposal domain to project domain value
            project_domain = {"dev": "Dev", "government": "Government", "human": "Human"}.get(domain, "N/A")
            issue_number = create_proposal_issue(
                title,
                f"**Domain**: {domain}\n\n{description}",
                domain=project_domain,
            )
            proposal["issue_number"] = issue_number
        else:
            # Verify existing issue is still open before debating
            if not _is_issue_open(issue_number):
                log.info("Skipping debate for #%d (already closed)", issue_number)
                continue
            # Skip if already debated
            if _issue_has_debate_comment(issue_number):
                log.info("Skipping debate for #%d (already has debate comment)", issue_number)
                continue

        # Round 1: Advocate opens, Skeptic challenges
        advocate_arg = await _run_advocate(title, description, domain, model=model)
        skeptic_challenge = await _run_skeptic_challenge(
            title, description, advocate_arg, model=model,
        )

        # Round 2: Advocate rebuts, Skeptic renders final verdict
        advocate_rebuttal = await _run_advocate_rebuttal(
            title, description, skeptic_challenge, model=model,
        )
        skeptic_verdict = await _run_skeptic_verdict(
            title, description, advocate_rebuttal, model=model,
        )

        # Deterministic judge: check if skeptic rejected in final verdict
        verdict = "REJECTED" if "VERDICT: REJECT" in skeptic_verdict else "ACCEPTED"

        # Post full debate as issue comment
        post_debate_comment(
            issue_number, advocate_arg, skeptic_challenge,
            advocate_rebuttal, skeptic_verdict, verdict,
        )

        proposal["advocate_arg"] = advocate_arg
        proposal["skeptic_challenge"] = skeptic_challenge
        proposal["advocate_rebuttal"] = advocate_rebuttal
        proposal["skeptic_verdict"] = skeptic_verdict
        proposal["verdict"] = verdict

        if verdict == "ACCEPTED":
            accept_issue(issue_number)
            accepted.append(proposal)
            log.info("ACCEPTED: %s (#%d)", title, issue_number)
        else:
            reject_issue(issue_number)
            rejected.append(proposal)
            log.info("REJECTED: %s (#%d)", title, issue_number)

    return accepted, rejected


async def _run_advocate(
    title: str,
    description: str,
    domain: str,
    *,
    model: str,
) -> str:
    """Round 1: PM argues for the proposal (~200 words)."""
    prompt = f"""Written by PM agent:

Propose this improvement for the AI Government project. Focus on why it's the
highest-impact thing to do right now.

Title: {title}
Description: {description}
Domain: {domain}

Write a concise argument (~200 words) covering:
- What concrete value does this deliver?
- Why now — what makes this the right priority?
- How does it move the project forward?
"""
    system_prompt = _load_role_prompt("pm")
    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=DEBATE_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )
    return await _run_sdk_with_retry(prompt, opts)


async def _run_skeptic_challenge(
    title: str,
    description: str,
    advocate_arg: str,
    *,
    model: str,
) -> str:
    """Round 1: Reviewer provides constructive feedback. No verdict yet."""
    prompt = f"""Written by Critic agent:

Review this proposed improvement for the AI Government project. Your goal is to
help refine the idea, not to kill it.

Title: {title}
Description: {description}

The PM argues:
{advocate_arg}

Provide constructive feedback (~200 words):
- Are there ways to scope or sharpen this to increase impact?
- Any technical risks or dependencies the PM should consider?
- Suggestions to make implementation smoother?

Flag as a **blocking concern** ONLY if the proposal:
- Is technically infeasible with the current codebase
- Violates the project constitution (ethics, transparency, public interest)
- Has a serious security or safety issue

Do NOT give a verdict yet. Just provide your feedback so the PM can refine.
"""
    system_prompt = _load_role_prompt("reviewer")
    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=DEBATE_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )
    return await _run_sdk_with_retry(prompt, opts)


async def _run_advocate_rebuttal(
    title: str,
    description: str,
    skeptic_challenge: str,
    *,
    model: str,
) -> str:
    """Round 2: PM refines the proposal based on feedback (~200 words)."""
    prompt = f"""Written by PM agent:

The critic provided feedback on your proposal. Refine the idea based on their input.

Title: {title}
Description: {description}

Critic's feedback:
{skeptic_challenge}

Write a concise response (~200 words):
- Acknowledge good suggestions and incorporate them
- If the critic raised a blocking concern, explain how you'll address it
- Adjust scope if needed based on their feedback
- Present the refined version of the proposal
"""
    system_prompt = _load_role_prompt("pm")
    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=DEBATE_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )
    return await _run_sdk_with_retry(prompt, opts)


async def _run_skeptic_verdict(
    title: str,
    description: str,
    advocate_rebuttal: str,
    *,
    model: str,
) -> str:
    """Round 2: Reviewer gives final verdict after PM refinement."""
    prompt = f"""Written by Critic agent:

The PM has refined the proposal based on your feedback. Render your final verdict.

Title: {title}
Description: {description}

PM's refined proposal:
{advocate_rebuttal}

Write a brief assessment (~100 words), then end with EXACTLY one of:

- "VERDICT: ACCEPT — <reason>" if the proposal is sound (this is the default
  for any reasonable proposal without blocking issues)
- "VERDICT: REJECT — <reason>" ONLY if there is a genuine blocking issue:
  technically infeasible, violates the constitution, or has a serious
  security/safety problem

The bar for rejection is HIGH. Style preferences, priority disagreements,
and scope concerns are NOT blocking — those get refined during implementation.
When in doubt, accept.
"""
    system_prompt = _load_role_prompt("reviewer")
    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=DEBATE_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )
    return await _run_sdk_with_retry(prompt, opts)


# ---------------------------------------------------------------------------
# Step 3: Pick
# ---------------------------------------------------------------------------


def _issue_has_label(issue: dict[str, Any], label: str) -> bool:
    """Check if an issue has a specific label."""
    labels = issue.get("labels", [])
    return any(lbl.get("name") == label for lbl in labels)


def step_pick() -> dict[str, Any] | None:
    """Pick the next backlog issue using 5-tier priority.

    Priority order:
      1. Human suggestions (human-suggestion) — always highest priority
      2. Analysis tasks (task:analysis)
      3. Strategy suggestions (strategy-suggestion) — reserved for #83
      4. Director suggestions (director-suggestion)
      5. Regular FIFO (oldest first)

    This ensures human feedback is acted on immediately rather than
    waiting behind AI-generated proposals. Within each tier, picks
    the oldest issue first (FIFO).
    """
    issues = list_backlog_issues()
    if not issues:
        log.info("No backlog issues to pick")
        return None

    # Priority order: urgent first, then human suggestions, then other categories.
    priority_labels = [
        LABEL_URGENT,          # Tier 0: Drop everything (CI broken, site down, etc.)
        LABEL_HUMAN,           # Tier 1: Human suggestions
        LABEL_TASK_ANALYSIS,   # Tier 2: Government decision analysis
        LABEL_STRATEGY,        # Tier 3: Strategic guidance (reserved)
        LABEL_DIRECTOR,        # Tier 4: Director-identified issues
        LABEL_RESEARCH_SCOUT,  # Tier 5: Research scout suggestions
    ]

    for label in priority_labels:
        for issue in issues:
            if _issue_has_label(issue, label):
                log.info(
                    "Picked [%s] issue #%d: %s", label, issue["number"], issue["title"],
                )
                return issue

    # Fall back to FIFO
    picked = issues[0]
    log.info("Picked issue #%d: %s", picked["number"], picked["title"])
    return picked


# ---------------------------------------------------------------------------
# Step 4: Execute
# ---------------------------------------------------------------------------


async def step_execute(
    issue: dict[str, Any],
    *,
    model: str,
    max_pr_rounds: int,
    dry_run: bool = False,
    telemetry: CycleTelemetry | None = None,
) -> bool:
    """Route execution by task type. Returns True on success."""
    if _issue_has_label(issue, LABEL_TASK_ANALYSIS):
        return await step_execute_analysis(issue, model=model, dry_run=dry_run, telemetry=telemetry)
    return await step_execute_code_change(
        issue, model=model, max_pr_rounds=max_pr_rounds, dry_run=dry_run,
    )


async def step_execute_code_change(
    issue: dict[str, Any],
    *,
    model: str,
    max_pr_rounds: int,
    dry_run: bool = False,
) -> bool:
    """Execute a code change issue via pr_workflow. Returns True on success."""
    issue_number = issue["number"]
    title = issue["title"]
    body = issue.get("body", "")
    task = f"{title}\n\n{body}\n\nCloses #{issue_number}"

    mark_issue_in_progress(issue_number)

    if dry_run:
        log.info("DRY RUN: would execute issue #%d: %s", issue_number, title)
        # Undo in-progress label for dry run
        _run_gh(["gh", "issue", "edit", str(issue_number),
                 "--remove-label", LABEL_IN_PROGRESS,
                 "--add-label", LABEL_BACKLOG])
        return True

    # Import pr_workflow to reuse its run_workflow function
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from pr_workflow import InfrastructureError, run_workflow

    # Make sure we're on main and up to date
    _run_gh(["git", "checkout", "main"])
    _run_gh(["git", "pull", "--ff-only"], check=False)

    try:
        await run_workflow(task, max_rounds=max_pr_rounds, model=model, issue=issue_number)
        mark_issue_done(issue_number)
        log.info("Issue #%d completed successfully", issue_number)
        return True
    except InfrastructureError as exc:
        reason = f"Infrastructure error: {exc}"
        mark_issue_failed(issue_number, reason)
        log.critical("Issue #%d hit infrastructure failure: %s", issue_number, exc)
        _log_error("step_execute_code_change", exc, issue_number=issue_number)
        raise
    except SystemExit as e:
        reason = f"PR workflow exited with code {e.code}"
        mark_issue_failed(issue_number, reason)
        log.error("Issue #%d failed: %s", issue_number, reason)
        _log_error("step_execute_code_change", e, issue_number=issue_number)
        return False
    except Exception as exc:
        reason = f"Unexpected error: {exc}"
        mark_issue_failed(issue_number, reason)
        log.exception("Issue #%d failed", issue_number)
        _log_error("step_execute_code_change", exc, issue_number=issue_number)
        return False
    finally:
        # Always return to main branch
        _run_gh(["git", "checkout", "main"], check=False)


# ---------------------------------------------------------------------------
# Phase D: Project Director — helpers
# ---------------------------------------------------------------------------


def _build_error_distribution_section(entries: list[CycleTelemetry]) -> str:
    """Summarize error types from recent telemetry cycles."""
    error_counts: Counter[str] = Counter()
    for entry in entries:
        for err in entry.errors:
            # Use first line (exception class + message prefix) as category
            pattern = err.strip().split("\n")[0][:120]
            if pattern:
                error_counts[pattern] += 1
    if not error_counts:
        return "## Error Distribution\n\nNo errors recorded in recent cycles."
    lines = [f"  {pat}: {cnt}x" for pat, cnt in error_counts.most_common(10)]
    return "## Error Type Distribution (recent cycles)\n\n" + "\n".join(lines)


def _build_agent_performance_section(entries: list[CycleTelemetry]) -> str:
    """Summarize per-phase performance stats from telemetry."""
    phase_durations: dict[str, list[float]] = {}
    phase_failures: Counter[str] = Counter()
    phase_runs: Counter[str] = Counter()
    for entry in entries:
        for phase in entry.phases:
            phase_runs[phase.phase] += 1
            phase_durations.setdefault(phase.phase, []).append(phase.duration_seconds)
            if not phase.success:
                phase_failures[phase.phase] += 1

    if not phase_runs:
        return "## Agent/Phase Performance\n\nNo phase-level data available."

    lines: list[str] = []
    for phase_id in sorted(phase_runs):
        runs = phase_runs[phase_id]
        fails = phase_failures.get(phase_id, 0)
        durations = phase_durations.get(phase_id, [])
        avg_dur = sum(durations) / len(durations) if durations else 0
        max_dur = max(durations) if durations else 0
        fail_pct = (fails / runs * 100) if runs else 0
        lines.append(
            f"  Phase {phase_id}: {runs} runs, {fails} failures ({fail_pct:.0f}%), "
            f"avg {avg_dur:.1f}s, max {max_dur:.1f}s"
        )
    return "## Agent/Phase Performance\n\n" + "\n".join(lines)


def _build_change_impact_section(all_entries: list[CycleTelemetry]) -> str:
    """Compare before/after telemetry for recently deployed code changes.

    For each closed code-change issue, finds the cycle that deployed it (via
    ``picked_issue_number``), takes 5 cycles before and up to 5 after, and
    computes yield rate, errors/cycle, phase failure rate, and avg duration.
    """
    if len(all_entries) < 6:
        return ""

    # Fetch recently closed code-change issues with self-improve:done label
    result = _run_gh([
        "gh", "issue", "list",
        "--state", "closed",
        "--label", f"{LABEL_TASK_CODE},{LABEL_DONE}",
        "--json", "number,title,closedAt,labels",
        "--limit", "15",
    ], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        issues = json.loads(result.stdout)
    except (json.JSONDecodeError, KeyError):
        return ""
    if not issues:
        return ""

    def _source_label(labels: list[dict[str, Any]]) -> str:
        names = {lbl.get("name", "") for lbl in labels}
        if LABEL_DIRECTOR in names:
            return "director-suggestion"
        if LABEL_STRATEGY in names:
            return "strategy-suggestion"
        if LABEL_HUMAN in names:
            return "human-suggestion"
        return "unknown"

    def _window_metrics(
        window: list[CycleTelemetry],
    ) -> tuple[float, float, float, float]:
        """Return (yield_pct, errors_per_cycle, phase_fail_pct, avg_duration)."""
        n = len(window)
        if n == 0:
            return (0.0, 0.0, 0.0, 0.0)
        yield_pct = sum(1 for e in window if e.cycle_yielded) / n * 100
        total_errors = sum(len(e.errors) for e in window)
        errors_per_cycle = total_errors / n
        total_phases = sum(len(e.phases) for e in window)
        failed_phases = sum(
            1 for e in window for p in e.phases if not p.success
        )
        phase_fail_pct = (failed_phases / total_phases * 100) if total_phases else 0.0
        avg_dur = sum(e.duration_seconds for e in window) / n
        return (yield_pct, errors_per_cycle, phase_fail_pct, avg_dur)

    reports: list[str] = []
    # Build an index from issue number to deploy position in telemetry
    issue_to_idx: dict[int, int] = {}
    for idx, entry in enumerate(all_entries):
        if entry.picked_issue_number is not None:
            issue_to_idx[entry.picked_issue_number] = idx

    for issue in issues:
        num = issue.get("number")
        if num is None:
            continue
        closed_at_str = issue.get("closedAt", "")

        # Find the deploy index: prefer picked_issue_number match
        deploy_idx: int | None = issue_to_idx.get(num)
        if deploy_idx is None and closed_at_str:
            # Fallback: first entry after close time
            try:
                closed_dt = datetime.fromisoformat(closed_at_str)
                for idx, entry in enumerate(all_entries):
                    if entry.started_at > closed_dt:
                        deploy_idx = idx
                        break
            except ValueError:
                continue
        if deploy_idx is None:
            continue

        # Build before/after windows
        before = all_entries[max(0, deploy_idx - 5):deploy_idx]
        after = all_entries[deploy_idx + 1:deploy_idx + 6]
        if len(after) < 3:
            continue  # not enough data yet

        b_yield, b_err, b_pfail, b_dur = _window_metrics(before)
        a_yield, a_err, a_pfail, a_dur = _window_metrics(after)

        d_yield = a_yield - b_yield
        d_err = a_err - b_err
        d_pfail = a_pfail - b_pfail
        d_dur = a_dur - b_dur

        # Determine tag
        if d_yield > 0 and d_err <= 0:
            tag = "[IMPROVED]"
        elif d_yield < 0 or d_err > 0.5:
            tag = "[REGRESSED]"
        else:
            tag = "[MIXED]"

        # Count confounders: other code-change issues that closed in the after window
        confounder_count = 0
        if after:
            after_start = all_entries[deploy_idx + 1].started_at
            after_end = after[-1].started_at
            for other in issues:
                other_num = other.get("number")
                if other_num == num or other_num is None:
                    continue
                other_closed = other.get("closedAt", "")
                if other_closed:
                    try:
                        other_dt = datetime.fromisoformat(other_closed)
                        if after_start <= other_dt <= after_end:
                            confounder_count += 1
                    except ValueError:
                        pass

        source = _source_label(issue.get("labels", []))
        deploy_date = closed_at_str[:10] if closed_at_str else "unknown"
        title = issue.get("title", "untitled")

        lines = [
            f"### #{num}: {title}",
            f"  Source: {source}  |  Deployed: {deploy_date}",
            f"  Before: yield {b_yield:.0f}%, errors/cycle {b_err:.1f}, "
            f"phase fail {b_pfail:.0f}%, avg {b_dur:.0f}s",
            f"  After:  yield {a_yield:.0f}%, errors/cycle {a_err:.1f}, "
            f"phase fail {a_pfail:.0f}%, avg {a_dur:.0f}s",
            f"  Delta:  yield {d_yield:+.0f}pp, errors {d_err:+.1f}, "
            f"phase fail {d_pfail:+.0f}pp, duration {d_dur:+.0f}s  {tag}",
        ]
        if confounder_count:
            lines.append(
                f"  Note: {confounder_count} other change(s) also deployed in this window"
            )
        reports.append("\n".join(lines))

    if not reports:
        return ""
    return (
        "## Change Impact Reports\n\n"
        "Recent system changes with before/after metrics (5-cycle windows):\n\n"
        + "\n\n".join(reports)
    )


def _build_ci_results_section() -> str:
    """Fetch recent CI workflow run conclusions from GitHub Actions."""
    result = _run_gh([
        "gh", "run", "list",
        "--branch", "main",
        "--limit", "10",
        "--json", "conclusion,event,name,createdAt,headBranch",
    ], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return "## Recent CI Runs\n\nNo CI data available (gh run list failed or empty)."
    try:
        runs = json.loads(result.stdout)
        if not runs:
            return "## Recent CI Runs\n\nNo CI runs found on main branch."
        conclusion_counts: Counter[str] = Counter()
        lines: list[str] = []
        for run in runs:
            conclusion = run.get("conclusion") or "in_progress"
            conclusion_counts[conclusion] += 1
            lines.append(
                f"  - {run.get('name', '?')}: {conclusion} "
                f"({run.get('createdAt', '?')[:10]})"
            )
        summary = ", ".join(f"{k}: {v}" for k, v in conclusion_counts.most_common())
        return (
            f"## Recent CI Runs (last {len(runs)})\n\n"
            f"Summary: {summary}\n\n" + "\n".join(lines)
        )
    except (json.JSONDecodeError, KeyError):
        return "## Recent CI Runs\n\nFailed to parse CI run data."


# ---------------------------------------------------------------------------
# Phase D: Project Director
# ---------------------------------------------------------------------------


def _prefetch_director_context(last_n_cycles: int) -> str:
    """Pre-fetch all context the Director needs (it has no tool access)."""
    sections: list[str] = []

    # 1. Telemetry
    entries = load_telemetry(TELEMETRY_PATH, last_n=last_n_cycles)
    if entries:
        telem_lines = [e.model_dump_json() for e in entries]
        sections.append(
            f"## Recent Telemetry (last {len(entries)} cycles)\n\n"
            + "\n".join(telem_lines)
        )

        # Compute yield
        yielded = sum(1 for e in entries if e.cycle_yielded)
        total = len(entries)
        pct = (yielded / total * 100) if total else 0
        sections.append(
            f"\n## Cycle Yield: {yielded}/{total} ({pct:.0f}%)\n"
        )

        # Error type distribution from telemetry
        sections.append(_build_error_distribution_section(entries))

        # Agent-level performance stats from telemetry phases
        sections.append(_build_agent_performance_section(entries))
    else:
        sections.append("## Telemetry\n\nNo telemetry data available yet.\n")

    # 1b. Structured runtime errors
    errors = load_errors(ERRORS_PATH, last_n=last_n_cycles * 3)
    if errors:
        err_lines = [e.model_dump_json() for e in errors]
        sections.append(
            f"## Recent Runtime Errors ({len(errors)} entries)\n\n"
            "Each line is a structured error with step, error_type, message, "
            "issue/PR context, and traceback. Look for recurring patterns.\n\n"
            + "\n".join(err_lines)
        )

    # 2. Recent issues
    result = _run_gh([
        "gh", "issue", "list",
        "--state", "all",
        "--json", "number,title,state,labels,createdAt",
        "--limit", "30",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        sections.append(f"## Recent Issues (up to 30)\n\n{result.stdout.strip()}")

    # 3. Recent PRs
    result = _run_gh([
        "gh", "pr", "list",
        "--state", "all",
        "--json", "number,title,state,createdAt,mergedAt,closedAt",
        "--limit", "15",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        sections.append(f"## Recent PRs (up to 15)\n\n{result.stdout.strip()}")

    # 4. Label distribution
    label_result = _run_gh([
        "gh", "issue", "list",
        "--state", "open",
        "--json", "labels",
        "--limit", "100",
    ], check=False)
    if label_result.returncode == 0 and label_result.stdout.strip():
        try:
            issues = json.loads(label_result.stdout)
            label_counts: Counter[str] = Counter()
            for issue in issues:
                for lbl in issue.get("labels", []):
                    label_counts[lbl.get("name", "")] += 1
            dist = "\n".join(f"  {k}: {v}" for k, v in label_counts.most_common())
            sections.append(f"## Open Issue Label Distribution\n\n{dist}")
        except (json.JSONDecodeError, KeyError):
            pass

    # 5. Recent CI run results
    sections.append(_build_ci_results_section())

    # 6. Open technical gap observations from PM
    gap_result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_GAP_TECHNICAL,
        "--state", "open",
        "--json", "number,title,body,createdAt",
        "--limit", "10",
    ], check=False)
    if gap_result.returncode == 0 and gap_result.stdout.strip():
        gap_issues = json.loads(gap_result.stdout)
        if gap_issues:
            gap_lines = []
            for gi in gap_issues:
                gap_lines.append(
                    f"- #{gi['number']}: {gi['title']}\n  {gi.get('body', '')[:200]}"
                )
            sections.append(
                "## Open Technical Gap Observations (from PM)\n\n"
                "The PM has identified the following technical/operational gaps.\n"
                "Review each one and decide whether to act (file a fix/staffing issue) "
                "or dismiss. Close the gap issue either way, with a comment explaining "
                "your decision.\n\n"
                + "\n".join(gap_lines)
            )

    # 7. Change impact reports (before/after metrics for past code changes)
    all_entries = load_telemetry(TELEMETRY_PATH)
    impact = _build_change_impact_section(all_entries)
    if impact:
        sections.append(impact)

    return "\n\n".join(sections)


async def step_director(*, model: str, director_interval: int) -> list[int]:
    """Run the Project Director agent. Returns list of created issue numbers."""
    context = _prefetch_director_context(last_n_cycles=director_interval * 2)

    system_prompt = _load_role_prompt("director")
    prompt = f"""Review the operational data below and identify systemic problems.

{context}

Based on this data, output a JSON array of 0-2 issues to file.
Each issue should target a root cause, not a symptom.
If the system is healthy, output an empty array: []

Format:
[
  {{"title": "Short imperative title", "description": "What to change, which file, and why"}}
]
"""

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=DIRECTOR_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )

    log.info("Running Project Director agent...")
    raw = await _run_sdk_for_json_array(prompt, opts, agent_name="Director")

    created: list[int] = []
    for item in raw[:2]:  # Hard cap at 2
        try:
            validated = DirectorOutput.model_validate(item)
        except Exception:
            log.warning("Skipping invalid Director output: %s", item)
            continue
        num = create_director_issue(validated.title, validated.description)
        log.info("Director filed issue #%d: %s", num, validated.title)
        created.append(num)

    return created


# ---------------------------------------------------------------------------
# Phase E: Strategic Director — helpers
# ---------------------------------------------------------------------------


def _build_agent_roster_section() -> str:
    """Return a markdown section listing current ministry agents and their domains."""
    from government.agents.ministry_economy import create_economy_agent
    from government.agents.ministry_education import create_education_agent
    from government.agents.ministry_eu import create_eu_agent
    from government.agents.ministry_finance import create_finance_agent
    from government.agents.ministry_health import create_health_agent
    from government.agents.ministry_interior import create_interior_agent
    from government.agents.ministry_justice import create_justice_agent

    factories = [
        create_finance_agent,
        create_justice_agent,
        create_eu_agent,
        create_health_agent,
        create_interior_agent,
        create_education_agent,
        create_economy_agent,
    ]
    lines: list[str] = []
    for factory in factories:
        agent = factory(None)
        areas = ", ".join(agent.ministry.focus_areas)
        lines.append(f"  - {agent.ministry.name} ({agent.ministry.slug}): {areas}")
    return "## Current Agent Roster\n\n" + "\n".join(lines)


def _build_skipped_news_section() -> str:
    """Return a markdown section with skipped/rejected news items from GitHub issues."""
    result = _run_gh([
        "gh", "issue", "list",
        "--state", "closed",
        "--label", LABEL_REJECTED,
        "--json", "title,closedAt",
        "--limit", "10",
    ], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return "## Skipped/Rejected Items\n\nNo rejected issues found."
    try:
        issues = json.loads(result.stdout)
        if not issues:
            return "## Skipped/Rejected Items\n\nNo rejected issues found."
        lines = [f"  - {iss.get('title', '?')} (closed {iss.get('closedAt', '?')[:10]})"
                 for iss in issues]
        return f"## Skipped/Rejected Items (last {len(issues)})\n\n" + "\n".join(lines)
    except (json.JSONDecodeError, KeyError):
        return "## Skipped/Rejected Items\n\nFailed to parse rejected issues."


# ---------------------------------------------------------------------------
# Phase E: Strategic Director
# ---------------------------------------------------------------------------


def _prefetch_strategic_context(last_n_cycles: int) -> str:
    """Pre-fetch all context the Strategic Director needs (no tool access)."""
    sections: list[str] = []

    # 1. Recent telemetry (focusing on output yield)
    entries = load_telemetry(TELEMETRY_PATH, last_n=last_n_cycles)
    if entries:
        telem_lines = [e.model_dump_json() for e in entries]
        sections.append(
            f"## Recent Telemetry (last {len(entries)} cycles)\n\n"
            + "\n".join(telem_lines)
        )

        # Tweet posting stats
        tweets_posted = sum(1 for e in entries if e.tweet_posted)
        sections.append(
            f"\n## Social Media Activity: {tweets_posted}/{len(entries)} cycles posted tweets\n"
        )
    else:
        sections.append("## Telemetry\n\nNo telemetry data available yet.\n")

    # 1b. Structured runtime errors
    errors = load_errors(ERRORS_PATH, last_n=last_n_cycles * 3)
    if errors:
        err_lines = [e.model_dump_json() for e in errors]
        sections.append(
            f"## Recent Runtime Errors ({len(errors)} entries)\n\n"
            "Each line is a structured error with step, error_type, message, "
            "issue/PR context, and traceback. Look for recurring patterns.\n\n"
            + "\n".join(err_lines)
        )

    # 2. Recent published analyses + domain/topic distribution
    if DATA_DIR.exists():
        try:
            results = load_results_from_dir(DATA_DIR)
            sections.append(
                f"## Published Analyses: {len(results)} total\n\n"
                f"Most recent: {[r.decision.title[:50] for r in results[:3]]}"
            )

            # Domain/topic distribution from published analyses
            category_counts: Counter[str] = Counter()
            ministry_counts: Counter[str] = Counter()
            for r in results:
                category_counts[r.decision.category or "general"] += 1
                for a in r.assessments:
                    ministry_counts[a.ministry] += 1
            if category_counts:
                cat_lines = "\n".join(
                    f"  {cat}: {cnt}" for cat, cnt in category_counts.most_common()
                )
                sections.append(
                    f"## Analysis Domain Distribution (by decision category)\n\n{cat_lines}"
                )
            if ministry_counts:
                min_lines = "\n".join(
                    f"  {m}: {cnt} assessments" for m, cnt in ministry_counts.most_common()
                )
                sections.append(
                    f"## Ministry Assessment Activity\n\n{min_lines}"
                )
        except Exception as exc:
            log.warning("Failed to load results for strategic context: %s", exc)

    # 3. Current agent roster (ministry agents and their domains)
    sections.append(_build_agent_roster_section())

    # 4. Issue distribution by type
    result = _run_gh([
        "gh", "issue", "list",
        "--state", "all",
        "--json", "labels,state,createdAt",
        "--limit", "100",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        try:
            issues = json.loads(result.stdout)
            label_counts: Counter[str] = Counter()
            for issue in issues:
                for lbl in issue.get("labels", []):
                    label_counts[lbl.get("name", "")] += 1
            dist = "\n".join(f"  {k}: {v}" for k, v in label_counts.most_common())
            sections.append(f"## Issue Type Distribution\n\n{dist}")
        except (json.JSONDecodeError, KeyError):
            pass

    # 5. Skipped/rejected news items (topics we saw but didn't analyze)
    sections.append(_build_skipped_news_section())

    # 6. Open content gap observations from PM
    gap_result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_GAP_CONTENT,
        "--state", "open",
        "--json", "number,title,body,createdAt",
        "--limit", "10",
    ], check=False)
    if gap_result.returncode == 0 and gap_result.stdout.strip():
        gap_issues = json.loads(gap_result.stdout)
        if gap_issues:
            gap_lines = []
            for gi in gap_issues:
                gap_lines.append(
                    f"- #{gi['number']}: {gi['title']}\n  {gi.get('body', '')[:200]}"
                )
            sections.append(
                "## Open Content Gap Observations (from PM)\n\n"
                "The PM has identified the following content/coverage gaps.\n"
                "Review each one and decide whether to act (file a staffing/fix issue) "
                "or dismiss. Close the gap issue either way, with a comment explaining "
                "your decision.\n\n"
                + "\n".join(gap_lines)
            )

    # 7. Change impact reports (before/after metrics for past code changes)
    all_entries = load_telemetry(TELEMETRY_PATH)
    impact = _build_change_impact_section(all_entries)
    if impact:
        sections.append(impact)

    # Placeholder for future metrics
    sections.append(
        "\n## Future Metrics (not yet implemented)\n\n"
        "- X/Twitter analytics (impressions, engagement, follower growth)\n"
        "- Site traffic (visitors, page views, time on site)\n"
        "- API costs and budget trends\n"
        "- Media mentions and citations\n"
    )

    return "\n\n".join(sections)


async def step_strategic_director(
    *, model: str, strategic_interval: int
) -> list[int]:
    """Run the Strategic Director agent. Returns list of created issue numbers."""
    context = _prefetch_strategic_context(last_n_cycles=strategic_interval * 2)

    system_prompt = _load_role_prompt("strategic-director")
    prompt = f"""Review the external impact data below and identify strategic opportunities.

{context}

Based on this data, output a JSON array of 0-2 strategic issues to file.
Focus on:
- Public reach and engagement
- Content resonance with the news cycle
- Sustainability (costs, scaling)
- Capability gaps that no existing agent covers
- Organizational growth (new agent roles needed)

If no strategic issues need attention, output an empty array: []

Format:
[
  {{"title": "Short imperative title", "description": "Strategic action, why it matters, expected impact"}}
]
"""

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=STRATEGIC_DIRECTOR_MAX_TURNS,
        allowed_tools=[],
        effort="medium",
    )

    log.info("Running Strategic Director agent...")
    raw = await _run_sdk_for_json_array(prompt, opts, agent_name="Strategic Director")

    created: list[int] = []
    for item in raw[:2]:  # Hard cap at 2
        try:
            validated = StrategicDirectorOutput.model_validate(item)
        except Exception:
            log.warning("Skipping invalid Strategic Director output: %s", item)
            continue
        num = create_strategic_director_issue(validated.title, validated.description)
        log.info("Strategic Director filed issue #%d: %s", num, validated.title)
        created.append(num)

    return created


# ---------------------------------------------------------------------------
# Phase F: Research Scout — helpers
# ---------------------------------------------------------------------------


def _prefetch_research_scout_context() -> tuple[str, str]:
    """Pre-fetch AI stack doc and existing open research-scout issues for dedup.

    Returns (ai_stack_context, existing_issues).
    """
    ai_stack_path = PROJECT_ROOT / "docs" / "AI_STACK.md"
    ai_stack_context = ai_stack_path.read_text() if ai_stack_path.exists() else "(AI_STACK.md not found)"

    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_RESEARCH_SCOUT,
        "--state", "open",
        "--json", "number,title",
        "--limit", "20",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        try:
            issues = json.loads(result.stdout)
            if issues:
                lines = [f"- #{i['number']}: {i['title']}" for i in issues]
                existing_issues = "\n".join(lines)
            else:
                existing_issues = "No open research-scout issues."
        except (json.JSONDecodeError, KeyError):
            existing_issues = "No open research-scout issues."
    else:
        existing_issues = "No open research-scout issues."

    return ai_stack_context, existing_issues


# ---------------------------------------------------------------------------
# Phase F: Research Scout
# ---------------------------------------------------------------------------


async def step_research_scout(*, model: str) -> list[int]:
    """Run the Research Scout agent. Returns list of created issue numbers."""
    ai_stack_context, existing_issues = _prefetch_research_scout_context()

    system_prompt = _load_role_prompt("research-scout")
    system_prompt = system_prompt.replace("{ai_stack_context}", ai_stack_context)
    system_prompt = system_prompt.replace("{existing_issues}", existing_issues)

    prompt = (
        "Scan for recent AI ecosystem developments that could improve this project. "
        "Check model releases, SDK updates, and agent architecture patterns. "
        "Return a JSON array of 0-2 actionable issues, or [] if nothing new."
    )

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=RESEARCH_SCOUT_MAX_TURNS,
        allowed_tools=RESEARCH_SCOUT_TOOLS,
        effort="low",
    )

    log.info("Running Research Scout agent...")
    raw = await _run_sdk_for_json_array(prompt, opts, agent_name="Research Scout")

    created: list[int] = []
    for item in raw[:RESEARCH_SCOUT_MAX_ISSUES]:
        try:
            validated = ResearchScoutOutput.model_validate(item)
        except Exception:
            log.warning("Skipping invalid Research Scout output: %s", item)
            continue
        num = create_research_scout_issue(validated.title, validated.description)
        log.info("Research Scout filed issue #%d: %s", num, validated.title)
        created.append(num)

    # Persist state so the scout doesn't run again until next interval
    _save_research_scout_state(_dt.date.today().isoformat())

    return created


# ---------------------------------------------------------------------------
# Conductor — context, journal, LLM call, dispatcher
# ---------------------------------------------------------------------------

# Analysis lifecycle labels (separate from self-improve:* labels)
LABEL_ANALYSIS_PENDING = "analysis:pending"
LABEL_ANALYSIS_IN_PROGRESS = "analysis:in-progress"
LABEL_ANALYSIS_DONE = "analysis:done"
LABEL_ANALYSIS_FAILED = "analysis:failed"

ANALYSIS_LABELS: dict[str, str] = {
    LABEL_ANALYSIS_PENDING: "c5def5",      # pale blue
    LABEL_ANALYSIS_IN_PROGRESS: "fbca04",  # yellow
    LABEL_ANALYSIS_DONE: "6f42c1",         # purple
    LABEL_ANALYSIS_FAILED: "d73a4a",       # red
}


def _load_conductor_journal(last_n: int = 10) -> list[dict[str, str]]:
    """Load the last N entries from the Conductor journal."""
    if not CONDUCTOR_JOURNAL_PATH.exists():
        return []
    lines = CONDUCTOR_JOURNAL_PATH.read_text().strip().splitlines()
    entries: list[dict[str, str]] = []
    for line in lines[-last_n:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            log.debug("Skipping unparseable journal line")
    return entries


def _append_conductor_journal(
    reasoning: str,
    notes: str,
    actions: list[str],
) -> None:
    """Append a Conductor journal entry."""
    CONDUCTOR_JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "reasoning": reasoning[:500],
        "notes_for_next_cycle": notes[:300],
        "actions": actions,
    }
    with CONDUCTOR_JOURNAL_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _compute_action_frequency(entries: list[CycleTelemetry]) -> str:
    """Compute action frequency from recent telemetry conductor_actions."""
    counts: Counter[str] = Counter()
    for entry in entries:
        for action_name in entry.conductor_actions:
            counts[action_name] += 1
    if not counts:
        return "No action frequency data yet (first cycles)."
    parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
    return ", ".join(parts)


def _prefetch_conductor_context(
    *,
    cycle: int,
    productive_cycles: int,
    dry_run: bool,
    model: str,
) -> str:
    """Assemble all context the Conductor needs to decide what to do this cycle."""
    sections: list[str] = []

    sections.append(
        f"## Cycle Metadata\n\n"
        f"- Cycle number: {cycle}\n"
        f"- Productive cycles so far: {productive_cycles}\n"
        f"- Dry run: {dry_run}\n"
        f"- Model: {model}\n"
        f"- Current time: {datetime.now(UTC).isoformat()}\n"
    )

    # Telemetry (last 20 cycles)
    entries = load_telemetry(TELEMETRY_PATH, last_n=20)
    if entries:
        telem_lines = [e.model_dump_json() for e in entries]
        sections.append(
            f"## Recent Telemetry (last {len(entries)} cycles)\n\n"
            + "\n".join(telem_lines)
        )
    else:
        sections.append("## Recent Telemetry\n\nNo telemetry data yet (first cycle).\n")

    # Errors (last 30)
    errors = load_errors(ERRORS_PATH, last_n=30)
    if errors:
        err_lines = [e.model_dump_json() for e in errors]
        sections.append(
            f"## Recent Errors ({len(errors)} entries)\n\n"
            + "\n".join(err_lines)
        )

    # Backlog issues
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_BACKLOG,
        "--state", "open",
        "--json", "number,title,labels,createdAt",
        "--limit", "50",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        issues = json.loads(result.stdout)
        if issues:
            lines = []
            for iss in issues:
                labels = [lbl["name"] for lbl in iss.get("labels", [])]
                age_str = iss.get("createdAt", "")[:10]
                lines.append(f"- #{iss['number']}: {iss['title']} [{', '.join(labels)}] (created {age_str})")
            sections.append(f"## Backlog Issues ({len(issues)} open)\n\n" + "\n".join(lines))
        else:
            sections.append("## Backlog Issues\n\nBacklog is empty.\n")
    else:
        sections.append("## Backlog Issues\n\nBacklog is empty.\n")

    # Recently completed issues (last 10)
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_DONE,
        "--state", "closed",
        "--json", "number,title,closedAt",
        "--limit", "10",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        done_issues = json.loads(result.stdout)
        if done_issues:
            lines = [
                f"- #{i['number']}: {i['title']} (closed {i.get('closedAt', '')[:10]})"
                for i in done_issues
            ]
            sections.append(
                f"## Recently Completed Issues ({len(done_issues)})\n\n"
                + "\n".join(lines)
            )

    # Recently failed issues (last 10)
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_FAILED,
        "--state", "closed",
        "--json", "number,title,closedAt",
        "--limit", "10",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        failed_issues = json.loads(result.stdout)
        if failed_issues:
            lines = [
                f"- #{i['number']}: {i['title']} (closed {i.get('closedAt', '')[:10]})"
                for i in failed_issues
            ]
            sections.append(
                f"## Recently Failed Issues ({len(failed_issues)})\n\n"
                + "\n".join(lines)
            )

    # Recently rejected proposals (last 5)
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_REJECTED,
        "--state", "closed",
        "--json", "number,title,closedAt",
        "--limit", "5",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        rejected = json.loads(result.stdout)
        if rejected:
            lines = [f"- #{i['number']}: {i['title']}" for i in rejected]
            sections.append(f"## Recently Rejected Proposals ({len(rejected)})\n\n" + "\n".join(lines))

    # Open PRs
    result = _run_gh([
        "gh", "pr", "list",
        "--state", "open",
        "--json", "number,title,createdAt",
        "--limit", "10",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        prs = json.loads(result.stdout)
        if prs:
            lines = [f"- PR #{p['number']}: {p['title']}" for p in prs]
            sections.append(f"## Open PRs ({len(prs)})\n\n" + "\n".join(lines))

    # Recently merged PRs (last 10)
    result = _run_gh([
        "gh", "pr", "list",
        "--state", "merged",
        "--json", "number,title,mergedAt",
        "--limit", "10",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        merged = json.loads(result.stdout)
        if merged:
            lines = [
                f"- PR #{p['number']}: {p['title']} "
                f"(merged {p.get('mergedAt', '')[:10]})"
                for p in merged
            ]
            sections.append(
                f"## Recently Merged PRs ({len(merged)})\n\n"
                + "\n".join(lines)
            )

    # Rate-limit state
    can_analyze = should_run_analysis()
    wait = analysis_wait_seconds()
    sections.append(
        f"## Rate Limiting\n\n"
        f"- Analysis allowed now: {can_analyze}\n"
        f"- Seconds until next analysis window: {wait}\n"
    )

    # News Scout state
    can_fetch = should_fetch_news()
    sections.append(f"- News Scout can run: {can_fetch}\n")

    # Research Scout state
    can_research = should_run_research_scout()
    sections.append(f"- Research Scout can run: {can_research}\n")

    # Tweet backlog
    try:
        unposted = load_unposted_from_dir(DATA_DIR)
        unposted_ids = [r.decision.id for r in unposted[:5]]
        sections.append(
            f"## Tweet Backlog\n\n"
            f"- Unposted analyses: {len(unposted)}\n"
            + (f"- IDs: {', '.join(unposted_ids)}\n" if unposted_ids else "")
            + ("- Action: include `post_pending_tweets` to drain backlog\n"
               if unposted else "- No action needed\n")
        )
    except Exception:
        log.debug("Failed to load tweet backlog for conductor context", exc_info=True)

    # Director timing
    sections.append(
        f"## Director Timing\n\n"
        f"- Productive cycles: {productive_cycles}\n"
        f"- Director baseline: every ~5 productive cycles\n"
        f"- Strategic Director baseline: every ~10 productive cycles\n"
    )

    # CI status (last 10 runs)
    sections.append(_build_ci_results_section())

    # Action frequency from telemetry
    freq = _compute_action_frequency(entries)
    sections.append(
        f"## Action Frequency (last {len(entries)} cycles)\n\n"
        f"{freq}\n\n"
        f"Baseline rates for reference:\n"
        f"- fetch_news: ~1x/day\n"
        f"- propose + debate: ~1x/cycle when improvement backlog is empty\n"
        f"- pick_and_execute: ~1x/cycle (core productive action)\n"
        f"- director: ~every 5 productive cycles\n"
        f"- strategic_director: ~every 10 productive cycles\n"
        f"- research_scout: ~1x/week\n"
    )

    # Analysis category distribution (helps conductor diversify topic picks)
    cat_dist = _build_category_distribution_context()
    if cat_dist:
        sections.append(cat_dist.strip())

    # Conductor journal (last 10 entries)
    journal = _load_conductor_journal(last_n=10)
    if journal:
        journal_lines = [
            f"- [{j.get('timestamp', '')[:16]}] actions={j.get('actions', [])} "
            f"notes={j.get('notes_for_next_cycle', '')}"
            for j in journal
        ]
        sections.append(
            f"## Conductor Journal (last {len(journal)} entries)\n\n"
            + "\n".join(journal_lines)
        )

    return "\n\n".join(sections)


def _default_plan(
    *,
    productive_cycles: int,
    dry_run: bool,
    sdk_down: bool = False,
) -> ConductorPlan:
    """Build a safe default plan when both Conductor and recovery agent fail.

    When ``sdk_down`` is True, the API/SDK is unreachable — all LLM-dependent
    actions would fail too.  Return a ``skip_cycle`` plan so the loop backs off
    gracefully instead of burning through the circuit breaker.
    """
    if sdk_down:
        return ConductorPlan(
            reasoning="SDK/API appears down — skipping cycle to avoid wasted calls",
            actions=[ConductorAction(action="skip_cycle", reason="SDK/API unreachable")],
            suggested_cooldown_seconds=300,
            notes_for_next_cycle="SDK was down; skipped cycle",
        )

    actions: list[ConductorAction] = []

    if should_fetch_news():
        actions.append(ConductorAction(
            action="fetch_news",
            reason="Default: news not yet fetched today",
        ))

    backlog = list_backlog_issues()
    non_analysis = [i for i in backlog if not _issue_has_label(i, LABEL_TASK_ANALYSIS)]
    if not non_analysis:
        actions.append(ConductorAction(
            action="propose",
            reason="Default: improvement backlog empty",
        ))

    # Pick an issue to execute
    if backlog:
        # Use simple priority: urgent > human > analysis > director > FIFO
        picked = None
        priority_labels = [LABEL_URGENT, LABEL_HUMAN, LABEL_TASK_ANALYSIS, LABEL_DIRECTOR]
        for label in priority_labels:
            for issue in backlog:
                if _issue_has_label(issue, label):
                    picked = issue
                    break
            if picked:
                break
        if not picked:
            picked = backlog[0]
        actions.append(ConductorAction(
            action="pick_and_execute",
            reason="Default: execute next backlog item",
            issue_number=picked["number"],
        ))

    return ConductorPlan(
        reasoning="Default plan (Conductor and recovery agent both failed)",
        actions=actions,
        suggested_cooldown_seconds=60,
        notes_for_next_cycle="Previous cycle used default plan due to Conductor failure",
    )


async def _run_conductor(
    *,
    cycle: int,
    productive_cycles: int,
    dry_run: bool,
    model: str,
) -> ConductorPlan:
    """Run the Conductor agent to decide this cycle's actions.

    Falls back to recovery agent, then default plan.
    """
    context = _prefetch_conductor_context(
        cycle=cycle,
        productive_cycles=productive_cycles,
        dry_run=dry_run,
        model=model,
    )

    system_prompt = _load_role_prompt("conductor")
    prompt = f"""Decide what actions to take this cycle.

{context}

Output a single JSON object with this schema:
{{
  "reasoning": "Brief explanation of your decision (2-4 sentences)",
  "actions": [
    {{
      "action": "<action_name>",
      "reason": "Why this action now",
      "issue_number": null,
      "title": null,
      "description": null,
      "seconds": null
    }}
  ],
  "suggested_cooldown_seconds": 60,
  "notes_for_next_cycle": "Brief observations to carry forward"
}}

Remember:
- pick_and_execute requires issue_number (specify which backlog issue)
- file_issue requires title and description
- cooldown requires seconds
- Maximum 6 actions per cycle
- When uncertain, prefer the standard order: fetch_news → propose → debate → pick_and_execute
"""

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=1,
        allowed_tools=[],
        effort="low",
    )

    sdk_failures = 0

    try:
        log.info("Running Conductor agent...")
        output = await _run_sdk_with_retry(prompt, opts)

        # Parse JSON object from output
        plan = _parse_conductor_plan(output)
        if plan is not None:
            return plan
        log.warning("Conductor returned no valid plan, trying recovery agent")
    except Exception as exc:
        if _is_sdk_transient_error(exc):
            sdk_failures += 1
            log.warning("Conductor failed with transient SDK error: %s", exc)
        else:
            log.exception("Conductor agent failed, trying recovery agent")

    # Recovery agent
    try:
        plan = await _run_recovery_agent(
            cycle=cycle,
            productive_cycles=productive_cycles,
            dry_run=dry_run,
            model=model,
        )
        if plan is not None:
            return plan
        log.warning("Recovery agent returned no valid plan, using default")
    except Exception as exc:
        if _is_sdk_transient_error(exc):
            sdk_failures += 1
            log.warning("Recovery agent failed with transient SDK error: %s", exc)
        else:
            log.exception("Recovery agent also failed, using default plan")

    return _default_plan(
        productive_cycles=productive_cycles,
        dry_run=dry_run,
        sdk_down=sdk_failures >= 2,
    )


def _is_sdk_transient_error(exc: BaseException) -> bool:
    """Check if an exception looks like a transient SDK/API outage."""
    if isinstance(exc, TimeoutError):
        return True
    msg = str(exc)
    return any(sig in msg for sig in SDK_TRANSIENT_SIGNATURES)


def _parse_conductor_plan(text: str) -> ConductorPlan | None:
    """Extract a ConductorPlan JSON object from agent output."""
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return ConductorPlan.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass

    # Find JSON object in the text
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start : i + 1])
                    if isinstance(data, dict):
                        return ConductorPlan.model_validate(data)
                except (json.JSONDecodeError, Exception):
                    pass
                break
    return None


async def _run_recovery_agent(
    *,
    cycle: int,
    productive_cycles: int,
    dry_run: bool,
    model: str,
) -> ConductorPlan | None:
    """Recovery agent with tool access to investigate and decide what to do."""
    system_prompt = _load_role_prompt("recovery")
    prompt = f"""The Conductor agent failed to produce a valid plan for cycle {cycle}.

You have tool access to investigate what's going on. Check:
1. Recent git log for merged PRs
2. Error logs in output/data/errors.jsonl
3. Telemetry in output/data/telemetry.jsonl
4. Open issues via `gh issue list`

Then decide what this cycle should do. Output a JSON object with the ConductorPlan schema:
{{
  "reasoning": "What you found and why you chose these actions",
  "actions": [
    {{"action": "<action_name>", "reason": "...",
      "issue_number": null, "title": null,
      "description": null, "seconds": null}}
  ],
  "suggested_cooldown_seconds": 60,
  "notes_for_next_cycle": "..."
}}

Context:
- Cycle: {cycle}, Productive cycles: {productive_cycles}, Dry run: {dry_run}
- Valid actions: fetch_news, propose, debate, pick_and_execute,
  director, strategic_director, research_scout, cooldown, halt,
  file_issue, skip_cycle
- pick_and_execute requires issue_number
- file_issue requires title and description
- Maximum 6 actions
"""

    opts = _sdk_options(
        system_prompt=system_prompt,
        model=model,
        max_turns=10,
        allowed_tools=["Bash", "Read", "Grep", "Glob"],
        effort="medium",
    )

    log.info("Running recovery agent...")
    output = await _run_sdk_with_retry(prompt, opts)
    return _parse_conductor_plan(output)


async def _dispatch_action(
    action: ConductorAction,
    *,
    telemetry: CycleTelemetry,
    model: str,
    max_pr_rounds: int,
    dry_run: bool,
    productive_cycles: int,
    pending_proposals: list[dict[str, Any]],
) -> str | None:
    """Execute a single Conductor action. Returns 'halt' to stop the loop."""
    t0 = time.monotonic()
    phase = CyclePhaseResult(phase=action.action)

    try:
        match action.action:
            case "fetch_news":
                new_issues = await step_check_decisions(model=model)
                telemetry.decisions_found = new_issues
                telemetry.analysis_issues_created = new_issues
                phase.detail = f"created {new_issues} issues"

            case "propose":
                backlog = list_backlog_issues()
                non_analysis = [i for i in backlog if not _issue_has_label(i, LABEL_TASK_ANALYSIS)]
                if non_analysis:
                    log.info("Skipping proposals: %d improvement issues in backlog", len(non_analysis))
                    phase.detail = f"skipped ({len(non_analysis)} issues in backlog)"
                else:
                    # Graceful degradation: if the SDK crashes after all retries,
                    # treat as 0 proposals instead of failing the entire phase.
                    # Human suggestion ingestion can still proceed.
                    proposals: list[dict[str, str]] = []
                    try:
                        proposals = await step_propose(
                            num_proposals=DEFAULT_PROPOSALS_PER_CYCLE, model=model,
                        )
                    except Exception as propose_exc:
                        if _is_sdk_transient_error(propose_exc):
                            log.warning(
                                "Propose failed with transient SDK error after retries, "
                                "continuing with 0 proposals: %s",
                                propose_exc,
                            )
                        else:
                            raise
                    telemetry.proposals_made = len(proposals)
                    pending_proposals.extend(proposals)
                    # Ingest human suggestions
                    human_issues = list_human_suggestions()
                    human_accepted = 0
                    for h in human_issues:
                        issue_num = h["number"]
                        author = h.get("author", {}).get("login", "")
                        if not _is_privileged_user(author):
                            _run_gh([
                                "gh", "issue", "close", str(issue_num),
                                "--comment",
                                "Closed: human-suggestion issues are restricted to project maintainers.",
                            ], check=False)
                            _run_gh([
                                "gh", "issue", "edit", str(issue_num),
                                "--remove-label", LABEL_HUMAN,
                            ], check=False)
                            continue
                        result = _run_gh([
                            "gh", "issue", "view", str(issue_num),
                            "--json", "labels", "-q", ".labels[].name",
                        ], check=False)
                        label_names = result.stdout.strip()
                        already_processed = (
                            LABEL_BACKLOG in label_names
                            or LABEL_IN_PROGRESS in label_names
                            or LABEL_DONE in label_names
                            or LABEL_FAILED in label_names
                        )
                        if already_processed:
                            continue
                        accept_issue(issue_num)
                        human_accepted += 1
                    telemetry.human_suggestions_ingested = human_accepted
                    phase.detail = f"{len(proposals)} proposals, {human_accepted} human suggestions"

            case "debate":
                # Debate any undebated proposed issues from GitHub
                result = _run_gh([
                    "gh", "issue", "list",
                    "--label", LABEL_PROPOSED,
                    "--state", "open",
                    "--json", "number,title,body,labels",
                    "--limit", "10",
                ], check=False)
                proposals_to_debate: list[dict[str, Any]] = []
                if result.returncode == 0 and result.stdout.strip():
                    proposed_issues = json.loads(result.stdout)
                    for iss in proposed_issues:
                        if not _issue_has_debate_comment(iss["number"]):
                            proposals_to_debate.append({
                                "title": iss["title"],
                                "description": iss.get("body", ""),
                                "domain": "dev",
                                "issue_number": iss["number"],
                            })
                # Merge in-memory proposals from the propose phase
                # (issue_number=None triggers step_debate to create GH issues)
                for prop in pending_proposals:
                    proposals_to_debate.append({
                        "title": prop.get("title", "Untitled"),
                        "description": prop.get("description", ""),
                        "domain": prop.get("domain", "dev"),
                        "issue_number": None,
                    })
                pending_proposals.clear()
                if proposals_to_debate:
                    accepted, rejected = await step_debate(proposals_to_debate, model=model)
                    telemetry.proposals_accepted = len(accepted)
                    telemetry.proposals_rejected = len(rejected)
                    phase.detail = f"{len(accepted)} accepted, {len(rejected)} rejected"
                else:
                    phase.detail = "no proposals to debate"

            case "pick_and_execute":
                if action.issue_number is None:
                    log.error("pick_and_execute requires issue_number")
                    phase.success = False
                    phase.detail = "missing issue_number"
                else:
                    # Fetch the issue details
                    result = _run_gh([
                        "gh", "issue", "view", str(action.issue_number),
                        "--json", "number,title,body,labels,state",
                    ], check=False)
                    if result.returncode != 0 or not result.stdout.strip():
                        log.error("Could not fetch issue #%d", action.issue_number)
                        phase.success = False
                        phase.detail = f"issue #{action.issue_number} not found"
                    else:
                        issue = json.loads(result.stdout)
                        if issue.get("state", "").upper() != "OPEN":
                            log.warning("Issue #%d is not open, skipping", action.issue_number)
                            phase.detail = f"issue #{action.issue_number} not open"
                        else:
                            telemetry.picked_issue_number = action.issue_number
                            is_analysis = _issue_has_label(issue, LABEL_TASK_ANALYSIS)
                            task_type = "analysis" if is_analysis else "code-change"
                            telemetry.picked_issue_type = task_type
                            title = issue.get("title", "")
                            print(f"  Executing [{task_type}]: #{action.issue_number} — {title}")
                            try:
                                success = await step_execute(
                                    issue, model=model, max_pr_rounds=max_pr_rounds, dry_run=dry_run,
                                    telemetry=telemetry,
                                )
                            except Exception as exc:
                                if isinstance(exc, _get_infrastructure_error()):
                                    log.critical("Infrastructure failure — halting loop")
                                    telemetry.errors.append(f"pick_and_execute [INFRASTRUCTURE]: {exc}")
                                    telemetry.execution_success = False
                                    phase.success = False
                                    phase.detail = f"infrastructure error: {exc}"
                                    phase.duration_seconds = time.monotonic() - t0
                                    telemetry.phases.append(phase)
                                    return "halt"
                                raise
                            telemetry.execution_success = success
                            phase.success = success
                            phase.detail = f"#{action.issue_number} {'OK' if success else 'FAILED'}"

            case "director":
                if dry_run:
                    phase.detail = "skipped (dry run)"
                else:
                    filed = await step_director(model=model, director_interval=DEFAULT_DIRECTOR_INTERVAL)
                    telemetry.director_ran = True
                    telemetry.director_issues_filed = len(filed)
                    phase.detail = f"filed {len(filed)} issues"

            case "strategic_director":
                if dry_run:
                    phase.detail = "skipped (dry run)"
                else:
                    filed = await step_strategic_director(
                        model=model, strategic_interval=DEFAULT_STRATEGIC_DIRECTOR_INTERVAL,
                    )
                    telemetry.strategic_director_ran = True
                    telemetry.strategic_director_issues_filed = len(filed)
                    phase.detail = f"filed {len(filed)} issues"

            case "research_scout":
                if dry_run:
                    phase.detail = "skipped (dry run)"
                else:
                    filed = await step_research_scout(model=model)
                    telemetry.research_scout_ran = True
                    telemetry.research_scout_issues_filed = len(filed)
                    phase.detail = f"filed {len(filed)} issues"

            case "post_pending_tweets":
                posted = post_tweet_backlog(DATA_DIR)
                if posted > 0 and telemetry is not None:
                    telemetry.tweet_posted = True
                phase.detail = f"posted {posted} tweets"

            case "cooldown":
                seconds = action.seconds or 30
                print(f"  Conductor cooldown: sleeping {seconds}s...")
                time.sleep(seconds)
                phase.detail = f"slept {seconds}s"

            case "halt":
                phase.detail = "halting"
                phase.duration_seconds = time.monotonic() - t0
                telemetry.phases.append(phase)
                return "halt"

            case "file_issue":
                if action.title and action.description:
                    num = create_director_issue(action.title, action.description)
                    log.info("Conductor filed issue #%d: %s", num, action.title)
                    phase.detail = f"filed #{num}"
                else:
                    log.warning("file_issue requires title and description")
                    phase.detail = "missing title/description"

            case "skip_cycle":
                phase.detail = "skipped"

    except Exception as exc:
        log.exception("Action %s failed", action.action)
        phase.success = False
        phase.detail = str(exc)
        telemetry.errors.append(f"{action.action}: {exc}")
        _log_error(f"dispatch_{action.action}", exc)

    phase.duration_seconds = time.monotonic() - t0
    telemetry.phases.append(phase)
    return None


# ---------------------------------------------------------------------------
# Resilience — Layer 3: error pattern detection (circuit breaker)
# ---------------------------------------------------------------------------


def _check_error_patterns() -> None:
    """Scan recent telemetry for recurring errors and auto-file a stability issue.

    This is a mechanical pattern detector — no LLM call, no cost, instant.
    Max 1 auto-filed issue per invocation. Never crashes the loop.
    """
    try:
        entries = load_telemetry(TELEMETRY_PATH, last_n=ERROR_PATTERN_WINDOW)
        if len(entries) < ERROR_PATTERN_THRESHOLD:
            return

        # Collect all errors across recent cycles, skipping transient SDK errors
        # that are already handled by _run_sdk_with_retry (same logic as circuit breaker).
        pattern_counts: Counter[str] = Counter()
        for entry in entries:
            for err in entry.errors:
                # Extract a stable pattern: first line (exception class + message prefix)
                pattern = err.strip().split("\n")[0][:120]
                if not pattern:
                    continue
                if any(sig in pattern for sig in SDK_TRANSIENT_SIGNATURES):
                    continue
                pattern_counts[pattern] += 1

        # Find patterns that exceed threshold
        for pattern, count in pattern_counts.most_common():
            if count < ERROR_PATTERN_THRESHOLD:
                break

            # Deduplicate: check if an open stability issue already exists
            result = _run_gh([
                "gh", "issue", "list",
                "--state", "open",
                "--search", "stability:",
                "--json", "number,title",
                "--limit", "20",
            ], check=False)
            if result.returncode == 0 and result.stdout.strip():
                existing = json.loads(result.stdout)
                # Check if any existing stability issue covers this pattern
                already_filed = any(
                    pattern[:50] in issue.get("title", "")
                    for issue in existing
                )
                if already_filed:
                    log.debug("Stability issue already exists for: %s", pattern[:50])
                    return

            # File one stability issue
            title = f"stability: {pattern[:70]}"
            cycles_affected = [
                str(e.cycle) for e in entries if any(pattern[:50] in err for err in e.errors)
            ]
            body = (
                f"**Auto-filed by error pattern detector (Layer 3)**\n\n"
                f"Recurring error detected in {count}/{len(entries)} "
                f"of the last {len(entries)} cycles.\n\n"
                f"**Pattern**: `{pattern}`\n\n"
                f"**Affected cycles**: {', '.join(cycles_affected)}\n\n"
                f"**Full errors from most recent occurrence**:\n```\n"
                + "\n---\n".join(
                    err for e in entries for err in e.errors if pattern[:50] in err
                )[:2000]
                + "\n```"
            )
            num = create_director_issue(title, body)
            log.info("Auto-filed stability issue #%d: %s", num, title)
            return  # Max 1 per invocation

    except Exception:
        log.exception("Error pattern check failed (non-fatal)")


def _check_circuit_breaker() -> None:
    """Halt the loop if the last N cycles all failed with the same error.

    Unlike ``_check_error_patterns`` (which files an issue), this is a hard
    stop — the error is likely infrastructure-level and retrying will just
    burn API credits.  Exits with code 2 so operators can distinguish a
    circuit-breaker halt from a normal failure (code 1).

    Never crashes the loop itself (wrapped in try/except).
    """
    try:
        entries = load_telemetry(TELEMETRY_PATH, last_n=CIRCUIT_BREAKER_THRESHOLD)
        if len(entries) < CIRCUIT_BREAKER_THRESHOLD:
            return

        # Every recent cycle must have at least one error
        if not all(entry.errors for entry in entries):
            return

        # Collect the first-line signature from every error in every cycle
        sigs_per_cycle: list[set[str]] = []
        for entry in entries:
            sigs: set[str] = set()
            for err in entry.errors:
                sig = err.strip().split("\n")[0][:120]
                if sig:
                    sigs.add(sig)
            sigs_per_cycle.append(sigs)

        # Find signatures common to ALL cycles
        common = sigs_per_cycle[0]
        for sigs in sigs_per_cycle[1:]:
            common = common & sigs
        if not common:
            return

        # Don't circuit-break on transient SDK/API errors — those resolve
        # on their own and the exponential backoff handles them.
        common = {
            sig for sig in common
            if not any(ts in sig for ts in SDK_TRANSIENT_SIGNATURES)
        }
        if not common:
            log.info(
                "Circuit breaker: all %d common signatures are transient SDK errors, "
                "not tripping (backoff will handle it)",
                len(sigs_per_cycle[0]),
            )
            return

        banner = (
            "\n" + "!" * 60 + "\n"
            "CIRCUIT BREAKER TRIPPED\n"
            f"Last {CIRCUIT_BREAKER_THRESHOLD} cycles all failed with the same error.\n"
            f"Signature: {next(iter(common))}\n"
            "Halting to avoid burning API credits. Fix the root cause and restart.\n"
            + "!" * 60
        )
        log.critical(banner)
        print(banner)
        sys.exit(2)

    except SystemExit:
        raise  # let sys.exit propagate
    except Exception:
        log.exception("Circuit breaker check failed (non-fatal)")


# ---------------------------------------------------------------------------
# Output data commit (telemetry, analysis results, overrides)
# ---------------------------------------------------------------------------


def _commit_output_data() -> None:
    """Commit and push all output/data/ files (telemetry, results, overrides). Non-fatal."""
    data_dir = PROJECT_ROOT / "output" / "data"
    try:
        if not data_dir.exists():
            return
        # Check for any changed or untracked files in output/data/
        diff = _run_gh(
            ["git", "diff", "--name-only", str(data_dir)], check=False,
        )
        untracked = _run_gh(
            ["git", "ls-files", "--others", "--exclude-standard", str(data_dir)],
            check=False,
        )
        has_changes = bool(diff.stdout.strip()) or bool(untracked.stdout.strip())
        if not has_changes:
            return
        _run_gh(["git", "add", str(data_dir)], check=False)
        _run_gh(
            ["git", "commit", "-m", "chore: update output data"],
            check=False,
        )
        # Gate push on CI health: don't push if the last completed run failed,
        # to avoid cascading failures and triggering more broken CI runs.
        if not is_ci_passing():
            log.warning(
                "CI is failing on main — skipping push to avoid cascading failures. "
                "Output data was committed locally but NOT pushed."
            )
            return
        _run_gh(["git", "push"], check=False)
        log.info("Output data committed and pushed")
    except Exception:
        log.exception("Output data commit failed (non-fatal)")



# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def run_one_cycle(
    *,
    cycle: int,
    productive_cycles: int,
    model: str = DEFAULT_MODEL,
    max_pr_rounds: int = DEFAULT_MAX_PR_ROUNDS,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Run a single Conductor-driven main loop cycle.

    Returns (updated productive_cycles, suggested_cooldown_seconds).
    """
    telemetry = CycleTelemetry(
        cycle=cycle,
        dry_run=dry_run,
    )

    ensure_github_resources_exist()
    _check_circuit_breaker()

    print(f"\n{'='*60}")
    print(f"MAIN LOOP CYCLE {cycle}")
    print(f"{'='*60}\n")

    # --- Always run first (mechanical, no LLM) ---
    overrides = process_human_overrides()
    if overrides:
        print(f"  Processed {overrides} human override(s) -> moved to backlog")
    telemetry.human_overrides = overrides

    print("\nCI Health Check: Checking main branch status...")
    try:
        ci_issues_created = check_ci_health()
        if ci_issues_created > 0:
            print(f"  Created {ci_issues_created} CI failure issue(s)")
        else:
            print("  CI on main is healthy (or already tracked)")
    except Exception as exc:
        log.exception("CI health check failed")
        telemetry.errors.append(f"CI health check: {exc}")
        _log_error("ci_health_check", exc)

    # --- Conductor decides ---
    plan = await _run_conductor(
        cycle=cycle,
        productive_cycles=productive_cycles,
        dry_run=dry_run,
        model=model,
    )

    # Record Conductor decision
    telemetry.conductor_reasoning = plan.reasoning
    telemetry.conductor_actions = [a.action for a in plan.actions]
    # Check if we used the default/recovery plan
    if "Default plan" in plan.reasoning or "Recovery agent" in plan.reasoning:
        telemetry.conductor_fallback = True

    # Log the Conductor's decision
    print(f"\nConductor reasoning: {plan.reasoning}")
    print(f"Conductor plan ({len(plan.actions)} actions):")
    for i, action in enumerate(plan.actions, 1):
        detail = f" (issue #{action.issue_number})" if action.issue_number else ""
        print(f"  {i}. {action.action}{detail}: {action.reason}")
    if plan.notes_for_next_cycle:
        print(f"Notes for next cycle: {plan.notes_for_next_cycle}")
    print(f"Suggested cooldown: {plan.suggested_cooldown_seconds}s\n")

    # --- Execute plan ---
    # Cycle-scoped buffer for proposals from step_propose() so the debate
    # phase can consume them even though propose and debate are separate
    # Conductor actions.
    pending_proposals: list[dict[str, Any]] = []
    for action in plan.actions:
        result = await _dispatch_action(
            action,
            telemetry=telemetry,
            model=model,
            max_pr_rounds=max_pr_rounds,
            dry_run=dry_run,
            productive_cycles=productive_cycles,
            pending_proposals=pending_proposals,
        )
        if result == "halt":
            # Finalize telemetry before halting
            telemetry.finished_at = datetime.now(UTC)
            telemetry.duration_seconds = (
                telemetry.finished_at - telemetry.started_at
            ).total_seconds()
            append_telemetry(TELEMETRY_PATH, telemetry)
            banner = (
                "\n" + "!" * 60 + "\n"
                "CONDUCTOR HALTED THE LOOP\n"
                f"Reason: {action.reason}\n"
                + "!" * 60
            )
            print(banner)
            sys.exit(2)

    # Update productive_cycles: count if any pick_and_execute ran
    was_productive = telemetry.picked_issue_number is not None
    if was_productive:
        productive_cycles += 1

    # --- Auto-drain tweet backlog (runs every cycle, non-fatal) ---
    if not dry_run and "post_pending_tweets" not in telemetry.conductor_actions:
        try:
            posted = post_tweet_backlog(DATA_DIR, limit=3)
            if posted > 0:
                telemetry.tweet_posted = True
                print(f"  Auto-posted {posted} tweet(s) from backlog")
        except Exception:
            log.exception("Auto tweet backlog drain failed (non-fatal)")

    # --- Collect and save transparency records ---
    if not dry_run and was_productive:
        try:
            override_records = collect_override_records()
            if override_records:
                save_override_records(override_records)
                print(f"  Collected {len(override_records)} override record(s) for transparency report")
        except Exception:
            log.exception("Override collection failed (non-fatal)")

        try:
            suggestion_records = collect_human_suggestions()
            if suggestion_records:
                save_suggestion_records(suggestion_records)
                count = len(suggestion_records)
                print(f"  Collected {count} human-suggested issue(s) for transparency report")
        except Exception:
            log.exception("Human suggestion collection failed (non-fatal)")

        try:
            pr_merge_records = collect_pr_merges()
            if pr_merge_records:
                save_pr_merge_records(pr_merge_records)
                print(f"  Collected {len(pr_merge_records)} PR merge record(s) for transparency report")
        except Exception:
            log.exception("PR merge collection failed (non-fatal)")

    # --- Finalize telemetry ---
    telemetry.finished_at = datetime.now(UTC)
    telemetry.duration_seconds = (
        telemetry.finished_at - telemetry.started_at
    ).total_seconds()
    telemetry.cycle_yielded = bool(
        telemetry.execution_success or telemetry.tweet_posted
    )
    append_telemetry(TELEMETRY_PATH, telemetry)
    _check_error_patterns()

    # --- Append to Conductor journal ---
    _append_conductor_journal(
        reasoning=plan.reasoning,
        notes=plan.notes_for_next_cycle,
        actions=[a.action for a in plan.actions],
    )

    return productive_cycles, plan.suggested_cooldown_seconds


def _reexec(
    *,
    cycle_offset: int,
    productive_cycles_offset: int,
    max_cycles: int,
    cooldown: int,
    model: str,
    max_pr_rounds: int,
    dry_run: bool,
    verbose: bool,
    fail_streak: int = 0,
) -> None:
    """Re-exec the script to pick up any code changes from disk.

    After each cycle, execution merges PRs back to main. This function
    pulls latest, then replaces the current process with a fresh
    invocation so that any modifications to this script (or pr_workflow,
    or anything else) are picked up automatically.
    """
    _commit_output_data()
    _run_gh(["git", "checkout", "main"], check=False)
    _run_gh(["git", "pull", "--ff-only"], check=False)

    # Sync dependencies in case a merged PR changed pyproject.toml
    log.info("Syncing dependencies before re-exec...")
    subprocess.run(  # noqa: S603
        ["uv", "sync"], cwd=PROJECT_ROOT, check=False,
        capture_output=True, text=True,
    )

    argv: list[str] = [
        sys.executable, str(Path(__file__).resolve()),
        "--_cycle-offset", str(cycle_offset),
        "--_productive-cycles-offset", str(productive_cycles_offset),
    ]
    if max_cycles > 0:
        argv += ["--max-cycles", str(max_cycles)]
    if cooldown != DEFAULT_COOLDOWN_SECONDS:
        argv += ["--cooldown", str(cooldown)]
    if model != DEFAULT_MODEL:
        argv += ["--model", model]
    if max_pr_rounds != DEFAULT_MAX_PR_ROUNDS:
        argv += ["--max-pr-rounds", str(max_pr_rounds)]
    if dry_run:
        argv += ["--dry-run"]
    if verbose:
        argv += ["--verbose"]
    if fail_streak > 0:
        argv += ["--_fail-streak", str(fail_streak)]

    print(f"\n--- Re-execing to pick up latest code (cycle offset {cycle_offset}) ---\n")
    os.execv(sys.executable, argv)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Conductor-driven main loop: Conductor agent decides what to do each cycle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  uv run python scripts/main_loop.py                          # run indefinitely
  uv run python scripts/main_loop.py --dry-run --max-cycles 1 # test Conductor planning only
  uv run python scripts/main_loop.py --max-cycles 3           # 3 cycles then stop
""",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=0,
        help="Maximum cycles to run; 0 = unlimited (default: 0)",
    )
    parser.add_argument(
        "--cooldown", type=int, default=DEFAULT_COOLDOWN_SECONDS,
        help=f"Minimum cooldown seconds between cycles (default: {DEFAULT_COOLDOWN_SECONDS})",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-pr-rounds", type=int, default=DEFAULT_MAX_PR_ROUNDS,
        help=f"Max coder-reviewer rounds per PR; 0 = unlimited (default: {DEFAULT_MAX_PR_ROUNDS})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Conductor plans but pick_and_execute does not actually run tasks",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose (debug) logging",
    )
    # Internal args: track completed cycles across re-execs
    parser.add_argument(
        "--_cycle-offset", type=int, default=0, dest="cycle_offset",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--_productive-cycles-offset", type=int, default=0, dest="productive_cycles_offset",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--_fail-streak", type=int, default=0, dest="fail_streak",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy SDK transport logs
    logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)

    cycle = args.cycle_offset + 1
    productive_cycles = args.productive_cycles_offset

    # Check if we've exceeded max_cycles (across re-execs)
    if args.max_cycles > 0 and cycle > args.max_cycles:
        print(f"Reached max cycles ({args.max_cycles}). Stopping.")
        return

    suggested_cooldown = args.cooldown
    fail_streak = args.fail_streak
    cycle_failed = False

    async def _run() -> tuple[int, int]:
        return await run_one_cycle(
            cycle=cycle,
            productive_cycles=productive_cycles,
            model=args.model,
            max_pr_rounds=args.max_pr_rounds,
            dry_run=args.dry_run,
        )

    try:
        productive_cycles, suggested_cooldown = anyio.run(_run)
    except KeyboardInterrupt:
        print("\nMain loop interrupted.")
        sys.exit(1)
    except Exception as exc:
        # Layer 1: never crash the loop — record the error and move on
        log.exception("Cycle %d crashed at top level", cycle)
        _log_error("main_loop_cycle", exc)
        cycle_failed = True
        try:
            partial = CycleTelemetry(
                cycle=cycle,
                finished_at=datetime.now(UTC),
                errors=[f"Top-level crash: {exc}"],
                dry_run=args.dry_run,
            )
            append_telemetry(TELEMETRY_PATH, partial)
        except Exception:
            log.exception("Failed to write crash telemetry")

    # Check telemetry to detect SDK-down skip cycles (also count as failures
    # for backoff purposes even though they don't throw exceptions)
    if not cycle_failed:
        try:
            last = load_telemetry(TELEMETRY_PATH, last_n=1)
            if last and last[0].conductor_fallback and last[0].errors:
                cycle_failed = True
        except Exception:
            pass

    # Update fail streak: reset on success, increment on failure
    if cycle_failed:
        fail_streak += 1
        log.warning("Cycle %d failed (fail streak: %d)", cycle, fail_streak)
    else:
        if fail_streak > 0:
            log.info("Cycle %d succeeded, resetting fail streak (was %d)", cycle, fail_streak)
        fail_streak = 0

    # Cooldown: use Conductor's suggestion, but enforce minimum from CLI.
    # Apply exponential backoff when cycles keep failing.
    remaining = 0 if args.max_cycles > 0 and cycle >= args.max_cycles else 1
    if remaining:
        cooldown = max(suggested_cooldown, args.cooldown)
        if fail_streak > 0:
            backoff = min(cooldown * (2 ** fail_streak), MAX_BACKOFF_SECONDS)
            print(
                f"\nFail streak {fail_streak}: backing off for {backoff}s "
                f"(base {cooldown}s × 2^{fail_streak}, max {MAX_BACKOFF_SECONDS}s)"
            )
            cooldown = backoff
        else:
            print(f"\nCooling down for {cooldown}s (Conductor suggested {suggested_cooldown}s)...")
        time.sleep(cooldown)

        _reexec(
            cycle_offset=cycle,
            productive_cycles_offset=productive_cycles,
            max_cycles=args.max_cycles,
            cooldown=args.cooldown,
            model=args.model,
            max_pr_rounds=args.max_pr_rounds,
            dry_run=args.dry_run,
            verbose=args.verbose,
            fail_streak=fail_streak,
        )
    else:
        print("\nMain loop finished.")


if __name__ == "__main__":
    main()
