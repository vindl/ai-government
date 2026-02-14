#!/usr/bin/env python3
"""Autonomous self-improvement loop.

Runs an indefinite cycle: propose improvements → debate/triage →
backlog as GitHub Issues → pick a task → execute via PR workflow → repeat.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_PROPOSALS_PER_CYCLE = 3
DEFAULT_MAX_PR_ROUNDS = 0  # 0 = unlimited

LABEL_PROPOSED = "self-improve:proposed"
LABEL_BACKLOG = "self-improve:backlog"
LABEL_REJECTED = "self-improve:rejected"
LABEL_IN_PROGRESS = "self-improve:in-progress"
LABEL_DONE = "self-improve:done"
LABEL_FAILED = "self-improve:failed"
LABEL_HUMAN = "human-suggestion"

ALL_LABELS: dict[str, str] = {
    LABEL_PROPOSED: "808080",    # gray
    LABEL_BACKLOG: "0e8a16",     # green
    LABEL_REJECTED: "e67e22",    # orange
    LABEL_IN_PROGRESS: "fbca04",  # yellow
    LABEL_DONE: "6f42c1",       # purple
    LABEL_FAILED: "d73a4a",     # red
    LABEL_HUMAN: "0075ca",      # blue
}

# Unset CLAUDECODE so spawned SDK subprocesses don't refuse to launch.
# Also clear ANTHROPIC_API_KEY so the subprocess uses OAuth.
SDK_ENV = {"CLAUDECODE": "", "ANTHROPIC_API_KEY": ""}

PROPOSE_MAX_TURNS = 10
DEBATE_MAX_TURNS = 5
PROPOSE_TOOLS = ["Bash", "Read", "Glob", "Grep"]

log = logging.getLogger("self_improve")


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


def ensure_labels_exist() -> None:
    """Create all labels idempotently."""
    for label, color in ALL_LABELS.items():
        _run_gh(
            ["gh", "label", "create", label, "--color", color, "--force"],
            check=False,
        )
    log.info("Labels ensured")


def create_proposal_issue(title: str, body: str) -> int:
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
    return int(url.rstrip("/").split("/")[-1])


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


def reject_issue(issue_number: int) -> None:
    """Label as rejected and close."""
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_PROPOSED,
             "--add-label", LABEL_REJECTED])
    _run_gh(["gh", "issue", "close", str(issue_number),
             "--comment", "Written by Triage agent: Rejected by triage debate. See debate above."])


def list_backlog_issues() -> list[dict[str, Any]]:
    """Return backlog issues, oldest first."""
    result = _run_gh([
        "gh", "issue", "list",
        "--label", LABEL_BACKLOG,
        "--state", "open",
        "--json", "number,title,body,createdAt",
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
        _run_gh(["gh", "issue", "edit", str(n),
                 "--remove-label", LABEL_REJECTED,
                 "--add-label", LABEL_BACKLOG])
        _run_gh(["gh", "issue", "comment", str(n),
                 "--body",
                 "Written by Triage agent: Issue reopened by human — "
                 "moved to backlog via human override."])
        log.info("Human override (reopened): #%d %s", n, issue["title"])
        count += 1

    # Case 2: HUMAN OVERRIDE in comments on any open issue with proposed/rejected label
    for label in (LABEL_PROPOSED, LABEL_REJECTED):
        result = _run_gh([
            "gh", "issue", "list",
            "--label", label,
            "--state", "all",
            "--json", "number,title,comments",
            "--limit", "50",
        ], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        issues = json.loads(result.stdout)
        for issue in issues:
            comments = issue.get("comments", [])
            has_override = any(
                "HUMAN OVERRIDE" in c.get("body", "")
                for c in comments
            )
            if not has_override:
                continue
            n = issue["number"]
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
                     "Written by Triage agent: HUMAN OVERRIDE detected — "
                     "moved to backlog."])
            log.info("Human override (comment): #%d %s", n, issue["title"])
            count += 1

    return count


def mark_issue_in_progress(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_BACKLOG,
             "--add-label", LABEL_IN_PROGRESS])


def mark_issue_done(issue_number: int) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_DONE])
    _run_gh(["gh", "issue", "close", str(issue_number)])


def mark_issue_failed(issue_number: int, reason: str) -> None:
    _run_gh(["gh", "issue", "edit", str(issue_number),
             "--remove-label", LABEL_IN_PROGRESS,
             "--add-label", LABEL_FAILED])
    _run_gh(["gh", "issue", "comment", str(issue_number),
             "--body", f"Written by Executor agent: Execution failed: {reason}"])


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
            issue_number = create_proposal_issue(
                title,
                f"**Domain**: {domain}\n\n{description}",
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


def step_pick() -> dict[str, Any] | None:
    """Pick the oldest backlog issue (FIFO)."""
    issues = list_backlog_issues()
    if not issues:
        log.info("No backlog issues to pick")
        return None
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
    """Execute the picked issue via pr_workflow. Returns True on success."""
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
# Main loop
# ---------------------------------------------------------------------------


async def run_one_cycle(
    *,
    cycle: int,
    proposals_per_cycle: int = DEFAULT_PROPOSALS_PER_CYCLE,
    model: str = DEFAULT_MODEL,
    max_pr_rounds: int = DEFAULT_MAX_PR_ROUNDS,
    dry_run: bool = False,
) -> None:
    """Run a single self-improvement cycle."""
    ensure_labels_exist()

    print(f"\n{'='*60}")
    print(f"SELF-IMPROVEMENT CYCLE {cycle}")
    print(f"{'='*60}\n")

    # --- Step 0: Process human overrides ---
    overrides = process_human_overrides()
    if overrides:
        print(f"  Processed {overrides} human override(s) → moved to backlog")

    # --- Step 1: Propose ---
    print("Step 1: Proposing improvements...")
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

    if not all_proposals:
        print("  No proposals this cycle.")
        return

    # --- Step 2: Debate ---
    print("\nStep 2: Debating proposals...")
    try:
        accepted, rejected = await step_debate(all_proposals, model=model)
    except Exception:
        log.exception("Debate step failed")
        accepted, rejected = [], []
    print(f"  Accepted: {len(accepted)}, Rejected: {len(rejected)}")

    # --- Step 3: Pick ---
    print("\nStep 3: Picking next task from backlog...")
    issue = step_pick()
    if issue is None:
        print("  Backlog empty.")
        return

    print(f"  Picked: #{issue['number']} — {issue['title']}")

    # --- Step 4: Execute ---
    print(f"\nStep 4: Executing issue #{issue['number']}...")
    success = await step_execute(
        issue, model=model, max_pr_rounds=max_pr_rounds, dry_run=dry_run,
    )
    print(f"  Result: {'SUCCESS' if success else 'FAILED'}")


def _reexec(
    *,
    cycle_offset: int,
    max_cycles: int,
    cooldown: int,
    proposals: int,
    model: str,
    max_pr_rounds: int,
    dry_run: bool,
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
    if verbose:
        argv += ["--verbose"]

    print(f"\n--- Re-execing to pick up latest code (cycle offset {cycle_offset}) ---\n")
    os.execv(sys.executable, argv)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous self-improvement loop for the AI Government project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  uv run python scripts/self_improve.py                          # run indefinitely
  uv run python scripts/self_improve.py --dry-run --max-cycles 1 # test ideation + triage only
  uv run python scripts/self_improve.py --max-cycles 3           # 3 cycles then stop
  uv run python scripts/self_improve.py --cooldown 30 --proposals 5
  uv run python scripts/self_improve.py --max-cycles 1 --max-pr-rounds 3
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
        )

    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        print("\nSelf-improvement loop interrupted.")
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
            verbose=args.verbose,
        )
    else:
        print("\nSelf-improvement loop finished.")


if __name__ == "__main__":
    main()
