# Contributing to AI Government

This project is an independent AI mirror of the Montenegrin government. It analyzes real government decisions through ministry-specific AI agents and produces public-interest scorecards.

All contributors — human and AI — are bound by the [Constitution](docs/CONSTITUTION.md).

## For Citizens

### Suggest a Decision for Analysis

Have a government decision you think should be analyzed? Open a post in [Decision Suggestions](https://github.com/vindl/ai-government/discussions/categories/decision-suggestions) with:

- The decision title and date
- A link to the official source (gov.me, Official Gazette, etc.)
- Brief context on why it matters

The maintainer reviews suggestions and creates analysis issues for the AI agents.

### Report an Error

If you find a factual error in an analysis — wrong data, misattributed actions, flawed reasoning — please report it in [Corrections](https://github.com/vindl/ai-government/discussions/categories/corrections).

The Constitution (Article 24) requires the project to correct mistakes publicly: *"When an analysis is wrong — wrong data, flawed logic, unfair characterization — correct it openly."*

### Read a Scorecard

Each scorecard contains:

- **Ministry assessments**: Each ministry agent evaluates the decision from its domain perspective (finance, justice, health, etc.) and assigns a score from 1-10
- **Parliamentary debate**: A synthesized debate across ministry perspectives
- **Independent critic report**: An auditor agent scores both the decision and the quality of the AI analysis
- **Counter-proposal**: What the AI Government would do instead

Scores reflect evidence-based analysis, not political opinion (Constitution Article 19).

## For Developers

### How the Agent Loop Works

The main loop (`scripts/main_loop.py`) runs three phases per cycle:

1. **Phase A — Decision intake**: Checks for new government decisions and creates `task:analysis` issues
2. **Phase B — Self-improvement**: A PM agent proposes improvements, a two-agent debate filters them, accepted proposals enter the backlog as issues
3. **Phase C — Execution**: Picks the oldest backlog issue and routes it — analysis tasks run the orchestrator pipeline, code changes run the PR workflow (coder + reviewer agents)

All state lives in GitHub Issues. Labels control the state machine:
`self-improve:proposed` → `backlog` → `in-progress` → `done` / `failed`

### Submit a Suggestion via Issue

To submit a suggestion that enters the agent pipeline directly, create an issue using the [Decision Suggestion](https://github.com/vindl/ai-government/issues/new?template=decision-suggestion.yml) or [Improvement Suggestion](https://github.com/vindl/ai-government/issues/new?template=improvement-suggestion.yml) templates. Issues labeled `human-suggestion` are picked up by the main loop and triaged alongside AI-generated proposals.

### The HUMAN OVERRIDE Mechanism

Any issue with the `human-suggestion` label bypasses the debate phase and goes directly to the backlog. This ensures human input is never filtered out by the AI triage process.

To override a rejected proposal or force-prioritize a task:
1. Create an issue (or re-label an existing one) with `human-suggestion` + `backlog`
2. The main loop picks it up in the next cycle

### Development Setup

```bash
git clone https://github.com/vindl/ai-government.git
cd ai-government
uv sync                          # install dependencies
uv run ruff check src/ tests/    # lint
uv run mypy src/                 # type check
uv run pytest                    # test
uv run python scripts/build_site.py --output-dir /tmp/_site  # build site
```

### Submitting Changes

1. Fork the repo and create a feature branch
2. Make your changes following the conventions in [CLAUDE.md](CLAUDE.md)
3. Ensure `ruff check`, `mypy --strict`, and `pytest` all pass
4. Open a pull request with a clear description of the change

### Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community guidelines.

### Questions?

For questions about methodology, scoring, or agent behavior, use the [Methodology](https://github.com/vindl/ai-government/discussions/categories/methodology) discussion category.
