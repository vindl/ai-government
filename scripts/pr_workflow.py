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
REVIEWER_MAX_TURNS = 15

CODER_TOOLS = ["Bash", "Write", "Edit", "Read", "Glob", "Grep"]
REVIEWER_TOOLS = ["Bash", "Read", "Glob", "Grep"]

# Unset CLAUDECODE so spawned SDK subprocesses don't refuse to launch
# (Claude Code detects nested sessions via this env var).
SDK_ENV = {"CLAUDECODE": ""}

log = logging.getLogger("pr_workflow")


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


def get_pr_review_state(pr_number: int) -> str:
    """Get the review decision for a PR.

    Returns 'APPROVED', 'CHANGES_REQUESTED', or '' (empty).
    """
    result = _run_gh(
        ["gh", "pr", "view", str(pr_number), "--json", "reviewDecision", "-q", ".reviewDecision"],
        check=False,
    )
    return result.stdout.strip()


def merge_pr(pr_number: int) -> None:
    """Merge a PR using gh."""
    _run_gh(["gh", "pr", "merge", str(pr_number), "--merge", "--delete-branch"])
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
    return f"""You need to review PR #{pr_number}. Do the following:

1. Read the PR diff: `gh pr diff {pr_number}`
2. Read any files that need more context to understand the changes.
3. Run the project checks yourself:
   - `uv run ruff check src/ tests/`
   - `uv run mypy src/`
   - `uv run pytest`
4. Evaluate the changes against the project conventions in CLAUDE.md.
5. Submit your review:
   - If the code is correct, clean, and follows conventions:
     `gh pr review {pr_number} --approve --body "LGTM - <brief reason>"`
   - If changes are needed:
     `gh pr review {pr_number} --request-changes --body "<detailed feedback>"`

Be thorough but pragmatic. Focus on correctness, type safety, and convention adherence.
Do NOT approve if checks fail.
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
        stream = claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=system_prompt,
                model=model,
                max_turns=CODER_MAX_TURNS,
                allowed_tools=CODER_TOOLS,
                permission_mode="bypassPermissions",
                cwd=PROJECT_ROOT,
                env=SDK_ENV,
            ),
        )
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
        stream = claude_code_sdk.query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                system_prompt=system_prompt,
                model=model,
                max_turns=REVIEWER_MAX_TURNS,
                allowed_tools=REVIEWER_TOOLS,
                permission_mode="bypassPermissions",
                cwd=PROJECT_ROOT,
                env=SDK_ENV,
            ),
        )
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
) -> None:
    """Run the full PR coder-reviewer workflow.

    Loops reviewer → coder until the reviewer approves, then merges.
    If max_rounds > 0, stops after that many rounds and leaves the PR open.
    """
    branch_name = branch or make_branch_name(task)
    rounds_label = "unlimited" if max_rounds == 0 else str(max_rounds)

    # Ensure we're on the right branch
    current = get_current_branch()
    if current != branch_name:
        create_branch(branch_name)

    # --- Round 1: Coder implements and opens PR ---
    print(f"\n{'='*60}")
    print(f"ROUND 1 (max: {rounds_label}): Coder implementing...")
    print(f"{'='*60}\n")

    coder_prompt = _build_coder_prompt_round1(task)
    output, had_error = await run_coder(coder_prompt, model=model, branch=branch_name)

    if had_error:
        print("ERROR: Coder agent failed in round 1. Aborting.")
        sys.exit(1)

    print(f"\nCoder output:\n{output[:500]}{'...' if len(output) > 500 else ''}\n")

    # Find the PR
    pr_number = get_pr_number_for_branch(branch_name)
    if pr_number is None:
        print("ERROR: No PR found after coder round. The coder may have failed to create one.")
        sys.exit(1)

    print(f"PR #{pr_number} created on branch {branch_name}")

    # --- Review loop: reviewer → (merge | coder fix) → repeat ---
    round_num = 1
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

        # Check review state
        state = get_pr_review_state(pr_number)
        print(f"Review state: {state or '(none)'}")

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
""",
    )
    parser.add_argument(
        "task",
        help="Description of the task for the coder to implement",
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
        )

    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        print("\nWorkflow interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
