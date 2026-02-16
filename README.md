# AI Government 🏛️

AI mirror of the Montenegrin government. Analyzes real government decisions through specialized ministry AI agents, simulates parliamentary debate, and produces bilingual scorecards and reports of public interest.

All agents are bound by the [Constitution](docs/CONSTITUTION.md).

## How It Works

1. **Input**: Real Montenegrin government decisions, sourced by the News Scout agent via web search
2. **Analysis**: Each AI ministry agent evaluates the decision from its domain perspective
3. **Debate**: A parliament agent synthesizes all ministry assessments into a debate
4. **Scoring**: An independent critic agent scores the decision and all assessments
5. **Output**: Bilingual (EN/MNE) static site with HTML scorecards + optional X/Twitter posts

## Architecture

Two agent fleets:

- **Government Mirror** (Fleet 1): Python agents via Claude Code SDK — Finance, Justice, EU Integration, Health, Interior, Economy, Education, Environment, Tourism ministries + Parliament + Critic + Synthesizer
- **Theseus** (Fleet 2): Specialized Claude Code instances with role-specific prompts in `theseus/` — Coder, Reviewer, PM, Director, Editorial Director, News Scout, Research Scout, Strategic Director

## Quick Start

```bash
# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, GH_TOKEN, and optional TWITTER_* credentials

# Run a session with sample data
uv run python scripts/run_session.py --decision-file data/seed/sample_decisions.json

# Run the main loop (news intake + analysis + self-improvement)
uv run python scripts/main_loop.py --max-cycles 1

# Build the static site
uv run python scripts/build_site.py

# Launch a Theseus fleet member
./scripts/launch_dev_member.sh coder
```

### Docker

```bash
export GH_TOKEN="ghp_..."
docker compose build
docker compose up          # run indefinitely
LOOP_MAX_CYCLES=3 docker compose up  # 3 cycles then stop
```

## Development

```bash
uv run ruff check government/ tests/   # Lint
uv run mypy government/                 # Type check
uv run pytest                           # Test
```

## License

MIT
