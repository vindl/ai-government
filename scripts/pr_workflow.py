#!/usr/bin/env python3
"""PR-based coder-reviewer workflow.

Automates the dev loop: coder implements on a branch, files a PR,
reviewer reviews, and the loop continues until approval or max rounds.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import claude_code_sdk
from claude_code_sdk import AssistantMessage, ClaudeCodeOptions, TextBlock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_ROUNDS = 0  # 0 = unlimited, loop until approved

CODER_MAX_TURNS = 30
REVIEWER_MAX_TURNS = 10

CODER_TOOLS = ["Bash", "Write", "Edit", "Read", "Glob", "Grep"]
REVIEWER_TOOLS = ["Bash", "Read", "Glob", "Grep"]

# Unset CLAUDECODE so spawned SDK subprocesses don't refuse to launch
# (Claude Code detects nested sessions via this env var).
# Also clear ANTHROPIC_API_KEY so the subprocess uses OAuth (Max plan)
# instead of an invalid or parent-session API key.
SDK_ENV = {"CLAUDECODE": "", "ANTHROPIC_API_KEY": ""}

# Verdict markers used by the reviewer agent in PR comments.
# The workflow parses the latest comment for these instead of using
# GitHub's reviewDecision (which blocks self-reviews).
VERDICT_APPROVED = "VERDICT: APPROVED"
VERDICT_CHANGES_REQUESTED = "VERDICT: CHANGES_REQUESTED"

log = logging.getLogger("pr_workflow")


def _sdk_options(
    *,
    system_prompt: str,
    model: str,
    max_turns: int,
    allowed_tools: list[str],
) -> ClaudeCodeOptions:
    """Build ClaudeCodeOptions with shared defaults."""
    return ClaudeCodeOptions(
        system_prompt=system_prompt,
        model=model,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        cwd=PROJECT_ROOT,
        env=SDK_ENV,
    )


# ---------------------------------------------------------------------------
# Git / GitHub helpers
# ---------------------------------------------------------------------------


def _run_gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a gh/git CLI command and return the result."""
    log.debug("Running: %s", " ".join(args))
    result = subprocess.run(  # noqa: S603
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if check and result.returncode != 0:
        log.error("Command failed: %s\nstderr: %s", " ".join(args), result.stderr.strip())
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result


def make_branch_name(task: str) -> str:
    """Generate a branch name from a task description."""
    slug = task.lower()[:40]
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)
    slug = slug.strip("-")
    short_id = uuid.uuid4().hex[:8]
    return f"ai-dev/{slug}-{short_id}"


def create_branch(name: str) -> None:
    """Create and checkout a new git branch."""
    _run_gh(["git", "checkout", "-b", name])
    log.info("Created branch: %s", name)


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = _run_gh(["git", "branch", "--show-current"])
    return result.stdout.strip()


def get_pr_number_for_branch(branch: str) -> int | None:
    """Get the PR number for a branch, or None if no PR exists."""
    result = _run_gh(
        ["gh", "pr", "view", branch, "--json", "number", "-q", ".number"],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def get_review_verdict_from_comments(pr_number: int) -> str:
    """Parse the latest PR comment for a structured verdict.

    The reviewer agent posts comments containing 'VERDICT: APPROVED' or
    'VERDICT: CHANGES_REQUESTED'. We scan comments in reverse order and
    return the first verdict found.

    Returns 'APPROVED', 'CHANGES_REQUESTED', or '' (empty).
    """
    import json as _json

    result = _run_gh(
        ["gh", "pr", "view", str(pr_number), "--json", "comments", "-q", ".comments"],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""

    try:
        comments = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        log.warning("Failed to parse PR comments JSON")
        return ""

    # Scan newest comments first
    for comment in reversed(comments):
        body = comment.get("body", "")
        if VERDICT_APPROVED in body:
            return "APPROVED"
        if VERDICT_CHANGES_REQUESTED in body:
            return "CHANGES_REQUESTED"

    return ""


def merge_pr(pr_number: int) -> None:
    """Merge a PR using gh.

    Uses --admin to bypass branch protection rules (required for automated
    merges when the repo has status checks or review requirements).
    """
    _run_gh(["gh", "pr", "merge", str(pr_number), "--merge", "--delete-branch", "--admin"])
    log.info("Merged PR #%d", pr_number)


# ---------------------------------------------------------------------------
# Role prompt loading
# ---------------------------------------------------------------------------


def _load_role_prompt(role: str) -> str:
    """Load a dev-fleet role prompt from disk."""
    path = PROJECT_ROOT / "dev-fleet" / role / "CLAUDE.md"
    if path.exists():
        return path.read_text()
    log.warning("Role prompt not found: %s", path)
    return ""


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------


def _build_coder_prompt_round1(task: str) -> str:
    """Build the coder prompt for the first round (implement + open PR)."""
    return f"""You have a task to implement. Do the following steps:

1. Implement the task described below.
2. Run checks to make sure everything passes:
   - `uv run ruff check src/ tests/`
   - `uv run mypy src/`
   - `uv run pytest`
3. Fix any issues found by the checks.
4. Stage and commit your changes with a concise commit message.
5. Push the branch to the remote: `git push -u origin HEAD`
6. Create a PR with `gh pr create --fill` (use a descriptive title and body).

Task: {task}
"""


def _build_coder_prompt_followup(task: str, pr_number: int) -> str:
    """Build the coder prompt for subsequent rounds (address review feedback)."""
    return f"""You previously opened PR #{pr_number} for the following task:

Task: {task}

The reviewer has requested changes. Do the following:

1. Read the review comments: `gh pr view {pr_number} --comments`
2. Also check inline review comments: `gh api repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments`
3. Address each piece of feedback by modifying the code.
4. Run checks to make sure everything passes:
   - `uv run ruff check src/ tests/`
   - `uv run mypy src/`
   - `uv run pytest`
5. Fix any issues found by the checks.
6. Stage and commit your changes with a concise message referencing the feedback.
7. Push: `git push`
"""


def _build_reviewer_prompt(pr_number: int) -> str:
    """Build the reviewer prompt."""
    return f"""Review PR #{pr_number} and post your verdict as a PR comment.

YOUR #1 PRIORITY: You MUST end by running `gh pr comment` with your verdict.
Nothing else matters if you don't post the comment. Do NOT use `gh pr review`.

Steps:
1. `gh pr diff {pr_number}` — read the diff.
2. Read any files needed for context (keep it brief, don't read everything).
3. Run checks: `uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest`
4. Post your verdict comment — this is the MOST IMPORTANT step:

   If approved:
   `gh pr comment {pr_number} --body "VERDICT: APPROVED — <one-line reason>"`

   If changes needed:
   `gh pr comment {pr_number} --body "VERDICT: CHANGES_REQUESTED — <specific feedback>"`

The comment body MUST start with exactly VERDICT: APPROVED or VERDICT: CHANGES_REQUESTED.
Do NOT approve if checks fail. Be pragmatic — focus on correctness, not style nitpicks.
"""


async def _collect_agent_output(stream: AsyncIterator[claude_code_sdk.Message]) -> str:
    """Collect text output from a Claude Code SDK query stream."""
    text_parts: list[str] = []
    async for message in stream:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "\n".join(text_parts)


async def run_coder(
    prompt: str,
    *,
    model: str,
    branch: str,
) -> tuple[str, bool]:
    """Run the coder agent. Returns (output_text, had_error)."""
    log.info("Running coder agent on branch %s...", branch)
    system_prompt = _load_role_prompt("coder")

    try:
        opts = _sdk_options(
            system_prompt=system_prompt,
            model=model,
            max_turns=CODER_MAX_TURNS,
            allowed_tools=CODER_TOOLS,
        )
        stream = claude_code_sdk.query(prompt=prompt, options=opts)
        output = await _collect_agent_output(stream)
        log.info("Coder finished. Output length: %d chars", len(output))
        return output, False
    except Exception:
        log.exception("Coder agent failed")
        return "", True


async def run_reviewer(
    pr_number: int,
    *,
    model: str,
) -> tuple[str, bool]:
    """Run the reviewer agent. Returns (output_text, had_error)."""
    log.info("Running reviewer agent on PR #%d...", pr_number)
    system_prompt = _load_role_prompt("reviewer")
    prompt = _build_reviewer_prompt(pr_number)

    try:
        opts = _sdk_options(
            system_prompt=system_prompt,
            model=model,
            max_turns=REVIEWER_MAX_TURNS,
            allowed_tools=REVIEWER_TOOLS,
        )
        stream = claude_code_sdk.query(prompt=prompt, options=opts)
        output = await _collect_agent_output(stream)
        log.info("Reviewer finished. Output length: %d chars", len(output))
        return output, False
    except Exception:
        log.exception("Reviewer agent failed")
        return "", True


# ---------------------------------------------------------------------------
# Main workflow loop
# ---------------------------------------------------------------------------


async def run_workflow(
    task: str,
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    model: str = DEFAULT_MODEL,
    branch: str | None = None,
    pr: int | None = None,
) -> None:
    """Run the full PR coder-reviewer workflow.

    Loops reviewer → coder until the reviewer approves, then merges.
    If max_rounds > 0, stops after that many rounds and leaves the PR open.
    If pr is given, skips coder round 1 and reviews the existing PR.
    """
    rounds_label = "unlimited" if max_rounds == 0 else str(max_rounds)

    if pr is not None:
        # --- Existing PR: skip coder round 1, go straight to review loop ---
        pr_number = pr
        branch_name = branch or get_current_branch()
        print(f"Reviewing existing PR #{pr_number} on branch {branch_name}")
    else:
        # --- New task: coder implements and opens PR ---
        branch_name = branch or make_branch_name(task)

        current = get_current_branch()
        if current != branch_name:
            create_branch(branch_name)

        print(f"\n{'='*60}")
        print(f"ROUND 1 (max: {rounds_label}): Coder implementing...")
        print(f"{'='*60}\n")

        coder_prompt = _build_coder_prompt_round1(task)
        output, had_error = await run_coder(coder_prompt, model=model, branch=branch_name)

        if had_error:
            print("ERROR: Coder agent failed in round 1. Aborting.")
            sys.exit(1)

        print(f"\nCoder output:\n{output[:500]}{'...' if len(output) > 500 else ''}\n")

        pr_number_result = get_pr_number_for_branch(branch_name)
        if pr_number_result is None:
            print("ERROR: No PR found after coder round. The coder may have failed to create one.")
            sys.exit(1)

        pr_number = pr_number_result
        print(f"PR #{pr_number} created on branch {branch_name}")

    # --- Review loop: reviewer → (merge | coder fix) → repeat ---
    round_num = 0
    while True:
        round_num += 1

        # Check safety cap
        if max_rounds > 0 and round_num > max_rounds:
            print(f"\nReached max rounds ({max_rounds}). PR #{pr_number} remains open.")
            sys.exit(1)

        # Reviewer reviews
        print(f"\n{'='*60}")
        print(f"ROUND {round_num} (max: {rounds_label}): Reviewer reviewing PR #{pr_number}...")
        print(f"{'='*60}\n")

        reviewer_output, had_error = await run_reviewer(pr_number, model=model)

        if had_error:
            print(f"ERROR: Reviewer agent failed in round {round_num}. Aborting.")
            sys.exit(1)

        print(f"\nReviewer output:\n{reviewer_output[:500]}{'...' if len(reviewer_output) > 500 else ''}\n")

        # Check review verdict from PR comments
        state = get_review_verdict_from_comments(pr_number)
        print(f"Review verdict: {state or '(none)'}")

        if state == "APPROVED":
            print(f"\nPR #{pr_number} approved! Merging...")
            merge_pr(pr_number)
            print(f"Done! PR merged after {round_num} rounds.")
            return

        if state != "CHANGES_REQUESTED":
            print(f"Unexpected review state: {state!r}. Treating as changes requested.")

        # Coder addresses feedback
        print(f"\n{'='*60}")
        print(f"ROUND {round_num} (max: {rounds_label}): Coder addressing feedback...")
        print(f"{'='*60}\n")

        coder_prompt = _build_coder_prompt_followup(task, pr_number)
        output, had_error = await run_coder(coder_prompt, model=model, branch=branch_name)

        if had_error:
            print(f"ERROR: Coder agent failed in round {round_num}. Aborting.")
            sys.exit(1)

        print(f"\nCoder output:\n{output[:500]}{'...' if len(output) > 500 else ''}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint for the PR workflow."""
    parser = argparse.ArgumentParser(
        description="Run a PR-based coder-reviewer workflow using Claude Code SDK agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  uv run python scripts/pr_workflow.py "Implement the gov.me scraper MCP server"
  uv run python scripts/pr_workflow.py "Add retry logic" --max-rounds 5  # safety cap
  uv run python scripts/pr_workflow.py "Fix bug" --model claude-opus-4-6 -v
  uv run python scripts/pr_workflow.py "Refactor" --branch ai-dev/my-branch
  uv run python scripts/pr_workflow.py --pr 2 "Review constitution PR"  # existing PR
""",
    )
    parser.add_argument(
        "task",
        help="Description of the task (used in coder prompts for context)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="Review an existing PR by number (skips coder round 1)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        help=f"Maximum coder-reviewer rounds; 0 = unlimited (default: {DEFAULT_MAX_ROUNDS})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Use a specific branch name instead of auto-generating one",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    async def _run() -> None:
        await run_workflow(
            args.task,
            max_rounds=args.max_rounds,
            model=args.model,
            branch=args.branch,
            pr=args.pr,
        )

    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        print("\nWorkflow interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
