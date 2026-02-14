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
- [ ] Build a decision pipeline: scrape → parse → analyze → output
- [ ] Handle decision deduplication and change detection

## Phase 4: Output & Distribution
- [ ] Polish scorecard format for readability
- [ ] Generate social media thread output automatically
- [ ] Add a web-friendly HTML/static site output option
- [ ] Set up automated posting (Twitter/X API integration)
- [ ] Daily automated sessions via GitHub Actions cron

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
