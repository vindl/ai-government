# Roadmap

## Phase 1: Scaffold (DONE)
- [x] Repo structure, dependencies, CI
- [x] Data models (GovernmentDecision, Assessment, Verdict, ParliamentDebate, CriticReport)
- [x] Agent framework (base class, 5 ministries, parliament, critic)
- [x] Orchestrator with parallel dispatch
- [x] Output formatters (markdown scorecard, Twitter/X threads)
- [x] Dev fleet prompts (coder, reviewer, tester, pm, devops)
- [x] Seed data (3 realistic Montenegrin government decisions)
- [x] Tests (16 passing), ruff, mypy all green

## Phase 1.5: Dev Fleet Tooling (DONE)
- [x] PR-based coder-reviewer workflow (`scripts/pr_workflow.py`)
- [x] Documentation convention: always update docs/ when doing work
- [x] Autonomous self-improvement loop (`scripts/self_improve.py`)

## Phase 1.7: Docker Isolation (DONE)
- [x] Dockerfile with Python 3.12, Node.js 20, gh CLI, uv, Claude Code CLI
- [x] docker-compose.yml with resource limits, restart policy, signal handling
- [x] Entrypoint script: validates env, clones repo, maps env vars to CLI flags
- [x] `uv sync` in `_reexec()` for dependency updates between cycles

## Phase 1.8: Unified Main Loop (DONE)
- [x] Renamed `self_improve.py` → `main_loop.py`
- [x] Three-phase cycle: decision checking → self-improvement → unified execution
- [x] Task-type routing: `task:analysis` → orchestrator, `task:code-change` → pr_workflow
- [x] Analysis tasks get execution priority in backlog
- [x] `--skip-analysis` and `--skip-improve` flags for phase control
- [x] Docker env vars renamed: `SELF_IMPROVE_*` → `LOOP_*`
- [x] `get_pending_decisions()` as scraper integration point (currently reads seed data)

## Phase 2: First Real Run
- [ ] Run the full pipeline against Claude API with seed decisions
- [ ] Evaluate output quality — are assessments substantive?
- [ ] Evaluate JSON parsing reliability — do agents consistently return valid JSON?
- [ ] Tune prompts based on real output
- [ ] Verify Montenegrin language quality (grammar, terminology)
- [ ] Add cost tracking / token usage logging

## Phase 3: Real Data Ingestion
- [ ] Implement `gov_me_scraper.py` MCP server — scrape gov.me for real decisions
- [ ] Implement `news_scraper.py` MCP server — scrape Montenegrin news for context
- [ ] Parse real government session agendas and decisions
- [ ] Wire scrapers into `get_pending_decisions()` in `main_loop.py` (integration point ready)
- [ ] Build a decision pipeline: scrape → parse → analyze → output
- [ ] Handle decision deduplication and change detection

## Phase 4: Output & Distribution
- [x] Add a web-friendly HTML/static site output option (Jinja2 templates, site builder, GitHub Pages deploy)
- [x] Publisher dev-fleet role for curating public content
- [ ] Polish scorecard format for readability
- [ ] Generate social media thread output automatically
- [x] Set up automated posting (X API integration via tweepy)
- [ ] Daily automated sessions via GitHub Actions cron

## Phase 4.5: Counter-Proposals (DONE)
- [x] `MinistryCounterProposal` and `CounterProposal` Pydantic models
- [x] Ministry prompts request domain-specific alternatives (same API call)
- [x] `SynthesizerAgent` consolidates ministry inputs into unified counter-proposal
- [x] Orchestrator Phase 3: synthesizer runs after parliament + critic
- [x] Output renderers: markdown scorecard, HTML templates, CSS, social media, X digest
- [x] Tests for models, agent parsing, backwards compatibility

## Phase 5: Quality & Depth
- [ ] Add more ministry agents (Education, Defence, Environment, etc.)
- [ ] Improve parliament agent with real party positions and dynamics
- [ ] Add historical context — compare with previous similar decisions
- [ ] Add EU progress tracking — link decisions to accession chapter progress
- [ ] Implement feedback loop — track which scorecards get engagement, tune accordingly

## Phase 6: Scale & Reliability
- [ ] Add retry logic and error handling for API failures
- [ ] Budget management — track and limit API spend per session
- [ ] Add structured logging
- [ ] Archive past sessions and build a searchable history
- [ ] Add A/B testing for prompt variations

## Ideas / Backlog
- Interactive mode: let users submit decisions for analysis
- Comparative analysis: score Montenegro against regional peers
- Translation layer: output in English for international audience
- Citizen feedback integration: incorporate public comments/reactions
- Integration with Montenegro's open data portal if available
