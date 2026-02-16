# AI Stack

Current model versions, SDK versions, agent architecture, and agent roster used by the AI Government project. This document is also injected as context for the Research Scout agent.

*Last updated: 2026-02-16*

## Models

| Component | Model | Notes |
|-----------|-------|-------|
| All agents (default) | `claude-opus-4-6` | Set via `DEFAULT_MODEL` in `scripts/main_loop.py` |

## SDK & Tooling

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `claude-code-sdk` | latest | Agent orchestration — spawns Claude Code subprocesses |
| `pydantic` | `>=2.0` | Data models, validation, JSON serialization |
| `anyio` | `>=4.0` | Async concurrency (task groups for parallel dispatch) |
| `httpx` | `>=0.27` | HTTP client (used by scraping utilities) |
| `tweepy` | `>=4.14` | X (Twitter) API integration (OAuth 1.0a) |
| `jinja2` | `>=3.1` | HTML templating for static site |

## Agent Architecture

- **Orchestration**: Claude Code SDK (`claude_code_sdk.query()`) — each agent runs as an isolated subprocess
- **Communication**: Structured JSON input/output via Pydantic models
- **Parallelism**: `anyio.create_task_group()` for concurrent agent dispatch
- **Tool access**: Agents receive tool access via `allowed_tools` in `ClaudeCodeOptions`
- **Prompt management**: Role prompts in `theseus-fleet/*/CLAUDE.md`, loaded at runtime via `_load_role_prompt()`
- **Permission mode**: `bypassPermissions` for all SDK agents (no interactive approval)

## Agent Roster

### Government Agents (Fleet 1)
| Agent | Module | Focus |
|-------|--------|-------|
| Finance Ministry | `agents/ministry_finance.py` | Budget, taxes, public spending |
| Justice Ministry | `agents/ministry_justice.py` | Laws, regulations, judicial system |
| EU Integration Ministry | `agents/ministry_eu.py` | EU accession, chapter negotiations |
| Health Ministry | `agents/ministry_health.py` | Healthcare policy, public health |
| Interior Ministry | `agents/ministry_interior.py` | Security, police, border control |
| Education Ministry | `agents/ministry_education.py` | Education policy, universities |
| Economy Ministry | `agents/ministry_economy.py` | Economic development, trade, industry |
| Parliament | `agents/parliament.py` | Debate synthesis across ministries |
| Critic | `agents/critic.py` | Independent auditor scoring |
| Synthesizer | `agents/synthesizer.py` | Counter-proposal consolidation |

### Dev Fleet (Fleet 2)
| Agent | Prompt Location | Role | Schedule |
|-------|----------------|------|----------|
| Coder | `theseus-fleet/coder/CLAUDE.md` | Implements code changes | Phase C (on demand) |
| Reviewer | `theseus-fleet/reviewer/CLAUDE.md` | Reviews PRs | Phase C (on demand) |
| PM | `theseus-fleet/pm/CLAUDE.md` | Proposes improvements | Phase B (every cycle) |
| News Scout | `theseus-fleet/news-scout/CLAUDE.md` | Discovers government decisions | Phase A (daily) |
| Editorial Director | `theseus-fleet/editorial-director/CLAUDE.md` | Reviews analysis quality | Phase C (per analysis) |
| Project Director | `theseus-fleet/director/CLAUDE.md` | Operational oversight | Phase D (every N cycles) |
| Strategic Director | `theseus-fleet/strategic-director/CLAUDE.md` | External impact strategy | Phase E (every N cycles) |
| Research Scout | `theseus-fleet/research-scout/CLAUDE.md` | AI ecosystem tracking | Phase F (daily) |

## Upgrade History

| Date | Change | ADR |
|------|--------|-----|
| 2026-02-14 | Initial scaffold with `claude-opus-4-6` | ADR-001 |
| 2026-02-16 | Added Research Scout agent (Phase F) | ADR-024 |
