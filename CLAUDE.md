# AI Government — Project Conventions

## Overview
AI mirror of the Montenegrin government. Analyzes real government decisions through ministry-specific AI agents, produces impactful scorecards and reports of public interest.

## Architecture
- **Government agents** (Fleet 1): Python + Claude Code SDK — ministry subagents that analyze decisions
- **Dev fleet** (Fleet 2): Claude Code instances with role-specific prompts (coder, reviewer, tester, pm, devops, publisher)

## Tech Stack
- Python 3.12+
- Claude Code SDK for agent orchestration
- Pydantic v2 for data models
- anyio for async
- httpx + BeautifulSoup4 for scraping
- Jinja2 for HTML templating (static site)

## Code Style
- Use `ruff` for linting (`ruff check src/ tests/`)
- Use `mypy --strict` for type checking
- All models use Pydantic v2
- Async-first: use `anyio` for concurrency, not `asyncio` directly
- Imports: stdlib → third-party → local (enforced by ruff isort)

## Project Layout
- `src/ai_government/` — main package
  - `agents/` — agent implementations (inherit from `GovernmentAgent`)
  - `prompts/` — prompt templates (one per agent)
  - `models/` — Pydantic data models
  - `mcp_servers/` — MCP tool servers (scrapers)
  - `output/` — output formatters (scorecard, social media, HTML, site builder)
- `site/` — site source (templates, static assets, announcement content)
- `tests/` — pytest tests
- `dev-fleet/` — Claude Code role prompts
- `data/seed/` — sample decision data
- `scripts/` — CLI scripts
- `output/data/` — serialized analysis results (committed, feeds the site builder)

## Running
```bash
uv sync                    # install deps
uv run ruff check src/ tests/  # lint
uv run mypy src/           # type check
uv run pytest              # test
uv run python scripts/run_session.py --decision-file data/seed/sample_decisions.json
uv run python scripts/pr_workflow.py "<task description>"  # PR workflow
uv run python scripts/main_loop.py                        # unified main loop (indefinite)
uv run python scripts/main_loop.py --dry-run --max-cycles 1  # test ideation + triage only
uv run python scripts/main_loop.py --max-cycles 3         # 3 cycles then stop
uv run python scripts/main_loop.py --skip-improve         # analysis only
uv run python scripts/main_loop.py --skip-analysis        # self-improvement only
uv run python scripts/build_site.py                        # build static site to _site/
uv run python scripts/build_site.py --output-dir /tmp/_site  # build to custom dir

# Docker (isolated main loop)
export GH_TOKEN="ghp_..."
docker compose build                                       # build image
docker compose up                                          # run indefinitely
docker compose up -d                                       # detached
docker compose logs -f ai-government                       # follow logs
LOOP_DRY_RUN=true docker compose up                        # dry run
LOOP_MAX_CYCLES=3 docker compose up                        # 3 cycles
LOOP_SKIP_IMPROVE=true docker compose up                   # analysis only
docker compose down                                        # stop
```

## Conventions
- Every agent class inherits from `GovernmentAgent` in `agents/base.py`
- Prompts live in `prompts/` as string constants, not inline in agent code
- All agent outputs are typed Pydantic models
- Use `MinistryConfig` dataclass for per-ministry configuration
- The orchestrator dispatches to agents in parallel via `anyio.create_task_group()`
- Output goes to `output/` directory (gitignored)

## Constitution
- **All agents are bound by `docs/CONSTITUTION.md`** — read it before doing any work
- It defines the project's ethical framework: public loyalty, anti-corruption, transparency, fiscal responsibility, nonpartisanship
- When in doubt about any decision, the constitution is the tiebreaker

## Documentation
- `docs/CONSTITUTION.md` — binding ethical and operational principles for all agents
- `docs/CONTEXT.md` — project background, goals, why Montenegro, agent roles
- `docs/STATUS.md` — what's implemented, what's a stub, known gotchas
- `docs/ROADMAP.md` — phased plan for what to build next
- `docs/DECISIONS.md` — architectural decision records (ADRs)
- **Read `docs/STATUS.md` first when resuming work** — it has implementation details and known issues
- **Always update docs/ when doing work** — every session should update relevant docs:
  - `docs/STATUS.md` — update what's implemented, what changed, new gotchas
  - `docs/DECISIONS.md` — add an ADR for any architectural or design decision
  - `docs/ROADMAP.md` — check off completed items, add new items discovered

## PR Workflow Operation
- The PR workflow (`scripts/pr_workflow.py`) should be run from within the Claude Code session, not in a separate terminal
- Launch it as a background task, monitor output, and fix errors in a loop
- Success criteria: visible GitHub PR comments, coder responses to feedback, and ultimately PR merge or close
- The reviewer agent uses `gh pr comment` (not `gh pr review`) with structured verdict markers (`VERDICT: APPROVED` or `VERDICT: CHANGES_REQUESTED`) because GitHub blocks self-reviews
- If the reviewer fails to post a verdict comment, the prompt or max_turns may need adjustment

## Git
- Do NOT include `Co-Authored-By` lines in commit messages
- Write concise commit messages focused on the "why"
