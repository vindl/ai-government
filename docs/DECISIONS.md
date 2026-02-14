# Architectural Decisions

## ADR-001: Claude Code SDK over Claude Agent SDK
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The plan originally called for `claude-agent-sdk` but the actual package available is `claude-code-sdk` which wraps Claude Code CLI as subprocesses.

**Decision**: Use `claude-code-sdk` (the Claude Code SDK) for agent orchestration. Each government agent runs as a Claude Code subprocess with a specific system prompt.

**Consequences**: Agents are isolated processes. Communication happens through structured inputs/outputs (JSON). This gives us natural parallelism and fault isolation.

---

## ADR-002: Pydantic v2 for All Data Models
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need structured, validated data flowing between agents.

**Decision**: All inter-agent data uses Pydantic v2 models with strict validation.

**Consequences**: Type safety throughout the pipeline. Easy JSON serialization for agent communication.

---

## ADR-003: Two-Fleet Architecture
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need both runtime AI agents (government simulation) and development tooling.

**Decision**:
- Fleet 1 (Government Mirror): Python agents orchestrated by Claude Code SDK — ministry subagents analyzing decisions
- Fleet 2 (Dev Fleet): Claude Code instances with role-specific `CLAUDE.md` prompts (coder, reviewer, tester, pm, devops)

**Consequences**: Clean separation between the product (government simulation) and the development process. Dev fleet members can work on the codebase with specialized expertise.

---

## ADR-004: anyio for Async Concurrency
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need to run multiple ministry agents in parallel for performance.

**Decision**: Use `anyio` instead of raw `asyncio` for all async operations.

**Consequences**: Backend-agnostic async code. Cleaner task group API for parallel agent dispatch.

---

## ADR-005: Montenegrin Government Focus
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need a specific government to mirror for concrete, testable output.

**Decision**: Focus on Montenegro's government structure with 5 initial ministries: Finance, Justice, EU Integration, Health, Interior.

**Consequences**: Prompts and scrapers are Montenegro-specific. The architecture is general enough to adapt to other governments later.

---

## ADR-006: PR-Based Dev Workflow
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Dev fleet work happened via interactive Claude Code sessions with no automated review loop. Needed a way for coder and reviewer agents to collaborate through structured PR-based iteration.

**Decision**: Build `scripts/pr_workflow.py` — an automated loop where:
- Coder and reviewer agents interact through GitHub PRs, not shared memory
- Each agent invocation is a fresh Claude Code SDK subprocess (no session continuity)
- State lives in GitHub (branch, PR, commits, review comments)
- Reviewer cannot modify code (Write/Edit excluded from its allowed_tools)
- A max rounds cap (default 3) prevents runaway loops

**Consequences**: Work is fully traceable in GitHub history. Reviewer stays honest (read-only). Each round has fresh context, avoiding stale state. The workflow can run unattended but has a safety cap.

---

## ADR-007: Autonomous Self-Improvement Loop
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The PR workflow automates coder-reviewer cycles, but task selection is still manual. We want the project to improve itself autonomously: propose improvements, triage them, and execute them in a continuous loop.

**Decision**: Build `scripts/self_improve.py` — an outer loop around `pr_workflow.py` that:
- **Proposes**: PM agent reads project status and proposes N improvements per cycle (dev + government domains)
- **Debates**: Two-agent dialectic (PM advocate vs Reviewer skeptic) with deterministic judge — no third LLM call for judging
- **Tracks via GitHub Issues**: Every proposal becomes an issue; debates are posted as comments; labels track lifecycle (proposed → backlog → in-progress → done/failed)
- **Human input**: Humans can submit suggestions via `human-suggestion` labeled issues, which get triaged alongside AI proposals
- **Executes**: Imports `run_workflow` directly (no subprocess) with `Closes #N` in the task to auto-link PRs to issues
- **Deduplicates**: Failed task titles are passed to the ideation prompt to prevent re-proposal
- **FIFO picking**: Oldest backlog issue gets executed first; triage already filters quality
- **Configurable safety**: `--max-cycles`, `--cooldown`, `--dry-run`, `--max-pr-rounds`

**Consequences**: The project can run unattended and continuously improve itself. All decisions are publicly traceable on GitHub (issues, comments, PRs). The debate mechanism prevents low-quality proposals from wasting execution time. Human suggestions are first-class citizens in the triage pipeline.

---

## ADR-008: Docker Isolation for Self-Improvement Loop
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The self-improvement loop runs with `bypassPermissions` and executes arbitrary commands via Claude Code SDK subprocesses. Running on the host machine exposes private data (SSH keys, `.netrc`, other repos) to the autonomous loop.

**Decision**: Dockerize the self-improvement loop with these isolation properties:
- Container only sees a fresh git clone (no host filesystem mount)
- Only two host resources exposed: `GH_TOKEN` env var and `~/.claude` mount (for OAuth token refresh)
- `init: true` (tini as PID 1) for proper signal handling with `os.execv`
- Fixed user `aigov` (UID 1000) defined in Dockerfile — no runtime UID override
- Resource limits (4 CPUs, 8GB RAM) prevent runaway consumption
- `on-failure:3` restart policy for crash recovery without infinite loops
- `uv sync` added to `_reexec()` so dependency changes from merged PRs are installed before the next cycle

**Consequences**: The autonomous loop is sandboxed — even with `bypassPermissions`, it cannot access host secrets, other repos, or system configuration. The trade-off is a heavier image (~1GB) due to Node.js and Claude Code CLI dependencies, and slightly slower startup from the fresh clone on each container start.

---

## ADR-010: GitHub Pages Static Site with Jinja2
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project produces AI cabinet analyses but has no public-facing output. The roadmap (Phase 4) calls for web-friendly HTML/static site output.

**Decision**: Build a static site using Jinja2 templates (no SSG framework):
- Templates live in `site/templates/`, static assets in `site/static/`, announcements in `site/content/`
- `SiteBuilder` class assembles scorecards, index, about (renders Constitution), and feed pages
- `scripts/build_site.py` CLI reads serialized results from `output/data/*.json`
- GitHub Actions deploys to GitHub Pages on push to main
- `SessionResult` converted from `@dataclass` to Pydantic `BaseModel` to enable `.model_dump_json()`
- Main loop serializes results to `output/data/` after each analysis
- Site chrome in Montenegrin (nav labels, headings, footer)

**Alternatives considered**:
- SSG frameworks (Hugo, Jekyll, MkDocs) — rejected: adds tooling dependency, site has <100 pages, Jinja2 is already Python-native
- SPA (React/Vue) — rejected: unnecessary complexity for a content site
- Server-rendered — rejected: hosting cost, GitHub Pages is free and fits the use case

**Consequences**: Zero new tooling beyond Jinja2 (already a Python dependency). Full rebuild per deploy (fine for small site). Incremental builds can be added later if needed. The `output/data/` directory is committed to git so the deploy workflow can read it.

---

## ADR-009: Unified Main Loop
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project had two separate entry points: `self_improve.py` (infinite loop for codebase improvement) and `run_session.py` (one-shot government analysis). These needed to be unified so a single Docker container could do both: analyze government decisions AND improve itself.

**Decision**: Rename `self_improve.py` to `main_loop.py` and add a three-phase cycle:
- **Phase A**: Check for new government decisions (from seed data, future: scrapers) and create `task:analysis` issues in the unified backlog
- **Phase B**: Self-improvement — propose improvements, debate, and add accepted proposals to the backlog as before
- **Phase C**: Pick from unified backlog (analysis tasks get priority) and route by task type: `task:analysis` runs the orchestrator pipeline, everything else runs pr_workflow

Analysis tasks skip debate (analyzing real decisions is always the right thing to do). Both phases are independently skippable via `--skip-analysis` and `--skip-improve`. The `get_pending_decisions()` function loads from seed data now and is the integration point for scrapers in Phase 3.

**Consequences**: A single process handles both the product (government analysis) and the meta-process (self-improvement). Docker env vars renamed from `SELF_IMPROVE_*` to `LOOP_*`. The `run_session.py` CLI remains available for one-off analysis outside the loop.

---

## ADR-011: X Daily Digest Over Per-Analysis Threads
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project had a `social_media.py` formatter that produced multi-tweet threads per analysis, but nothing actually posted to X. The goal is automated X posting with minimal noise (1-2 posts/day max).

**Decision**: Post a single daily digest tweet instead of per-analysis threads:
- Template-based composition (no LLM call) — picks up to 3 most concerning results sorted by critic `decision_score` ascending
- 24h cooldown between posts, enforced by a local state file (`output/twitter_state.json`)
- Graceful degradation: if `TWITTER_*` env vars are unset, posting is silently skipped; the main loop never fails because of X
- OAuth 1.0a via tweepy for posting (Bearer Token is app-only/read-only)
- Post content is always logged to console, even when credentials aren't configured

**Alternatives considered**:
- Per-analysis thread posting — rejected: too noisy, user wants max 1-2 posts/day
- LLM-generated tweet text — rejected: adds API cost, latency, and unpredictability for a deterministic formatting task
- Checking X API for last post time — rejected: unnecessary API calls when a local state file suffices

**Consequences**: Predictable, low-noise X presence. The existing `social_media.py` thread formatter remains available for future use (e.g., manual posting, other platforms). Dev environments work without X credentials.
