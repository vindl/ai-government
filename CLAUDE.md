# AI Government — Project Conventions

## Overview
AI mirror of the Montenegrin government. Analyzes real government decisions through ministry-specific AI agents, produces impactful scorecards and reports of public interest.

## Architecture
- **Government agents** (Fleet 1): Python + Claude Code SDK — ministry subagents that analyze decisions
- **Dev fleet** (Fleet 2): Claude Code instances with role-specific prompts (coder, reviewer, tester, pm, devops)

## Tech Stack
- Python 3.12+
- Claude Code SDK for agent orchestration
- Pydantic v2 for data models
- anyio for async
- httpx + BeautifulSoup4 for scraping

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
  - `output/` — output formatters (scorecard, social media)
- `tests/` — pytest tests
- `dev-fleet/` — Claude Code role prompts
- `data/seed/` — sample decision data
- `scripts/` — CLI scripts

## Running
```bash
uv sync                    # install deps
uv run ruff check src/ tests/  # lint
uv run mypy src/           # type check
uv run pytest              # test
uv run python scripts/run_session.py --decision-file data/seed/sample_decisions.json
uv run python scripts/pr_workflow.py "<task description>"  # PR workflow
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

## Git
- Do NOT include `Co-Authored-By` lines in commit messages
- Write concise commit messages focused on the "why"
