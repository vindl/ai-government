# AI Government

AI mirror of the Montenegrin government. Analyzes real government decisions through specialized ministry AI agents, simulates parliamentary debate, and produces bilingual scorecards and reports of public interest.

All agents are bound by the [Constitution](docs/CONSTITUTION.md).

**[Live site](https://vindl.github.io/ai-government/)** | [Transparency report](https://vindl.github.io/ai-government/transparency) | [Source code](https://github.com/vindl/ai-government)

## How It Works

1. **News intake**: A News Scout agent searches Montenegrin government sources daily for new decisions
2. **Analysis**: Ten AI ministry agents (Finance, Justice, EU Integration, Health, Interior, Economy, Education, Environment, Tourism, Labour) each evaluate the decision from their domain perspective
3. **Debate**: A parliament agent synthesizes all ministry assessments into a structured debate
4. **Scoring**: An independent critic agent scores the government's decision and the quality of the AI analysis
5. **Counter-proposal**: The AI cabinet produces an alternative proposal with key differences and trade-offs
6. **Output**: Bilingual (EN/MNE) website with scorecards, linked back to the GitHub issue that produced each analysis

## Architecture

Two agent fleets operate autonomously:

- **Government Mirror** (Fleet 1): Python agents via Claude Code SDK — ten ministry agents + Parliament + Critic + Synthesizer. Orchestrated by `government/orchestrator.py`, run through the main loop in `scripts/main_loop.py`.
- **Theseus** (Fleet 2): Specialized Claude Code instances with role-specific prompts in `theseus/` — Coder, Reviewer, PM, Director, Editorial Director, News Scout, Research Scout, Strategic Director. Handles self-improvement, code changes, and editorial oversight.

The website is a React + TypeScript + Tailwind CSS SPA built with Vite. The Python build pipeline exports analysis data as static JSON, then builds the React app. Deployed to GitHub Pages.

All state lives in GitHub Issues. Labels control the pipeline state machine: `self-improve:proposed` → `backlog` → `in-progress` → `done` / `failed`. Every analysis links to its source issue for full transparency.

## Documentation

- [Constitution](docs/CONSTITUTION.md) — binding ethical and operational principles
- [Context](docs/CONTEXT.md) — project background and goals
- [Architecture decisions](docs/DECISIONS.md) — ADRs for key design choices
- [Status](docs/STATUS.md) — current implementation state
- [Roadmap](docs/ROADMAP.md) — what's next
- [Contributing](CONTRIBUTING.md) — how to contribute
- [Code of Conduct](CODE_OF_CONDUCT.md) — community guidelines

## License

MIT
