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

---

## ADR-017: Editorial Director for Analysis Quality Control
**Date**: 2026-02-15
**Status**: Accepted

**Context**: No agent monitors whether published analyses are accurate, compelling, or resonating with the public. Without quality oversight, we risk publishing low-impact or flawed content. Strategic Director (#122) identified this capability gap.

**Decision**: Add Editorial Director agent that reviews completed analyses for:
1. **Factual accuracy** — no errors, misinterpretations, or unsupported claims
2. **Narrative quality** — clear structure, logical flow, engaging for general readers
3. **Public relevance** — addresses citizen concerns, actionable insights
4. **Constitutional alignment** — transparency, anti-corruption, fiscal responsibility
5. **Engagement potential** — tracks which topics/framing resonate (when metrics available)

**Implementation**:
- Role prompt: `dev-fleet/editorial-director/CLAUDE.md`
- Model: `EditorialReview` (approval flag, quality score 1-10, strengths, issues, recommendations)
- Integration: Runs in `step_execute_analysis()` after orchestrator completes but before marking issue done
- Non-blocking: Review failures are non-fatal. If not approved, files an `editorial-quality` issue and proceeds with publication
- Output: JSON review with approval status, quality score, and actionable feedback

**Alternatives considered**:
- Manual human review — rejected: doesn't scale, adds latency
- Post-publication quality analysis — rejected: better to catch issues before publication
- Quality checks in existing agents — rejected: dilutes each agent's focus, no unified quality standard
- Blocking publication on failure — rejected: creates bottleneck, better to flag and continue

**Consequences**:
- One additional API call per analysis (runs after analysis completion)
- Quality issues tracked via GitHub issues with `editorial-quality` label
- Feedback loop enables continuous improvement of analysis quality
- When social/engagement metrics are available, Editorial Director can identify which topics/framing generate most public interest
- Non-blocking design ensures system keeps running even if review fails

---

## ADR-018: Zero-Budget Constraint as Design Driver

**Date**: 2026-02-14
**Status**: Accepted

**Context**: This project has no funding. No grants, no sponsors, no revenue. Every tool choice must account for the fact that the project operates on the maintainer's personal resources and free tiers.

**Decision**: Treat zero-budget as a first-class architectural constraint, not a temporary limitation:
- **GitHub as platform**: Issues (task tracking), Actions (CI/CD), Pages (hosting), Projects (kanban), Discussions (community) — all free for public repos
- **No paid infrastructure**: No databases, no servers, no SaaS subscriptions. State lives in git, files, and GitHub's free tier
- **Docker for local execution**: The main loop runs on personal hardware or free CI minutes, not cloud VMs
- **Claude API is the only variable cost**: All other tooling is zero-cost. This focuses cost management on a single dimension

**Consequences**: The project is reproducible by anyone with a Claude API key and a GitHub account. No vendor lock-in beyond GitHub (which is also the transparency mechanism — see ADR-019). The constraint forces simplicity: if a feature requires paid infrastructure, it must justify itself against the alternative of not existing. Trade-off: free tiers have rate limits (GitHub API: 5,000 requests/hour authenticated, 500 content-creation/hour; Actions: 2,000 minutes/month) which bound throughput.

---

## ADR-019: GitHub as Transparency Mechanism, Not Just Convenience

**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project uses GitHub Issues for agent coordination, PRs for code changes, and Actions for automation. This could be seen as a default engineering choice — GitHub is what developers reach for. But for this project, the choice is load-bearing.

**Decision**: GitHub is the coordination layer *because it is public by default*. This directly serves the Constitution (Art. 5: "show your reasoning", Art. 22: "methodology, source code, prompts, and analytical framework are public"):
- Every agent proposal, debate, and verdict is a GitHub Issue comment — visible to anyone
- Every code change goes through a PR with reviewer feedback — auditable
- The self-improvement loop's decisions are traceable: why was this task proposed? What was the debate? Who approved it?
- The project board shows what the system is working on, right now, in real time

This is a form of **stigmergy** — indirect coordination through a shared, observable environment. Agents don't message each other; they leave traces (issues, labels, comments) that other agents read. The public reads the same traces.

**Alternatives considered**:
- Internal task queue (Redis, SQLite) — rejected: faster, but opaque. Citizens can't see the queue
- Linear/Jira — rejected: adds cost, moves coordination behind a login wall
- File-based coordination — rejected: not observable without reading the repo directly

**Consequences**: The project's operational transparency is automatic, not performative. There's no separate "transparency report" to write — the work *is* the report. Trade-off: GitHub API latency (200-500ms per call vs <1ms for file I/O), rate limits, and the fact that GitHub is a US corporation hosting a Montenegrin public interest project. The transparency benefit outweighs these costs.

---

## ADR-020: Model Selection — Quality vs Cost Trade-off

**Date**: 2026-02-15
**Status**: Proposed

**Context**: The project uses Claude models for all agent work. The highest-quality models (Opus) produce the best analysis but cost significantly more per token. Routine tasks (label management, template formatting, issue parsing) don't need frontier-model reasoning.

**Decision**: Tiered model selection based on task criticality:
- **Analysis agents** (ministries, parliament, critic, synthesizer): Use the best available model. These produce the public-facing output that defines the project's credibility. Cutting quality here undermines the mission
- **Dev fleet** (coder, reviewer, PM): Use capable but cost-effective models. Code quality matters but is verified by CI and review loops — errors get caught
- **Directors** (project, strategic, editorial): Use high-quality models. These make judgment calls about what to work on and whether output meets standards
- **News Scout**: Use capable models. Needs web comprehension and news judgment, but output is reviewed before publication
- **Routine operations** (issue parsing, label transitions, template rendering): No LLM call where deterministic code suffices

**Consequences**: The most expensive operations are the ones that matter most — public-facing analysis. Cost scales primarily with the number of decisions analyzed per day (capped at 3 by the News Scout). Self-improvement cycles are the secondary cost driver and can be throttled via `--max-cycles` and `--cooldown`. The project should track per-cycle costs in telemetry to inform future model selection decisions.

---

## ADR-021: Monorepo — Engine and Application Are One Organism

**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project has two conceptual layers: (1) the government analysis agents that produce public-facing output, and (2) the self-improving meta-layer (directors, PM, coder, reviewer, main loop) that evolves the system. These could be separated into two repositories — a reusable "self-improving agent engine" and a domain-specific "government analysis application."

**Decision**: Keep everything in one repository. The layers are not separable in practice:
- **The engine modifies the application**: The coder agent creates PRs that change ministry prompts, analysis models, and output templates. Cross-repo PRs would add significant complexity
- **`_reexec()` assumes one repo**: `git pull --ff-only && os.execv()` restarts the process with new code. Coordinating pulls across two repos breaks this
- **GitHub Issues span both layers**: A single issue might touch analysis quality (application) and prompt tuning (engine). One issue tracker is simpler than cross-repo references
- **The transparency mechanism is repo-scoped**: One public repo = one place for citizens to observe the entire system
- **The engine isn't domain-neutral**: Key design choices (GitHub for transparency, Constitution as reward signal, public observability) are driven by the government-analysis mission. Extracting a "generic" engine would strip out its most distinctive properties

**Alternatives considered**:
- Two repos (engine + application) — rejected: cross-repo self-modification is significantly more complex; the engine's design is mission-specific; no second domain exists to justify the extraction
- Monorepo with hard internal boundaries (separate packages) — considered for future: if the engine proves generalizable, extract then, with the benefit of knowing where the real boundaries are

**Consequences**: Simpler operations, simpler CI, single audit trail. The cost is that the project looks like one large system rather than a composable toolkit. This is acceptable because it *is* one system — the self-improvement and the analysis co-evolve.

---

## ADR-022: Engagement Metrics as Validation, Not Optimization Target

**Date**: 2026-02-15
**Status**: Proposed

**Context**: The project posts daily digests to X and publishes scorecards on the website. Social media engagement (likes, retweets, replies) and website traffic are measurable signals. The temptation is to optimize for these metrics — chase engagement to "prove" impact.

**Decision**: Treat engagement metrics as a **validation signal** (are people reading this?) not an **optimization target** (how do we get more clicks?):
- Track engagement data when available, but do not feed it into agent reward loops
- Do not modify analysis framing, topic selection, or tone to increase engagement
- The Constitution (Art. 4: "never distort, omit, or spin") explicitly prohibits optimizing for attention at the cost of accuracy
- Engagement is a lagging indicator — early engagement will be low or zero. This is not a signal to change course
- When engagement data exists, use it as a **dashboard** (which topics resonate?) not a **score** (are we doing well?)

**Rationale (Goodhart's Law)**: Once engagement becomes a target, the system will find ways to game it — sensationalist framing, partisan hot-takes, outrage-driven topic selection. These are the exact behaviors the Constitution prohibits. The project's credibility depends on *not* optimizing for attention.

**Consequences**: The project may grow slowly. Early engagement will be negligible. This is acceptable — the goal is a trustworthy institution, not a viral account. The Editorial Director tracks engagement potential as one of several quality dimensions, but it does not override factual accuracy or constitutional alignment.

---

## ADR-023: AGPL-3.0 Licensing

**Date**: 2026-02-14
**Status**: Accepted

**Context**: The project's code, prompts, and methodology are public (Constitution Art. 22). The license must allow anyone to reuse, modify, and learn from the work — but prevent commercial exploitation or closed-source forks. A government transparency tool should not become someone's proprietary product.

**Decision**: License under **AGPL-3.0** (GNU Affero General Public License v3.0):
- **Allows**: copying, modification, redistribution, running the software for any purpose
- **Requires**: any modified version — including one deployed as a network service — must release its full source code under AGPL-3.0
- **Effectively prevents closed-source use**: the copyleft obligation makes proprietary forks legally impossible
- **Effectively deters commercial exploitation**: most companies will not adopt AGPL code because they cannot keep modifications proprietary. This is a practical barrier, not a legal prohibition

**Why not an explicit non-commercial clause**:
- Licenses with non-commercial restrictions (CC BY-NC-SA, Polyform Noncommercial) are not recognized as "open source" by OSI. This limits community adoption and creates ambiguity (what counts as "commercial"?)
- AGPL achieves the same practical outcome — deterring commercial capture — while remaining a recognized free software license
- If another government, NGO, or civic tech project wants to adapt this for their country, AGPL lets them. A non-commercial clause might block legitimate civic reuse by organizations that technically operate commercially

**Alternatives considered**:
- MIT/Apache — rejected: allows closed-source forks and commercial exploitation with no obligations
- GPL-3.0 — rejected: copyleft applies to distribution but has the "SaaS loophole" — deploying as a web service doesn't trigger source disclosure. AGPL closes this gap
- CC BY-NC-SA 4.0 — rejected: not designed for software (no patent grant, no linking semantics), discouraged by FSF and OSI for code
- Polyform Noncommercial 1.0.0 — rejected: explicitly non-commercial but doesn't require derivative works to stay open source

**Consequences**: Anyone can fork, adapt, and deploy this project — for Montenegro, for another country, for any civic purpose — as long as they keep it open. Companies can use it too, but they must open-source their modifications. The AGPL's reputation as "the license companies avoid" is a feature, not a bug, for this project.

---

## ADR-024: Research Scout Agent for AI Ecosystem Tracking
**Date**: 2026-02-16
**Status**: Accepted

**Context**: The project uses fixed AI model versions and SDK patterns. AI research moves fast — model releases, SDK updates, and new agent architecture patterns could improve the project but are currently discovered only by manual human review.

**Decision**: Add a Research Scout agent (Phase F) that runs weekly to scan for AI ecosystem developments and files actionable improvement issues. Uses `WebSearch` + `WebFetch` (same as News Scout). Tracks three areas: model releases, agent architecture patterns, and SDK/tooling updates. Context injection includes `docs/AI_STACK.md` (current stack) and existing open `research-scout` issues (for dedup).

**Design choices**:
- Daily cadence to work through existing backlog of improvements — AI research moves slower than daily news
- Same state-file pattern as News Scout but with configurable interval
- Max 2 issues per run — actionable improvements only, not ecosystem commentary
- Tier 5 in `step_pick()` priority — after Director suggestions, before FIFO
- `docs/AI_STACK.md` serves dual purpose: documentation and agent context

**Alternatives considered**:
- Daily cadence — rejected: too frequent for the pace of AI releases, wastes API calls
- No dedup context — rejected: would file duplicate issues for the same model release across weeks
- Higher priority tier — rejected: ecosystem upgrades are important but not urgent compared to human suggestions, analysis tasks, or director-identified operational issues

**Consequences**: The project will automatically track relevant AI ecosystem developments and file upgrade issues. Reduces human overhead for monitoring releases. `docs/AI_STACK.md` becomes the single source of truth for the project's AI stack.
