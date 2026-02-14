# Project Status

*Last updated: 2026-02-14*

## Current Phase: Scaffold Complete (v0.1.0)

The full repository scaffold is in place. All code passes linting, type checking, and tests. The pipeline is wired end-to-end but has not been run against the real Claude API yet.

## What Is Done

### Core Infrastructure
- [x] Git repo initialized, pushed to https://github.com/vindl/ai-government
- [x] `pyproject.toml` with all dependencies (claude-code-sdk, pydantic, anyio, httpx, bs4)
- [x] Dev dependencies: ruff, mypy, pytest, pytest-asyncio
- [x] `.python-version` (3.12), `.gitignore`, `.env.example`
- [x] `CLAUDE.md` project conventions (applies to all Claude Code instances)
- [x] `uv sync` installs everything cleanly

### Data Models (`src/ai_government/models/`)
- [x] `GovernmentDecision` — Pydantic model for input decisions
- [x] `Assessment` — ministry agent output with verdict + score
- [x] `Verdict` — StrEnum (strongly_positive → strongly_negative)
- [x] `ParliamentDebate` — synthesized debate output
- [x] `CriticReport` — independent auditor output

### Agent Framework (`src/ai_government/agents/`)
- [x] `GovernmentAgent` base class with `analyze()` method
- [x] `MinistryConfig` frozen dataclass for per-ministry config
- [x] Response parsing with JSON extraction + graceful fallback
- [x] 5 ministry agents: Finance, Justice, EU Integration, Health, Interior
- [x] `ParliamentAgent` — receives all assessments, synthesizes debate
- [x] `CriticAgent` — independent scoring of decision + assessments

### Prompts (`src/ai_government/prompts/`)
- [x] `ministry_base.py` — shared template with `build_ministry_prompt()`
- [x] Per-ministry prompts with Montenegro-specific expertise
- [x] Parliament prompt — neutral moderator persona
- [x] Critic prompt — independent watchdog persona
- [x] All prompts request JSON output, Montenegrin language (Latin script)

### Orchestrator (`src/ai_government/orchestrator.py`)
- [x] Parallel ministry dispatch via `anyio.create_task_group()`
- [x] Sequential mode option for debugging/budget control
- [x] Phase 1: ministries in parallel → Phase 2: parliament + critic in parallel
- [x] `SessionResult` dataclass aggregating all outputs

### Session Runner (`src/ai_government/session.py`)
- [x] CLI entrypoint with argparse
- [x] Loads decisions from JSON file
- [x] Runs orchestrator, saves scorecards to output dir
- [x] Flags: `--decision-file`, `--output-dir`, `--sequential`, `--model`

### Output Formatters (`src/ai_government/output/`)
- [x] `scorecard.py` — full markdown scorecard with tables, scores, details
- [x] `social_media.py` — Twitter/X thread formatter (280-char limit)
- [x] `html.py` — Jinja2-based HTML scorecard renderer
- [x] `site_builder.py` — full static site builder (index, scorecards, about, feed)

### Static Site (`site/`)
- [x] Jinja2 templates: base, scorecard, index, about, feed
- [x] Minimal responsive CSS (no frameworks)
- [x] Montenegrin nav labels and site chrome
- [x] About page renders `docs/CONSTITUTION.md`
- [x] Feed page reads markdown announcements from `site/content/announcements/`
- [x] `scripts/build_site.py` CLI — reads `output/data/*.json`, outputs `_site/`
- [x] GitHub Actions deploy workflow (push to main triggers build + deploy to GitHub Pages)
- [x] CI includes site build verification step
- [x] Main loop serializes analysis results to `output/data/` for site builder

### Dev Fleet (`dev-fleet/`)
- [x] 6 role prompts: coder, reviewer, tester, pm, devops, publisher
- [x] `scripts/launch_dev_member.sh` — launches Claude Code with role prompt
- [x] `scripts/pr_workflow.py` — automated PR-based coder-reviewer loop
  - Coder agent implements on a branch, runs checks, opens a PR
  - Reviewer agent reviews the diff, runs checks, approves or requests changes
  - Loop iterates until approval (auto-merge) or max rounds reached
  - Each agent gets fresh context per round (no session continuity)
  - Configurable: `--max-rounds`, `--model`, `--branch`, `-v`
- [x] `scripts/main_loop.py` — unified main loop (analysis + self-improvement)
  - Three-phase cycle:
    - Phase A: Check for new government decisions → create analysis issues
    - Phase B: Self-improvement — propose → debate → backlog
    - Phase C: Pick from unified backlog → execute (routes by task type)
  - `task:analysis` issues run the orchestrator pipeline (ministries + parliament + critic)
  - `task:code-change` issues run pr_workflow (coder-reviewer loop)
  - Analysis tasks get execution priority over code changes
  - PM agent proposes improvements across dev and government domains
  - Two-agent debate (PM advocate vs Reviewer skeptic) with deterministic judge
  - All proposals, debates, and verdicts tracked as GitHub Issues with labels
  - Human suggestions supported via `human-suggestion` label
  - Failed tasks tracked and excluded from re-proposal
  - Configurable: `--max-cycles`, `--cooldown`, `--proposals`, `--dry-run`
  - Phase skipping: `--skip-analysis`, `--skip-improve`

### Docker Support
- [x] `Dockerfile` — Python 3.12-slim with Node.js 20, gh CLI, uv, Claude Code CLI
- [x] `docker-compose.yml` — service config with resource limits, restart policy, logging
- [x] `scripts/docker-entrypoint.sh` — validates env, clones repo, installs deps, runs loop
- [x] `.dockerignore` — excludes .venv, .git, .env, .claude, output, caches
- [x] Fresh clone at runtime (no host filesystem mount) for full isolation
- [x] `uv sync` in `_reexec()` so new dependencies are installed after git pull

### X Daily Digest (`src/ai_government/output/twitter.py`)
- [x] `TwitterState` Pydantic model for tracking last post time and posted decision IDs
- [x] `load_state()` / `save_state()` — persists to `output/twitter_state.json`
- [x] `should_post()` — 24h cooldown between posts
- [x] `get_unposted_results()` — filters already-posted decisions
- [x] `compose_daily_tweet()` — template-based, picks up to 3 most concerning results, Montenegrin, 280 chars
- [x] `post_tweet()` — posts via tweepy (X API v2, OAuth 1.0a), gracefully skips if creds not set
- [x] `step_post_tweet()` in main loop — runs after each cycle, non-fatal, logs composed post content
- [x] Docker env var passthrough for `TWITTER_*` credentials

### Tests
- [x] 16 tests passing
- [x] `tests/models/test_decision.py` — model creation, validation, JSON roundtrip, seed data loading
- [x] `tests/agents/test_base.py` — config, prompt building, response parsing (valid/invalid/surrounded), factory functions
- [x] `tests/conftest.py` — shared fixtures with realistic Montenegrin data

### CI/CD
- [x] `.github/workflows/ci.yml` — ruff + mypy + pytest + site build verification on push/PR
- [x] `.github/workflows/daily-session.yml` — scheduled daily run + manual trigger
- [x] `.github/workflows/deploy-site.yml` — GitHub Pages deployment on push to main

### Docs
- [x] `README.md` — project overview and quick start
- [x] `docs/CONTEXT.md` — background, goals, agent roles
- [x] `docs/DECISIONS.md` — architectural decision records
- [x] `docs/STATUS.md` — this file

## What Is a Stub / Placeholder

These files exist but have no real implementation yet:

- `src/ai_government/mcp_servers/gov_me_scraper.py` — TODO comment only, no scraping code
- `src/ai_government/mcp_servers/news_scraper.py` — TODO comment only, no scraping code

## What Has NOT Been Tested

- **No real API calls have been made.** All tests mock or avoid the Claude Code SDK. The full pipeline has not been run against the Anthropic API.
- **No real government decisions have been processed.** Seed data is realistic but manually written.
- **Prompt quality is untested.** Prompts have not been evaluated for output quality, JSON compliance, or Montenegrin language accuracy.

## Known Issues / Gotchas Discovered During Implementation

1. **Pydantic field name `date` shadows the `date` type.** Fixed by using `datetime.date` instead of `from datetime import date` in `decision.py`. If you add new models with date fields, use `datetime.date`.

2. **Claude Code SDK API is `claude_code_sdk.query()` (module-level function), not a class.** The plan referenced `claude-agent-sdk` which doesn't exist. The actual package is `claude-code-sdk` with:
   - `claude_code_sdk.query(prompt=..., options=ClaudeCodeOptions(...))` → async iterator
   - Options: `ClaudeCodeOptions(system_prompt=..., model=..., max_turns=...)`
   - Messages: check `isinstance(message, AssistantMessage)` then iterate `message.content` for `TextBlock`

3. **Ruff's TCH (type-checking) rules aggressively move imports to `TYPE_CHECKING` blocks.** This is fine with `from __future__ import annotations` but be aware that runtime-needed imports (e.g., for dataclass defaults) must stay as regular imports. The orchestrator's `SessionResult` dataclass was affected — ruff moved its type imports but `from __future__ import annotations` makes this safe.

4. **Line length set to 110** (not default 88) because prompt strings and Montenegrin text tend to be long. Prompt files (`src/ai_government/prompts/*.py`) have E501 disabled entirely.

5. **Claude Code SDK nested session guard.** When running `claude_code_sdk.query()` from inside a Claude Code session (e.g., the PR workflow script launched by an agent), the child process inherits `CLAUDECODE=1` and refuses to start. Fix: pass `env={"CLAUDECODE": ""}` in `ClaudeCodeOptions` to clear the nesting guard. This is safe — each SDK call spawns an independent subprocess.
