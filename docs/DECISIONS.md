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
- Fleet 2 (Dev Fleet): Claude Code instances with role-specific `CLAUDE.md` prompts (coder, reviewer, pm)

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

**Decision**: Focus on Montenegro as the target government with 5 initial analytical domains: Finance, Justice, EU Integration, Health, Interior. These represent policy analysis areas, not a replication of Montenegro's 25-ministry organizational structure. The project mirrors government *function* (analyzing decisions across all policy domains), not its *org chart*.

**Consequences**: Prompts and decision sources are Montenegro-specific. The architecture is general enough to adapt to other governments later. Future domain expansion should prioritize analytical coverage and consolidation over matching the bloated structure of Montenegro's actual government.

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

---

## ADR-012: Layered Counter-Proposal Architecture
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The AI Government critiques and scores government decisions but never proposes alternatives. To act as a true parallel governing body, it should say "here's what we would do instead."

**Decision**: Use a layered approach:
1. Each ministry produces a domain-specific counter-proposal as part of its existing analysis (same API call, no extra cost — just more output tokens)
2. A new `SynthesizerAgent` consolidates ministry counter-proposals into one unified counter-proposal (+1 API call per decision)

Pipeline changes from 7 → 8 API calls:
```
Before: Decision → 5 ministries (parallel) → parliament + critic (parallel) → output
After:  Decision → 5 ministries w/ counter-proposals (parallel) → parliament + critic (parallel) → synthesizer → output
```

All new model fields are optional (`None` default) for backwards compatibility with existing serialized data.

**Alternatives considered**:
- Single synthesizer without per-ministry proposals — rejected: loses domain-specific expertise, and ministries already have the context during analysis
- Parallel synthesizer with Phase 2 — rejected: keeping it sequential (Phase 3) leaves the door open to feed parliament/critic results into the synthesizer later
- Separate API call per ministry for counter-proposals — rejected: wasteful when the same context is already in the ministry analysis call

**Consequences**: ~14% cost increase (8 vs 7 API calls). Per-ministry counter-proposals are essentially free (same call, ~15-20% more output tokens). The unified counter-proposal gives the project its identity as a parallel governing body, not just a critic.

---

## ADR-013: GitHub Projects as View Layer
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The main loop tracks issue workflow state via GitHub labels (`self-improve:proposed` → `backlog` → `in-progress` → `done/failed/rejected`). This works reliably for agents but provides no visual overview for humans. A kanban board would let maintainers see the pipeline at a glance.

**Decision**: Add GitHub Projects integration as a **view layer** on top of the existing label system:
- Single project ("AI Government Workflow") with a Status field mirroring label states, plus Task Type and Domain metadata fields
- Labels remain the source of truth — agents read/write labels, project fields are updated as a side effect
- All project API calls are non-fatal (`check=False`, wrapped in try/except) so failures never break the main loop
- Project setup (create project, create fields, cache IDs) runs once per cycle in `ensure_github_resources_exist()`
- Code-driven via `gh project` CLI commands — no GitHub Automations dependency

**Alternatives considered**:
- GitHub Automations (built-in project automations) — rejected: limited to label-to-status mapping, no custom field control, opaque to debugging
- Separate tracking tool (Linear, Jira) — rejected: adds external dependency, GitHub Issues already used by agents
- Labels-only (status quo) — rejected: works for agents but poor human visibility

**Consequences**: Humans get a kanban board and table view without changing agent behavior. The `project` OAuth scope must be granted to the token (`gh auth refresh -s project`). Board/table views are configured manually in the GitHub web UI (one-time setup). Slightly more API calls per label transition (~1-3 extra calls per status change), but all are non-blocking.

---

## ADR-014: Discussions as Human-Only Surface
**Date**: 2026-02-14
**Status**: Accepted

**Context**: GitHub Discussions and Wiki were enabled on the repo. The project needed to decide how (or whether) to use them alongside the existing agent-driven Issue tracker and GitHub Pages static site.

**Decision**:
- **Discussions: adopted as a human-only surface.** Four categories: Announcements (maintainer updates), Decision Suggestions (citizens propose decisions), Methodology (Q&A about scoring/agents), Corrections (report factual errors per Constitution Art. 24). No agent integration — the maintainer manually triages Discussions into Issues when appropriate.
- **Wiki: disabled.** It duplicates `docs/` and the static site, is not version-controlled, and agents cannot maintain it programmatically.
- **Language policy**: Backend, agents, docs, community files, and Discussion structure stay English. The static site (GitHub Pages) uses Montenegrin with proper diacritics (č, ć, š, ž, đ) and ijekavski dialect. User-generated content in Discussions may be in Montenegrin.
- **Issue templates with contact_links** redirect conversational questions to Discussions, keeping the Issue tracker clean for the agent state machine.

**Alternatives considered**:
- Agent-managed Discussions (auto-post analyses, auto-respond) — rejected: Discussions are meant for human conversation; agent noise would discourage participation
- Wiki for documentation — rejected: not version-controlled, duplicates existing docs, agents can't maintain it
- Montenegrin community files — rejected: contributors/developers need English; only the public-facing site targets Montenegrin citizens

**Consequences**: Clean separation between human conversation (Discussions) and agent workflow (Issues). The Issue tracker stays structured and machine-readable. Citizens get a dedicated space to suggest decisions and report errors without needing to understand the agent pipeline. No main loop code changes required.

---

## ADR-015: Project Director Agent for Operational Oversight
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The main loop runs autonomously but has no meta-level feedback mechanism. When systemic problems occur (recurring PR failures, wasted debates, stuck issues, reviewer bugs), no agent detects or corrects them — a human must monitor and file issues manually.

**Decision**: Add a Project Director agent (Phase D) that periodically reviews cycle telemetry and files targeted process improvements:

- **North star: Cycle Yield** — the fraction of cycles producing a merged PR, published analysis, or posted digest. Not gameable (filing more issues doesn't help), captures what matters (the system exists to produce output).
- **Telemetry**: `CycleTelemetry` Pydantic model persisted as JSONL (`output/data/telemetry.jsonl`). Every cycle is instrumented with phase timing, success/failure, errors, and yield status.
- **4-layer resilience**: (L1) never crash the loop — top-level crash guard writes partial telemetry; (L2) record all errors in telemetry; (L3) auto-file stability issues for recurring error patterns (mechanical, no LLM); (L4) Docker `restart: unless-stopped`.
- **Director has NO tools** (`allowed_tools=[]`) — all context pre-fetched and injected into prompt. Prevents runaway commands.
- **5-tier priority**: analysis > human > strategy (#83) > director > FIFO.
- **Hard cap of 2 issues** per Director review, enforced in code regardless of agent output.
- **Runs every N cycles** (default 5, configurable via `--director-interval`). Needs accumulated data.
- **Agent tuning**: Director can file issues to adjust prompts of agents it manages (PM, Coder, Reviewer). Cannot modify its own prompt or higher-level agents.

**Alternatives considered**:
- Director with tool access — rejected: pre-fetching is safer and prevents unbounded exploration
- Director every cycle — rejected: not enough data to spot patterns, unnecessary cost
- Director as a separate process — rejected: tight integration with the main loop is simpler and ensures telemetry access

**Consequences**: The system can detect and correct its own operational problems without human intervention. Telemetry provides visibility into loop health. The circuit breaker (Layer 3) catches recurring errors faster than waiting for the Director's periodic review. The `strategy-suggestion` label is reserved for the future Strategic Director (#83).

---

## ADR-016: News Scout Agent over Custom Scrapers
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Phase 3 (Real Data Ingestion) called for MCP scraper servers (`gov_me_scraper.py`, `news_scraper.py`) to scrape gov.me and news outlets. Building and maintaining custom scrapers is fragile — sites change layouts, require auth handling, and need per-source parsing logic.

**Decision**: Replace custom scrapers with a single News Scout agent that uses Claude's built-in `WebSearch` and `WebFetch` tools to discover and read news. Key design points:
- **Agent-based, not script-based**: A Claude Code SDK agent with `WebSearch` + `WebFetch` discovers and parses news. No custom scraping code.
- **Once per day**: State file (`output/news_scout_state.json`) tracks last fetch date. Skips if already fetched today.
- **Capped at 3 decisions**: Prioritized by public interest to keep analysis costs manageable.
- **Deterministic IDs**: `news-{date}-{sha256(title)[:8]}` prevents duplicate analysis issues.
- **Self-contained issues**: Full `GovernmentDecision` JSON embedded in the GitHub issue body. Execution step parses directly from the issue.
- **Seed data preserved**: Seed decisions still load as fallback/supplement.
- **Non-fatal**: News scout failure doesn't crash the loop.
- **No scraping policy**: MCP scraper stubs deleted. Explicit policy against scraping scripts in `mcp_servers/__init__.py` and `CLAUDE.md`.

**Alternatives considered**:
- Custom MCP scrapers per source — rejected: fragile, high maintenance, requires per-site HTML parsing
- RSS/Atom feeds — rejected: not all Montenegrin sources have reliable feeds for government news
- Third-party news APIs — rejected: limited coverage of Montenegrin government decisions

**Consequences**: No scraping code to maintain. The agent adapts to site changes automatically. Trade-off is reliance on Claude's web search quality for Montenegrin sources and higher per-fetch cost (one agent invocation vs. deterministic HTTP requests). Capping at 3 decisions per day bounds the cost.
