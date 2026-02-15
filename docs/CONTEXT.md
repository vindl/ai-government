# Project Context & Background

## What Is This?
An AI system that mirrors the Montenegrin government. It takes real government decisions as input, analyzes them through ministry-specific AI agents, simulates parliamentary debate, and produces scorecards and social media content of public interest.

## Why Montenegro?
Montenegro is a small country with an active government making consequential decisions (EU integration, judicial reform, economic policy). Its size makes the government tractable to model, while the decisions are substantive enough to produce meaningful analysis.

## Goals
1. **Transparency**: Make government decisions accessible and understandable
2. **Analysis**: Provide multi-perspective expert analysis of each decision
3. **Public Interest**: Format output for social media engagement (scorecards, thread-ready content)
4. **Automation**: Run daily sessions automatically, processing new decisions

## Constraints
1. **Zero budget**: No funding, no sponsors. All infrastructure must be free-tier or personal resources. The only variable cost is Claude API usage.
2. **Public by default**: Every operational decision is visible on GitHub. This is not a transparency feature — it is the architecture. (See ADR-019)
3. **Quality over growth**: The project optimizes for analytical credibility, not audience size. Engagement metrics are observed, not optimized. (See ADR-022)
4. **Single operator**: One maintainer. The system must run autonomously with minimal human intervention, but all autonomous actions must be publicly traceable.

## Current State
- **Phase**: Initial scaffold (v0.1.0)
- **Status**: Repository structure created, core models and agent framework in place
- **Next**: Wire up real scraping, tune prompts, launch first automated sessions
- See [STATUS.md](./STATUS.md) for detailed implementation status
- See [ROADMAP.md](./ROADMAP.md) for what's next

## Key Technical Choices
- See [DECISIONS.md](./DECISIONS.md) for architectural decision records
- Claude Code SDK for agent orchestration (subprocess-based)
- Pydantic v2 for all data models
- anyio for async parallelism
- ruff + mypy for code quality

## Ministry Agents
| Ministry | Focus Area | Key Concerns |
|----------|-----------|--------------|
| Finance | Economic impact, budget, fiscal policy | Cost, revenue, debt, economic growth |
| Justice | Legal compliance, rule of law | Constitutionality, rights, legal precedent |
| EU Integration | EU alignment, accession progress | EU acquis, benchmarks, reform alignment |
| Health | Public health impact | Healthcare access, safety, epidemiology |
| Interior | Security, administration | Public safety, administrative capacity, enforcement |

## Meta-Agents
| Agent | Role |
|-------|------|
| Parliament | Synthesizes all ministry assessments into structured debate |
| Critic | Independent auditor — scores the decision and all assessments |
