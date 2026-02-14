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

CODER_MAX_TURNS = 0  # 0 = unlimited; let the coder run until it finishes
REVIEWER_MAX_TURNS = 0  # 0 = unlimited; let the reviewer complete all steps

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


def get_issue_comments(issue_number: int) -> list[dict[str, str]]:
    """Fetch all comments on an issue.

    Returns a list of comment dicts with 'author' and 'body' keys.
    Returns empty list on error.
    """
    import json as _json

    # Get owner/repo for REST API calls
    try:
        owner_repo = _get_owner_repo()
    except ValueError:
        log.warning("Cannot fetch issue comments: unable to determine owner/repo")
        return []

    result = _run_gh(
        ["gh", "api", f"repos/{owner_repo}/issues/{issue_number}/comments"],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        raw_comments = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        log.warning("Failed to parse issue comments JSON")
        return []

    # Normalize to simple dict format
    comments = []
    for c in raw_comments:
        author = c.get("user", {}).get("login", "")
        body = c.get("body", "")
        comments.append({"author": author, "body": body})

    return comments


def get_pr_comments(pr_number: int) -> list[dict[str, str]]:
    """Fetch all comments on a PR.

    Returns a list of comment dicts with 'author' and 'body' keys.
    Returns empty list on error.
    """
    import json as _json

    # Get owner/repo for REST API calls
    try:
        owner_repo = _get_owner_repo()
    except ValueError:
        log.warning("Cannot fetch PR comments: unable to determine owner/repo")
        return []

    result = _run_gh(
        ["gh", "api", f"repos/{owner_repo}/pulls/{pr_number}/comments"],
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        raw_comments = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        log.warning("Failed to parse PR comments JSON")
        return []

    # Also fetch issue comments (PR comments on the conversation tab)
    issue_result = _run_gh(
        ["gh", "api", f"repos/{owner_repo}/issues/{pr_number}/comments"],
        check=False,
    )
    if issue_result.returncode == 0 and issue_result.stdout.strip():
        try:
            issue_comments = _json.loads(issue_result.stdout)
            raw_comments.extend(issue_comments)
        except _json.JSONDecodeError:
            pass

    # Normalize to simple dict format
    comments = []
    for c in raw_comments:
        author = c.get("user", {}).get("login", "")
        body = c.get("body", "")
        comments.append({"author": author, "body": body})

    return comments


def _extract_override_from_comments(comments: list[dict[str, str]], source_type: str, source_id: int) -> str:
    """Extract HUMAN OVERRIDE text from a list of comments.

    Returns the text of the last matching comment (with marker removed),
    or empty string if no override found. Logs a warning if multiple found.

    Args:
        comments: List of comment dicts with 'author' and 'body' keys
        source_type: Type of source (e.g., "PR", "issue") for logging
        source_id: ID of the source for logging
    """
    override_text = ""
    override_author = ""
    override_count = 0

    for comment in comments:
        body = comment.get("body", "")
        if "HUMAN OVERRIDE" in body:
            override_count += 1
            # Remove the marker and save the text
            override_text = body.replace("HUMAN OVERRIDE", "").strip()
            override_author = comment.get("author", "unknown")

    if override_count > 0:
        log.info(
            "Found HUMAN OVERRIDE in %s #%d by %s",
            source_type, source_id, override_author,
        )
        if override_count > 1:
            log.warning(
                "Found %d HUMAN OVERRIDE comments in %s #%d, using the last one",
                override_count, source_type, source_id,
            )

    return override_text


def get_human_override_text(pr_number: int) -> str:
    """Extract HUMAN OVERRIDE text from PR comments, if present.

    Scans all PR comments for 'HUMAN OVERRIDE' markers. Returns the full
    text of the last matching comment (with the marker removed), or empty
    string if no override is found.

    If multiple overrides exist, the last one wins (by comment order).
    Human overrides take absolute priority over all other guidance.
    """
    comments = get_pr_comments(pr_number)
    return _extract_override_from_comments(comments, "PR", pr_number)


def extract_verdict_from_text(text: str) -> str:
    """Extract verdict marker from text (reviewer output).

    Returns 'APPROVED', 'CHANGES_REQUESTED', or '' (empty).
    """
    if VERDICT_APPROVED in text:
        return "APPROVED"
    if VERDICT_CHANGES_REQUESTED in text:
        return "CHANGES_REQUESTED"
    return ""


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
        verdict = extract_verdict_from_text(body)
        if verdict:
            return verdict

    return ""


def merge_pr(pr_number: int) -> None:
    """Merge a PR using gh (squash merge)."""
    _run_gh(["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"])
    log.info("Merged PR #%d", pr_number)


def _get_owner_repo() -> str:
    """Get owner/repo for the current repository.

    Returns the owner/repo string (e.g., "vindl/ai-government").
    Raises ValueError if the repository cannot be determined.
    """
    try:
        result = _run_gh(["gh", "repo", "view", "--json", "owner,name", "-q", ".owner.login + \"/\" + .name"])
        owner_repo = result.stdout.strip()
        if not owner_repo:
            raise ValueError("Could not determine repository owner/repo: empty output from gh")
        return owner_repo
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Could not determine repository owner/repo: {e.stderr}") from e


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


def _build_coder_prompt_round1(task: str, *, issue_number: int | None = None) -> str:
    """Build the coder prompt for the first round (implement + open PR)."""
    # Check for HUMAN OVERRIDE in issue comments
    override_text = ""
    if issue_number is not None:
        comments = get_issue_comments(issue_number)
        override_text = _extract_override_from_comments(comments, "issue", issue_number)

    override_section = ""
    if override_text:
        override_section = f"""
⚠️  **HUMAN OVERRIDE DETECTED** ⚠️
The following instructions from a human take ABSOLUTE PRIORITY over everything else
(including the original task description, AI debate conclusions, and any other guidance):

{override_text}

You MUST follow the HUMAN OVERRIDE instructions above. If they conflict with the
task description below, the HUMAN OVERRIDE wins.
---

"""

    return f"""{override_section}You have a task to implement. Do the following steps:

1. Read the task below and do minimal exploration — just enough to understand the
   code you need to change. Do NOT exhaustively read every related file. The reviewer
   will catch anything you miss, and you can fix it in the next round.
2. Implement the task. Start writing code quickly — don't spend most of your time
   reading and planning.
3. Write unit tests for any new functionality. Follow existing patterns in `tests/`.
   Tests should cover key behaviors, not just happy paths.
4. Run checks to make sure everything passes:
   - `uv run ruff check src/ tests/ scripts/`
   - `uv run mypy src/`
   - `uv run pytest`
5. Fix any issues found by the checks.
6. Stage and commit your changes with a concise commit message.
7. Push the branch to the remote: `git push -u origin HEAD`
8. Create a PR with `gh pr create`. Use a descriptive title. Start the PR body
   with "Written by Coder agent:" followed by a summary of what was implemented.

IMPORTANT: Your primary goal is to produce a working PR. Do not get stuck exploring —
if something is unclear, make a reasonable choice and move on. The reviewer will flag
anything that needs changing.

Task: {task}
"""


def _build_coder_prompt_followup(task: str, pr_number: int, *, issue_number: int | None = None) -> str:
    """Build the coder prompt for subsequent rounds (address review feedback)."""
    # Get owner/repo for inline comment commands (fail fast if unavailable)
    owner_repo = _get_owner_repo()

    # Check for HUMAN OVERRIDE in PR comments
    override_text = get_human_override_text(pr_number)

    # Also check issue comments if we have an issue number
    if not override_text and issue_number is not None:
        comments = get_issue_comments(issue_number)
        override_text = _extract_override_from_comments(comments, "issue", issue_number)

    override_section = ""
    if override_text:
        override_section = f"""
⚠️  **HUMAN OVERRIDE DETECTED** ⚠️
The following instructions from a human take ABSOLUTE PRIORITY over everything else
(including the task description, review feedback, and any other guidance):

{override_text}

You MUST follow the HUMAN OVERRIDE instructions above. If they conflict with the
reviewer's feedback or the task description, the HUMAN OVERRIDE wins.
---

"""

    return f"""{override_section}You previously opened PR #{pr_number} for the following task:

Task: {task}

The reviewer has requested changes. Do the following:

1. Read the review comments: `gh pr view {pr_number} --comments`
2. Also check inline review comments: `gh api repos/{owner_repo}/pulls/{pr_number}/comments`
3. For EACH piece of feedback, reply to the PR comment with your response.
   Start every comment with "Written by Coder agent:".
   For each item either:
   - Acknowledge it's a good point and note you've fixed it
   - Push back if you disagree, explaining why the current approach is correct
   Use: `gh pr comment {pr_number} --body "Written by Coder agent: ..."`
4. Make code changes only for feedback you agree with. Do NOT blindly accept all changes.
5. Run checks to make sure everything passes:
   - `uv run ruff check src/ tests/`
   - `uv run mypy src/`
   - `uv run pytest`
6. Fix any issues found by the checks.
7. Stage and commit your changes with a concise message referencing the feedback.
8. Push: `git push`
"""


def _build_reviewer_prompt(pr_number: int, *, issue_number: int | None = None) -> str:
    """Build the reviewer prompt."""
    # Get owner/repo for inline comment commands (fail fast if unavailable)
    owner_repo = _get_owner_repo()

    # Check for HUMAN OVERRIDE in PR comments
    override_text = get_human_override_text(pr_number)

    # Also check issue comments if we have an issue number
    if not override_text and issue_number is not None:
        comments = get_issue_comments(issue_number)
        override_text = _extract_override_from_comments(comments, "issue", issue_number)

    override_section = ""
    if override_text:
        override_section = f"""
⚠️  **HUMAN OVERRIDE DETECTED** ⚠️
The following instructions from a human take ABSOLUTE PRIORITY over everything else
(including standard review criteria, project conventions, and any other guidance):

{override_text}

You MUST follow the HUMAN OVERRIDE instructions above when conducting your review.
If they conflict with standard review guidelines, the HUMAN OVERRIDE wins.
---

"""

    return f"""{override_section}Review PR #{pr_number} thoroughly. Start every comment with "Written by Reviewer agent:".

Steps:
1. `gh pr diff {pr_number}` — read the full diff carefully.
2. Read surrounding files for context where needed.
3. Run checks: `uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest`
4. **Optionally post inline comments** on specific lines with issues:
   ```
   gh api repos/{owner_repo}/pulls/{pr_number}/comments \\
     -f body="Written by Reviewer agent: ..." \\
     -f commit_id="$(gh pr view {pr_number} --json commits -q '.commits[-1].oid')" \\
     -f path="path/to/file.py" -F line=42 -f side="RIGHT"
   ```
   Use inline comments for genuine bugs, logic errors, or security issues.
5. **Post your verdict** as a PR comment (NOT `gh pr review`):

   `gh pr comment {pr_number} --body "Written by Reviewer agent:\\n\\nVERDICT: ..."`

Verdict rules:
- CHANGES_REQUESTED: only for **blocking issues** — bugs, security problems,
  failing checks, missing tests for new functionality, or correctness errors.
  NOT for style preferences or nice-to-haves.
- APPROVED: when checks pass, new functionality has tests, and there are no
  blocking issues. You may include non-blocking suggestions in an approved review.
- Distinguish clearly between "must fix" (blocking) and "consider improving" (suggestion).
- If checks pass, tests exist for new code, and the code is correct, approve it.
  Don't block on polish.
- The comment body MUST contain exactly VERDICT: APPROVED or VERDICT: CHANGES_REQUESTED.

IMPORTANT — PR comment formatting:
- Do NOT paste raw terminal output (test results, lint output, command logs) into PR comments.
  Instead, summarize: "All checks passed (29 tests, lint clean, types clean)."
- Keep the verdict comment concise and focused on your review findings.
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
    issue_number: int | None = None,
) -> tuple[str, bool]:
    """Run the reviewer agent. Returns (output_text, had_error)."""
    log.info("Running reviewer agent on PR #%d...", pr_number)
    system_prompt = _load_role_prompt("reviewer")
    prompt = _build_reviewer_prompt(pr_number, issue_number=issue_number)

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
    issue: int | None = None,
) -> None:
    """Run the full PR coder-reviewer workflow.

    Loops reviewer → coder until the reviewer approves, then merges.
    If max_rounds > 0, stops after that many rounds and leaves the PR open.
    If pr is given, skips coder round 1 and reviews the existing PR.
    If issue is given, checks for HUMAN OVERRIDE comments in that issue.
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

        coder_prompt = _build_coder_prompt_round1(task, issue_number=issue)
        output, had_error = await run_coder(coder_prompt, model=model, branch=branch_name)

        if had_error:
            log.error("Coder agent raised an exception in round 1. Aborting.")
            sys.exit(1)

        print(f"\nCoder output:\n{output[:500]}{'...' if len(output) > 500 else ''}\n")

        pr_number_result = get_pr_number_for_branch(branch_name)
        if pr_number_result is None:
            log.error(
                "No PR found after coder round 1. Branch: %s\n"
                "Coder output (%d chars):\n%s",
                branch_name, len(output), output,
            )
            sys.exit(1)

        pr_number = pr_number_result
        print(f"PR #{pr_number} created on branch {branch_name}")

    # --- Review loop: reviewer → (merge | coder fix) → repeat ---
    round_num = 0
    consecutive_missing_verdicts = 0
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

        reviewer_output, had_error = await run_reviewer(pr_number, model=model, issue_number=issue)

        if had_error:
            print(f"ERROR: Reviewer agent failed in round {round_num}. Aborting.")
            sys.exit(1)

        print(f"\nReviewer output:\n{reviewer_output[:500]}{'...' if len(reviewer_output) > 500 else ''}\n")

        # Check review verdict from PR comments
        state = get_review_verdict_from_comments(pr_number)
        print(f"Review verdict from comments: {state or '(none)'}")

        # Fallback: if verdict missing from comments, check reviewer output text
        if not state:
            state = extract_verdict_from_text(reviewer_output)
            if state:
                log.warning(
                    "Reviewer composed verdict '%s' but did not post it (likely ran out of turns). "
                    "Using verdict from output text as fallback.",
                    state,
                )
                print(f"Review verdict from output text (fallback): {state}")

        # Track consecutive missing verdicts
        if not state:
            consecutive_missing_verdicts += 1
            log.warning(
                "Review verdict missing for %d consecutive round(s). "
                "Reviewer may have run out of turns.",
                consecutive_missing_verdicts,
            )
        else:
            consecutive_missing_verdicts = 0  # reset counter

        # Break loop if verdict missing for 2+ consecutive rounds
        if consecutive_missing_verdicts >= 2:
            log.error(
                "Verdict missing for %d consecutive rounds. Reviewer unable to complete review. "
                "Treating as approved (no blocking issues found) and merging.",
                consecutive_missing_verdicts,
            )
            print(
                f"\nWARNING: Reviewer failed to post verdict for {consecutive_missing_verdicts} rounds. "
                "Assuming no blocking issues and merging PR."
            )
            merge_pr(pr_number)
            print(f"Done! PR merged after {round_num} rounds (auto-approved due to missing verdicts).")
            return

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

        coder_prompt = _build_coder_prompt_followup(task, pr_number, issue_number=issue)
        output, had_error = await run_coder(coder_prompt, model=model, branch=branch_name)

        if had_error:
            log.error("Coder agent raised an exception in round %d. Aborting.", round_num)
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
        "--issue",
        type=int,
        default=None,
        help="Issue number to check for HUMAN OVERRIDE comments",
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
            issue=args.issue,
        )

    try:
        anyio.run(_run)
    except KeyboardInterrupt:
        print("\nWorkflow interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
