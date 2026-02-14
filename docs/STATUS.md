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
- [x] `Assessment` — ministry agent output with verdict + score + optional counter-proposal
- [x] `Verdict` — StrEnum (strongly_positive → strongly_negative)
- [x] `ParliamentDebate` — synthesized debate output
- [x] `CriticReport` — independent auditor output
- [x] `MinistryCounterProposal` — per-ministry alternative proposal
- [x] `CounterProposal` — unified counter-proposal from synthesizer

### Agent Framework (`src/ai_government/agents/`)
- [x] `GovernmentAgent` base class with `analyze()` method
- [x] `MinistryConfig` frozen dataclass for per-ministry config
- [x] Response parsing with JSON extraction + graceful fallback
- [x] 5 ministry agents: Finance, Justice, EU Integration, Health, Interior
- [x] `ParliamentAgent` — receives all assessments, synthesizes debate
- [x] `CriticAgent` — independent scoring of decision + assessments
- [x] `SynthesizerAgent` — consolidates ministry counter-proposals into unified alternative

### Prompts (`src/ai_government/prompts/`)
- [x] `ministry_base.py` — shared template with `build_ministry_prompt()`
- [x] Per-ministry prompts with Montenegro-specific expertise
- [x] Parliament prompt — neutral moderator persona
- [x] Critic prompt — independent watchdog persona
- [x] All prompts request JSON output, Montenegrin language (Latin script)

### Orchestrator (`src/ai_government/orchestrator.py`)
- [x] Parallel ministry dispatch via `anyio.create_task_group()`
- [x] Sequential mode option for debugging/budget control
- [x] Phase 1: ministries in parallel → Phase 2: parliament + critic in parallel → Phase 3: synthesizer
- [x] `SessionResult` dataclass aggregating all outputs (including optional `counter_proposal`)

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
- [x] 3 active role prompts: coder, reviewer, pm
- [x] Coder writes both implementation code and unit tests
- [x] Reviewer checks for test coverage and quality
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

### Counter-Proposals
- [x] `MinistryCounterProposal` model — per-ministry alternative proposal (optional on `Assessment`)
- [x] `CounterProposal` model — unified counter-proposal synthesized from all ministry inputs
- [x] Ministry prompts updated to request counter-proposals in JSON response
- [x] `SynthesizerAgent` — consolidates ministry counter-proposals into a unified alternative (+1 API call)
- [x] Orchestrator Phase 3: synthesizer runs after parliament + critic
- [x] `SessionResult.counter_proposal` field (optional, backwards compatible)
- [x] Markdown scorecard renders per-ministry and unified counter-proposals
- [x] HTML scorecard template with counter-proposal sections (ministry inset + unified card)
- [x] CSS styles: `.counter-proposal`, `.counter-proposal-mini`, `.feed-counter-proposal`
- [x] Index page badge "Counter-proposal available" when counter-proposal exists
- [x] Social media thread includes counter-proposal tweet
- [x] X daily digest includes `[+counter-proposal]` indicator

### GitHub Projects Integration
- [x] Single project "AI Government Workflow" auto-created via `gh project create`
- [x] Custom fields: Status (Proposed/Backlog/In Progress/Done/Failed/Rejected), Task Type (Code Change/Analysis), Domain (Dev/Government/Human/N/A)
- [x] Issues added to project on creation (`create_proposal_issue`, `create_analysis_issue`)
- [x] Project Status field synced on every label transition (`accept_issue`, `reject_issue`, `mark_issue_in_progress`, `mark_issue_done`, `mark_issue_failed`, `process_human_overrides`)
- [x] Non-fatal: all project calls use `check=False` and are wrapped so failures don't break the main loop
- [x] Idempotent: project/field creation checks for existing resources before creating
- [x] Cache per cycle: project number, GraphQL ID, field IDs, and option IDs fetched once in `_init_project()`
- **One-time manual steps**:
  - Grant `project` scope: `gh auth refresh -s project`
  - Configure board/table views in GitHub web UI after first run

### Project Director (Phase D) & Telemetry
- [x] `CycleTelemetry` and `CyclePhaseResult` Pydantic models (`src/ai_government/models/telemetry.py`)
- [x] JSONL I/O: `append_telemetry()` and `load_telemetry()` with `last_n` support
- [x] Telemetry persisted to `output/data/telemetry.jsonl` (already not gitignored)
- [x] Every cycle instrumented: phase timing, success/failure, error capture, yield computation
- [x] `dev-fleet/director/CLAUDE.md` role prompt — operational health focus, cycle yield north star
- [x] `step_director()` — invokes Director agent with pre-fetched context, no tool access
- [x] `_prefetch_director_context()` — assembles telemetry, issues, PRs, label distribution
- [x] `create_director_issue()` — files issues with `director-suggestion` + `self-improve:backlog` labels
- [x] 5-tier priority in `step_pick()`: analysis > human > strategy > director > FIFO
- [x] Phase D runs every N cycles (configurable via `--director-interval`, default 5)
- [x] Director hard-capped at 2 issues per review (enforced in code)
- [x] Resilience Layer 1: top-level crash guard in `main()` — records partial telemetry on crash
- [x] Resilience Layer 3: `_check_error_patterns()` — auto-files stability issues for recurring errors
- [x] Telemetry committed and pushed in `_reexec()` before git pull
- [x] `--director-interval` CLI arg + `LOOP_DIRECTOR_INTERVAL` Docker env var
- [x] `strategy-suggestion` label reserved for future Strategic Director (#83)

### Tests
- [x] 38 tests passing
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

### Community Infrastructure
- [x] `CONTRIBUTING.md` — contribution guide for citizens and developers
- [x] `CODE_OF_CONDUCT.md` — references Constitution + Contributor Covenant
- [x] `.github/ISSUE_TEMPLATE/config.yml` — contact links redirecting questions to Discussions
- [x] `.github/ISSUE_TEMPLATE/decision-suggestion.yml` — structured decision submission template
- [x] `.github/ISSUE_TEMPLATE/improvement-suggestion.yml` — project improvement template
- [x] `.github/ISSUE_TEMPLATE/bug-report.yml` — standard bug report template
- [x] GitHub Discussions — 4 categories: Announcements, Decision Suggestions, Methodology, Corrections
- [x] Wiki disabled (duplicates `docs/` and static site)
- [x] Site nav: "Diskusija" link to Discussions tab, proper diacritics on all nav items
- [x] Scorecard: "Prijavite grešku" link to Corrections category
- [x] Index: "Predložite odluku za analizu" CTA linking to Decision Suggestions

### News Scout (Phase A)
- [x] `dev-fleet/news-scout/CLAUDE.md` — role prompt for the News Scout agent
- [x] `step_fetch_news()` in main loop — invokes News Scout agent via Claude Code SDK
- [x] `should_fetch_news()` — once-per-day gate using `output/news_scout_state.json`
- [x] `_generate_decision_id()` — deterministic IDs: `news-{date}-{sha256(title)[:8]}`
- [x] `create_analysis_issue()` embeds full `GovernmentDecision` JSON in issue body
- [x] `step_execute_analysis()` parses embedded JSON (falls back to seed data lookup)
- [x] Max 3 decisions per day (prioritized by public interest)
- [x] Sources: Vijesti, RTCG, Pobjeda, gov.me, CDM, Portal Analitika
- [x] No scraping scripts — News Scout uses `WebSearch` + `WebFetch` tools directly
- [x] Non-fatal: failure logs error and falls back to seed data

## What Is a Stub / Placeholder

No stubs remain. MCP scraper stubs (`gov_me_scraper.py`, `news_scraper.py`) were deleted — news ingestion uses the News Scout agent instead.

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
