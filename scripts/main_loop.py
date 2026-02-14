#!/usr/bin/env python3
"""Unified main loop for the AI Government project.

Runs an indefinite cycle with three phases:
  Phase A: Check for new government decisions → create analysis issues
  Phase B: Self-improvement — propose improvements → debate/triage
  Phase C: Pick from unified backlog → execute (routes by task type)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

from ai_government.config import SessionConfig
from ai_government.orchestrator import Orchestrator
from ai_government.output.scorecard import render_scorecard
from ai_government.output.site_builder import load_results_from_dir, save_result_json
from ai_government.output.twitter import (
    compose_daily_tweet,
    get_unposted_results,
    load_state,
    post_tweet,
    save_state,
    should_post,
)
from ai_government.session import load_decisions

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ai_government.models.decision import GovernmentDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_PROPOSALS_PER_CYCLE = 1
DEFAULT_MAX_PR_ROUNDS = 0  # 0 = unlimited

LABEL_PROPOSED = "self-improve:proposed"
LABEL_BACKLOG = "self-improve:backlog"
LABEL_REJECTED = "self-improve:rejected"
LABEL_IN_PROGRESS = "self-improve:in-progress"
LABEL_DONE = "self-improve:done"
LABEL_FAILED = "self-improve:failed"
LABEL_HUMAN = "human-suggestion"
LABEL_TASK_ANALYSIS = "task:analysis"
LABEL_TASK_CODE = "task:code-change"

ALL_LABELS: dict[str, str] = {
    LABEL_PROPOSED: "808080",    # gray
    LABEL_BACKLOG: "0e8a16",     # green
    LABEL_REJECTED: "e67e22",    # orange
    LABEL_IN_PROGRESS: "fbca04",  # yellow
    LABEL_DONE: "6f42c1",       # purple
    LABEL_FAILED: "d73a4a",     # red
    LABEL_HUMAN: "0075ca",      # blue
    LABEL_TASK_ANALYSIS: "1d76db",  # light blue
    LABEL_TASK_CODE: "5319e7",      # violet
}

# GitHub Projects
PROJECT_TITLE = "AI Government Workflow"
FIELD_STATUS = "Status"
FIELD_TASK_TYPE = "Task Type"
FIELD_DOMAIN = "Domain"

STATUS_OPTIONS = ["Proposed", "Backlog", "In Progress", "Done", "Failed", "Rejected"]
TASK_TYPE_OPTIONS = ["Code Change", "Analysis"]
DOMAIN_OPTIONS = ["Dev", "Government", "Human", "N/A"]


# Unset CLAUDECODE so spawned SDK subprocesses don't refuse to launch.
# Also clear ANTHROPIC_API_KEY so the subprocess uses OAuth.
SDK_ENV = {"CLAUDECODE": "", "ANTHROPIC_API_KEY": ""}

PROPOSE_MAX_TURNS = 10
DEBATE_MAX_TURNS = 5
PROPOSE_TOOLS = ["Bash", "Read", "Glob", "Grep"]

PRIVILEGED_PERMISSIONS = {"admin", "maintain"}

SEED_DECISIONS_PATH = PROJECT_ROOT / "data" / "seed" / "sample_decisions.json"

log = logging.getLogger("main_loop")

_repo_nwo: str | None = None

# GitHub Projects cache (populated once per cycle by _init_project)
_project_number: int | None = None
_project_id: str | None = None
_field_ids: dict[str, str] = {}
_field_option_ids: dict[str, dict[str, str]] = {}


# ---------------------------------------------------------------------------
# SDK helpers
# ---------------------------------------------------------------------------


def _sdk_options(
    *,
    system_prompt: str,
    model: str,
    max_turns: int,
    allowed_tools: list[str],
) -> ClaudeCodeOptions:
    return ClaudeCodeOptions(
        system_prompt=system_prompt,
        model=model,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        cwd=PROJECT_ROOT,
        env=SDK_ENV,
    )


async def _collect_agent_output(
    stream: AsyncIterator[claude_code_sdk.Message],
) -> str:
    text_parts: list[str] = []
    async for message in stream:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "\n".join(text_parts)


# ---------------------------------------------------------------------------
# Git / GitHub helpers
# ---------------------------------------------------------------------------


def _run_gh(
    args: list[str], *, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log.debug("Running: %s", " ".join(args))
    result = subprocess.run(  # noqa: S603
        args, capture_output=True, text=True, cwd=PROJECT_ROOT, check=False,
    )
    if check and result.returncode != 0:
        log.error("Command failed: %s\nstderr: %s", " ".join(args), result.stderr.strip())
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result


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


def _ensure_labels() -> None:
    """Create all labels idempotently."""
    for label, color in ALL_LABELS.items():
        _run_gh(
            ["gh", "label", "create", label, "--color", color, "--force"],
            check=False,
        )
    log.info("Labels ensured")


# ---------------------------------------------------------------------------
# GitHub Projects helpers
# ---------------------------------------------------------------------------


def _get_owner() -> str:
    """Return the repo owner (org or user) from the cached NWO."""
    return _get_repo_nwo().split("/")[0]


def ensure_project_exists() -> int:
    """Find or create the GitHub Project. Returns project number."""
    global _project_number  # noqa: PLW0603
    if _project_number is not None:
        return _project_number

    owner = _get_owner()
    result = _run_gh([
        "gh", "project", "list",
        "--owner", owner,
        "--format", "json",
    ], check=False)

    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            projects = data.get("projects", data) if isinstance(data, dict) else data
            for proj in projects:
                if proj.get("title") == PROJECT_TITLE:
                    _project_number = proj["number"]
                    log.info("Found existing project #%d: %s", _project_number, PROJECT_TITLE)
                    break
        except (json.JSONDecodeError, KeyError):
            pass

    if _project_number is None:
        result = _run_gh([
            "gh", "project", "create",
            "--owner", owner,
            "--title", PROJECT_TITLE,
            "--format", "json",
        ])
        data = json.loads(result.stdout)
        _project_number = data["number"]
        log.info("Created project #%d: %s", _project_number, PROJECT_TITLE)

    # Link project to repo
    _run_gh([
        "gh", "project", "link", str(_project_number),
        "--owner", owner,
        "--repo", _get_repo_nwo(),
    ], check=False)

    return _project_number


def ensure_project_fields() -> None:
    """Create custom fields on the project if they don't exist."""
    global _field_ids, _field_option_ids  # noqa: PLW0603
    owner = _get_owner()
    num = ensure_project_exists()

    result = _run_gh([
        "gh", "project", "field-list", str(num),
        "--owner", owner,
        "--format", "json",
    ], check=False)

    existing_fields: dict[str, dict[str, Any]] = {}
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            fields = data.get("fields", data) if isinstance(data, dict) else data
            for f in fields:
                existing_fields[f["name"]] = f
        except (json.JSONDecodeError, KeyError):
            pass

    desired: dict[str, list[str]] = {
        FIELD_STATUS: STATUS_OPTIONS,
        FIELD_TASK_TYPE: TASK_TYPE_OPTIONS,
        FIELD_DOMAIN: DOMAIN_OPTIONS,
    }

    for field_name, options in desired.items():
        if field_name in existing_fields:
            fld = existing_fields[field_name]
            _field_ids[field_name] = fld["id"]
            opt_map: dict[str, str] = {}
            for opt in fld.get("options", []):
                opt_map[opt["name"]] = opt["id"]
            _field_option_ids[field_name] = opt_map
        else:
            cr = _run_gh([
                "gh", "project", "field-create", str(num),
                "--owner", owner,
                "--name", field_name,
                "--data-type", "SINGLE_SELECT",
                "--single-select-options", ",".join(options),
                "--format", "json",
            ], check=False)
            if cr.returncode != 0:
                log.warning("Failed to create field %s: %s", field_name, cr.stderr.strip())
                continue
            # Re-fetch fields to get IDs for the newly created field
            refetch = _run_gh([
                "gh", "project", "field-list", str(num),
                "--owner", owner,
                "--format", "json",
            ], check=False)
            if refetch.returncode == 0 and refetch.stdout.strip():
                try:
                    rdata = json.loads(refetch.stdout)
                    rfields = rdata.get("fields", rdata) if isinstance(rdata, dict) else rdata
                    for rf in rfields:
                        if rf["name"] == field_name:
                            _field_ids[field_name] = rf["id"]
                            opt_map = {}
                            for opt in rf.get("options", []):
                                opt_map[opt["name"]] = opt["id"]
                            _field_option_ids[field_name] = opt_map
                            break
                except (json.JSONDecodeError, KeyError):
                    pass

    log.info("Project fields ensured: %s", list(_field_ids.keys()))


def _init_project() -> None:
    """Initialize project cache. Called once per cycle."""
    global _project_id  # noqa: PLW0603
    ensure_project_exists()
    ensure_project_fields()

    owner = _get_owner()
    num = ensure_project_exists()
    result = _run_gh([
        "gh", "project", "view", str(num),
        "--owner", owner,
        "--format", "json",
    ], check=False)
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            _project_id = data.get("id")
        except (json.JSONDecodeError, KeyError):
            pass

    log.info("Project initialized: number=%s id=%s", _project_number, _project_id)


def _add_to_project(
    issue_number: int,
    *,
    status: str,
    task_type: str,
    domain: str = "N/A",
) -> None:
    """Add an issue to the project board and set its fields."""
    if _project_number is None or _project_id is None:
        return

    owner = _get_owner()
    nwo = _get_repo_nwo()
    issue_url = f"https://github.com/{nwo}/issues/{issue_number}"

    # Add item to project
    result = _run_gh([
        "gh", "project", "item-add", str(_project_number),
        "--owner", owner,
        "--url", issue_url,
        "--format", "json",
    ], check=False)
    if result.returncode != 0:
        log.warning("Failed to add #%d to project: %s", issue_number, result.stderr.strip())
        return

    try:
        item_data = json.loads(result.stdout)
        item_id = item_data.get("id")
    except (json.JSONDecodeError, KeyError):
        log.warning("Could not parse item ID after adding #%d to project", issue_number)
        return

    if not item_id:
        return

    # Set field values
    field_values = {
        FIELD_STATUS: status,
        FIELD_TASK_TYPE: task_type,
        FIELD_DOMAIN: domain,
    }

    for field_name, value in field_values.items():
        field_id = _field_ids.get(field_name)
        option_id = _field_option_ids.get(field_name, {}).get(value)
        if not field_id or not option_id:
            log.debug("Skipping field %s=%s (missing IDs)", field_name, value)
            continue
        _run_gh([
            "gh", "project", "item-edit",
            "--project-id", _project_id,
            "--id", item_id,
            "--field-id", field_id,
            "--single-select-option-id", option_id,
        ], check=False)

    log.debug("Added #%d to project: status=%s type=%s domain=%s", issue_number, status, task_type, domain)


def _update_project_status(issue_number: int, status: str) -> None:
    """Update the Status field of an issue already in the project."""
    if _project_number is None or _project_id is None:
        return

    owner = _get_owner()
    nwo = _get_repo_nwo()
    issue_url = f"https://github.com/{nwo}/issues/{issue_number}"

    # Find the item in the project
    result = _run_gh([
        "gh", "project", "item-list", str(_project_number),
        "--owner", owner,
        "--limit", "1000",
        "--format", "json",
    ], check=False)
    if result.returncode != 0:
        log.debug("Could not list project items: %s", result.stderr.strip())
        return

    item_id: str | None = None
    try:
        data = json.loads(result.stdout)
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items:
            content = item.get("content", {})
            if content.get("url") == issue_url or content.get("number") == issue_number:
                item_id = item.get("id")
                break
    except (json.JSONDecodeError, KeyError):
        pass

    if not item_id:
        log.debug("Issue #%d not found in project, skipping status update", issue_number)
        return

    field_id = _field_ids.get(FIELD_STATUS)
    option_id = _field_option_ids.get(FIELD_STATUS, {}).get(status)
    if not field_id or not option_id:
        log.debug("Missing field/option IDs for status=%s", status)
        return

    _run_gh([
        "gh", "project", "item-edit",
        "--project-id", _project_id,
        "--id", item_id,
        "--field-id", field_id,
        "--single-select-option-id", option_id,
    ], check=False)

    log.debug("Updated #%d project status to %s", issue_number, status)


def ensure_github_resources_exist() -> None:
    """Create labels and initialize the GitHub Project."""
    _ensure_labels()
    try:
        _init_project()
    except Exception:
        log.exception("GitHub Projects initialization failed (non-fatal)")


def create_proposal_issue(title: str, body: str, *, domain: str = "N/A") -> int:
    """Create a GitHub Issue with the proposed label. Returns issue number."""
    ai_body = f"Written by PM agent:\n\n{body}"
    result = _run_gh([
        "gh", "issue", "create",
        "--title", title,
        "--body", ai_body,
        "--label", LABEL_PROPOSED,
    ])
    # gh issue create prints the URL; extract number from it
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    _add_to_project(issue_number, status="Proposed", task_type="Code Change", domain=domain)
    return issue_number


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
    _run_gh(["gh", "issue", "comment", str(issue_number), "--body", body])


def accept_issue(issue_number: int) -> None:
    """Move issue from proposed to backlog."""
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_PROPOSED,
             "--add-label", LABEL_BACKLOG])
    _update_project_status(issue_number, "Backlog")


def reject_issue(issue_number: int) -> None:
    """Label as rejected and close."""
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_PROPOSED,
             "--add-label", LABEL_REJECTED])
    _run_gh(["gh", "issue", "close", str(issue_number),
             "--comment", "Written by Triage agent: Rejected by triage debate. See debate above."])
    _update_project_status(issue_number, "Rejected")


def list_backlog_issues() -> list[dict[str, Any]]:
    """Return backlog issues, oldest first."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_BACKLOG,
        "--state", "open",
        "--json", "number,title,body,labels,createdAt",
        "--limit", "50",
    ])
    issues: list[dict[str, Any]] = json.loads(result.stdout) if result.stdout.strip() else []
    issues.sort(key=lambda i: i.get("createdAt", ""))
    return issues


def list_human_suggestions() -> list[dict[str, Any]]:
    """Return human-suggestion issues pending triage."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_HUMAN,
        "--state", "open",
        "--json", "number,title,body,createdAt",
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
        _run_gh(["gh", "issue", "comment", str(n),
                 "--body",
                 f"Written by Triage agent: Issue reopened by @{actor_login} — "
                 "moved to backlog via human override."])
        _update_project_status(n, "Backlog")
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
            _run_gh(["gh", "issue", "comment", str(n),
                     "--body",
                     f"Written by Triage agent: HUMAN OVERRIDE by @{override_user} — "
                     "moved to backlog."])
            _update_project_status(n, "Backlog")
            log.info(
                "Human override (comment): #%d %s (by %s)",
                n, issue["title"], override_user,
            )
            count += 1

    return count


def mark_issue_in_progress(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_BACKLOG,
             "--add-label", LABEL_IN_PROGRESS])
    _update_project_status(issue_number, "In Progress")


def mark_issue_done(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_DONE])
    _run_gh(["gh", "issue", "close", str(issue_number)])
    _update_project_status(issue_number, "Done")


def mark_issue_failed(issue_number: int, reason: str) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_FAILED])
    _run_gh(["gh", "issue", "comment", str(issue_number),
             "--body", f"Written by Executor agent: Execution failed: {reason}"])
    _update_project_status(issue_number, "Failed")


def get_failed_issue_titles() -> list[str]:
    """Return titles of previously failed issues (for dedup)."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_FAILED,
        "--state", "all",
        "--json", "title",
        "--limit", "100",
    ])
    issues = json.loads(result.stdout) if result.stdout.strip() else []
    return [i["title"] for i in issues]


# ---------------------------------------------------------------------------
# Role prompt loading
# ---------------------------------------------------------------------------


def _load_role_prompt(role: str) -> str:
    path = PROJECT_ROOT / "dev-fleet" / role / "CLAUDE.md"
    if path.exists():
        return path.read_text()
    log.warning("Role prompt not found: %s", path)
    return ""


# ---------------------------------------------------------------------------
# Phase A: Government decision analysis
# ---------------------------------------------------------------------------


def get_pending_decisions() -> list[GovernmentDecision]:
    """Load decisions that need analysis.

    Currently reads from seed data. This is the future integration point
    for scrapers (gov.me, news sites).
    """
    if not SEED_DECISIONS_PATH.exists():
        log.warning("No seed decisions file: %s", SEED_DECISIONS_PATH)
        return []
    return load_decisions(SEED_DECISIONS_PATH)


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
    """Create a GitHub Issue for analyzing a government decision."""
    title = f"Analyze: {decision.title[:60]}"
    body = (
        f"**Decision ID**: {decision.id}\n"
        f"**Date**: {decision.date}\n"
        f"**Category**: {decision.category}\n\n"
        f"> {decision.summary}\n\n"
        f"Run full AI cabinet analysis on this decision."
    )
    result = _run_gh([
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--label", f"{LABEL_BACKLOG},{LABEL_TASK_ANALYSIS}",
    ])
    url = result.stdout.strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    _add_to_project(issue_number, status="Backlog", task_type="Analysis", domain="Government")
    return issue_number


def step_check_decisions() -> int:
    """Check for new government decisions and create analysis issues.

    Returns the number of new issues created.
    """
    decisions = get_pending_decisions()
    if not decisions:
        log.info("No pending decisions found")
        return 0

    created = 0
    for decision in decisions:
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

    # Extract decision ID from issue body
    match = re.search(r"\*\*Decision ID\*\*:\s*(\S+)", body)
    if not match:
        reason = "Could not parse decision ID from issue body"
        mark_issue_failed(issue_number, reason)
        log.error("Issue #%d: %s", issue_number, reason)
        return False

    decision_id = match.group(1)

    # Load the matching decision from seed data
    all_decisions = get_pending_decisions()
    decision = next((d for d in all_decisions if d.id == decision_id), None)
    if decision is None:
        reason = f"Decision {decision_id} not found in seed data"
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

        # Post scorecard as issue comment
        scorecard = render_scorecard(results[0])
        _run_gh(["gh", "issue", "comment", str(issue_number),
                 "--body", f"## AI Cabinet Scorecard\n\n{scorecard}"])

        # Serialize result to JSON for the static site builder
        data_dir = Path(__file__).resolve().parent.parent / "output" / "data"
        saved = save_result_json(results[0], data_dir)
        log.info("Saved result JSON to %s", saved)

        mark_issue_done(issue_number)
        log.info("Analysis issue #%d completed successfully", issue_number)
        return True
    except Exception as exc:
        reason = f"Analysis failed: {exc}"
        mark_issue_failed(issue_number, reason)
        log.exception("Issue #%d failed", issue_number)
        return False


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
    failed_titles = get_failed_issue_titles()
    failed_block = ""
    if failed_titles:
        titles_list = "\n".join(f"- {t}" for t in failed_titles)
        failed_block = (
            f"\n\nPreviously failed proposals (DO NOT re-propose these):\n{titles_list}"
        )

    prompt = f"""You are the PM for the AI Government project. Propose exactly {num_proposals} improvements.

Read these files for context:
- docs/STATUS.md
- docs/ROADMAP.md
- docs/CONTEXT.md
- Browse src/ and scripts/ to understand current implementation

Also check existing GitHub Issues to avoid duplicates:
- Run: gh issue list --state all --limit 50

Propose improvements across TWO domains:

1. **Dev fleet & workflow**: tooling, CI, testing, code quality, developer experience
2. **Government simulation**: new ministry agents, more realistic decision models,
   real-world data ingestion (gov.me scraper, news), matching structure to actual
   Montenegrin government bodies, improving prompt quality, EU accession tracking,
   Montenegrin language accuracy

Consider:
- How can we make the government mirror more realistic?
- What real-world data sources should we ingest?
- Should the ministry structure match the actual government or propose a better one?
- How can we improve based on feedback from previous outputs?
{failed_block}

Return ONLY a JSON array (no markdown fences) of exactly {num_proposals} objects:
[
  {{
    "title": "Short imperative title (under 80 chars)",
    "description": "2-3 sentences explaining the improvement, why it matters, and acceptance criteria",
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
    )

    log.info("Running PM agent to propose %d improvements...", num_proposals)
    stream = claude_code_sdk.query(prompt=prompt, options=opts)
    output = await _collect_agent_output(stream)

    # Extract JSON from the output
    proposals = _parse_json_array(output)
    if not proposals:
        log.warning("PM agent returned no parseable proposals")
        return []

    log.info("PM proposed %d improvements", len(proposals))
    return proposals[:num_proposals]


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
    )
    stream = claude_code_sdk.query(prompt=prompt, options=opts)
    return await _collect_agent_output(stream)


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
    )
    stream = claude_code_sdk.query(prompt=prompt, options=opts)
    return await _collect_agent_output(stream)


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
    )
    stream = claude_code_sdk.query(prompt=prompt, options=opts)
    return await _collect_agent_output(stream)


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
    )
    stream = claude_code_sdk.query(prompt=prompt, options=opts)
    return await _collect_agent_output(stream)


# ---------------------------------------------------------------------------
# Step 3: Pick
# ---------------------------------------------------------------------------


def _issue_has_label(issue: dict[str, Any], label: str) -> bool:
    """Check if an issue has a specific label."""
    labels = issue.get("labels", [])
    return any(lbl.get("name") == label for lbl in labels)


def step_pick() -> dict[str, Any] | None:
    """Pick the next backlog issue. Analysis tasks get priority, then FIFO."""
    issues = list_backlog_issues()
    if not issues:
        log.info("No backlog issues to pick")
        return None

    # Prefer analysis tasks over code changes
    for issue in issues:
        if _issue_has_label(issue, LABEL_TASK_ANALYSIS):
            log.info("Picked analysis issue #%d: %s", issue["number"], issue["title"])
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
) -> bool:
    """Route execution by task type. Returns True on success."""
    if _issue_has_label(issue, LABEL_TASK_ANALYSIS):
        return await step_execute_analysis(issue, model=model, dry_run=dry_run)
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
    from pr_workflow import run_workflow

    # Make sure we're on main and up to date
    _run_gh(["git", "checkout", "main"])
    _run_gh(["git", "pull", "--ff-only"], check=False)

    try:
        await run_workflow(task, max_rounds=max_pr_rounds, model=model)
        mark_issue_done(issue_number)
        log.info("Issue #%d completed successfully", issue_number)
        return True
    except SystemExit as e:
        reason = f"PR workflow exited with code {e.code}"
        mark_issue_failed(issue_number, reason)
        log.error("Issue #%d failed: %s", issue_number, reason)
        return False
    except Exception as exc:
        reason = f"Unexpected error: {exc}"
        mark_issue_failed(issue_number, reason)
        log.exception("Issue #%d failed", issue_number)
        return False
    finally:
        # Always return to main branch
        _run_gh(["git", "checkout", "main"], check=False)


# ---------------------------------------------------------------------------
# X daily digest
# ---------------------------------------------------------------------------


DATA_DIR = PROJECT_ROOT / "output" / "data"


def step_post_tweet() -> bool:
    """Post a daily digest to X if enough time has elapsed.

    Returns True if a post was published, False otherwise.
    Non-fatal: returns False on any error (missing creds, API failure, etc.).
    """
    state = load_state()

    if not should_post(state):
        log.debug("X post cooldown has not elapsed — skipping")
        return False

    if not DATA_DIR.exists():
        log.debug("No data directory — skipping X post")
        return False

    results = load_results_from_dir(DATA_DIR)
    unposted = get_unposted_results(results, state)

    if not unposted:
        log.debug("No unposted results — skipping X post")
        return False

    text = compose_daily_tweet(unposted)
    if not text:
        return False

    log.info("Composed X post:\n%s", text)

    tweet_id = post_tweet(text)
    if tweet_id is None:
        # Content was logged above — useful for dev when creds aren't set
        return False

    # Update state
    from datetime import UTC, datetime

    state.last_posted_at = datetime.now(UTC)
    state.posted_decision_ids.extend(r.decision.id for r in unposted[:3])
    save_state(state)
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def run_one_cycle(
    *,
    cycle: int,
    proposals_per_cycle: int = DEFAULT_PROPOSALS_PER_CYCLE,
    model: str = DEFAULT_MODEL,
    max_pr_rounds: int = DEFAULT_MAX_PR_ROUNDS,
    dry_run: bool = False,
    skip_analysis: bool = False,
    skip_improve: bool = False,
) -> None:
    """Run a single main loop cycle with three phases."""
    ensure_github_resources_exist()

    print(f"\n{'='*60}")
    print(f"MAIN LOOP CYCLE {cycle}")
    print(f"{'='*60}\n")

    # --- Step 0: Process human overrides ---
    overrides = process_human_overrides()
    if overrides:
        print(f"  Processed {overrides} human override(s) -> moved to backlog")

    # --- Phase A: Check for new government decisions ---
    if skip_analysis:
        print("Phase A: Skipped (--skip-analysis)")
    else:
        print("Phase A: Checking for new government decisions...")
        try:
            new_issues = step_check_decisions()
            print(f"  Created {new_issues} new analysis issue(s)")
        except Exception:
            log.exception("Phase A (decision check) failed")

    # --- Phase B: Self-improvement (propose + debate) ---
    if skip_improve:
        print("\nPhase B: Skipped (--skip-improve)")
    else:
        # Check if backlog is empty — only propose new work when backlog is drained
        backlog = list_backlog_issues()
        if backlog:
            print(f"\nPhase B: Skipped (backlog has {len(backlog)} open issues — draining queue)")
        else:
            print("\nPhase B: Self-improvement — proposing and debating...")
            try:
                ai_proposals = await step_propose(
                    num_proposals=proposals_per_cycle, model=model,
                )
            except Exception:
                log.exception("Propose step failed")
                ai_proposals = []

            # Ingest human suggestions
            human_issues = list_human_suggestions()
            human_proposals = [
                {
                    "title": h["title"],
                    "description": h.get("body", ""),
                    "domain": "human",
                    "issue_number": h["number"],
                }
                for h in human_issues
            ]

            all_proposals: list[dict[str, Any]] = ai_proposals + human_proposals
            print(f"  {len(ai_proposals)} AI proposals + {len(human_proposals)} human suggestions")

            if all_proposals:
                print("  Debating proposals...")
                try:
                    accepted, rejected = await step_debate(all_proposals, model=model)
                except Exception:
                    log.exception("Debate step failed")
                    accepted, rejected = [], []
                print(f"  Accepted: {len(accepted)}, Rejected: {len(rejected)}")
            else:
                print("  No proposals this cycle.")

    # --- Phase C: Pick from unified backlog and execute ---
    print("\nPhase C: Picking next task from backlog...")
    issue = step_pick()
    if issue is None:
        print("  Backlog empty.")
        return

    task_type = "analysis" if _issue_has_label(issue, LABEL_TASK_ANALYSIS) else "code-change"
    print(f"  Picked [{task_type}]: #{issue['number']} — {issue['title']}")

    print(f"\n  Executing issue #{issue['number']}...")
    success = await step_execute(
        issue, model=model, max_pr_rounds=max_pr_rounds, dry_run=dry_run,
    )
    print(f"  Result: {'SUCCESS' if success else 'FAILED'}")

    # --- Post daily X digest (if due) ---
    if not dry_run:
        try:
            posted = step_post_tweet()
            if posted:
                print("  Posted daily X digest")
        except Exception:
            log.exception("X posting failed (non-fatal)")


def _reexec(
    *,
    cycle_offset: int,
    max_cycles: int,
    cooldown: int,
    proposals: int,
    model: str,
    max_pr_rounds: int,
    dry_run: bool,
    skip_analysis: bool,
    skip_improve: bool,
    verbose: bool,
) -> None:
    """Re-exec the script to pick up any code changes from disk.

    After each cycle, execution merges PRs back to main. This function
    pulls latest, then replaces the current process with a fresh
    invocation so that any modifications to this script (or pr_workflow,
    or anything else) are picked up automatically.
    """
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
    ]
    if max_cycles > 0:
        argv += ["--max-cycles", str(max_cycles)]
    if cooldown != DEFAULT_COOLDOWN_SECONDS:
        argv += ["--cooldown", str(cooldown)]
    if proposals != DEFAULT_PROPOSALS_PER_CYCLE:
        argv += ["--proposals", str(proposals)]
    if model != DEFAULT_MODEL:
        argv += ["--model", model]
    if max_pr_rounds != DEFAULT_MAX_PR_ROUNDS:
        argv += ["--max-pr-rounds", str(max_pr_rounds)]
    if dry_run:
        argv += ["--dry-run"]
    if skip_analysis:
        argv += ["--skip-analysis"]
    if skip_improve:
        argv += ["--skip-improve"]
    if verbose:
        argv += ["--verbose"]

    print(f"\n--- Re-execing to pick up latest code (cycle offset {cycle_offset}) ---\n")
    os.execv(sys.executable, argv)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified main loop: analyze government decisions + self-improve.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  uv run python scripts/main_loop.py                          # run indefinitely
  uv run python scripts/main_loop.py --dry-run --max-cycles 1 # test ideation + triage only
  uv run python scripts/main_loop.py --max-cycles 3           # 3 cycles then stop
  uv run python scripts/main_loop.py --skip-improve           # analysis only
  uv run python scripts/main_loop.py --skip-analysis          # self-improvement only
""",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=0,
        help="Maximum cycles to run; 0 = unlimited (default: 0)",
    )
    parser.add_argument(
        "--cooldown", type=int, default=DEFAULT_COOLDOWN_SECONDS,
        help=f"Seconds between cycles (default: {DEFAULT_COOLDOWN_SECONDS})",
    )
    parser.add_argument(
        "--proposals", type=int, default=DEFAULT_PROPOSALS_PER_CYCLE,
        help=f"AI proposals per cycle (default: {DEFAULT_PROPOSALS_PER_CYCLE})",
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
        help="Propose and debate only; skip execution",
    )
    parser.add_argument(
        "--skip-analysis", action="store_true",
        help="Skip Phase A (government decision checking)",
    )
    parser.add_argument(
        "--skip-improve", action="store_true",
        help="Skip Phase B (self-improvement proposals + debate)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose (debug) logging",
    )
    # Internal arg: tracks completed cycles across re-execs
    parser.add_argument(
        "--_cycle-offset", type=int, default=0, dest="cycle_offset",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cycle = args.cycle_offset + 1

    # Check if we've exceeded max_cycles (across re-execs)
    if args.max_cycles > 0 and cycle > args.max_cycles:
        print(f"Reached max cycles ({args.max_cycles}). Stopping.")
        return

    async def _run() -> None:
        await run_one_cycle(
            cycle=cycle,
            proposals_per_cycle=args.proposals,
            model=args.model,
            max_pr_rounds=args.max_pr_rounds,
            dry_run=args.dry_run,
            skip_analysis=args.skip_analysis,
            skip_improve=args.skip_improve,
        )

    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        print("\nMain loop interrupted.")
        sys.exit(1)

    # Cooldown before next cycle
    remaining = 0 if args.max_cycles > 0 and cycle >= args.max_cycles else 1
    if remaining:
        print(f"\nCooling down for {args.cooldown}s...")
        time.sleep(args.cooldown)

        # Re-exec: pull latest code from main and restart the process.
        # This means if this script was modified during the cycle,
        # the next cycle runs the new version.
        _reexec(
            cycle_offset=cycle,
            max_cycles=args.max_cycles,
            cooldown=args.cooldown,
            proposals=args.proposals,
            model=args.model,
            max_pr_rounds=args.max_pr_rounds,
            dry_run=args.dry_run,
            skip_analysis=args.skip_analysis,
            skip_improve=args.skip_improve,
            verbose=args.verbose,
        )
    else:
        print("\nMain loop finished.")


if __name__ == "__main__":
    main()
