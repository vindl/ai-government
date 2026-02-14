# AI Government 🏛️

AI mirror of the Montenegrin government. Analyzes real government decisions through specialized ministry AI agents, simulates parliamentary debate, and produces impactful scorecards and social media reports of public interest.

## How It Works

1. **Input**: Real Montenegrin government decisions (scraped or manual)
2. **Analysis**: Each AI ministry agent evaluates the decision from its domain perspective
3. **Debate**: A parliament agent synthesizes all ministry assessments into a debate
4. **Scoring**: An independent critic agent scores the decision and all assessments
5. **Output**: Markdown scorecards + Twitter/X thread-ready content

## Architecture

Two agent fleets:

- **Government Mirror** (Fleet 1): Python agents via Claude Code SDK — Finance, Justice, EU Integration, Health, Interior ministries + Parliament + Critic
- **Dev Fleet** (Fleet 2): Specialized Claude Code instances (Coder, Reviewer, Tester, PM, DevOps) with role-specific prompts for building and maintaining the system

## Quick Start

```bash
# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Run a session with sample data
uv run python scripts/run_session.py --decision-file data/seed/sample_decisions.json

# Launch a dev fleet member
./scripts/launch_dev_member.sh coder
```

## Development

```bash
uv run ruff check src/ tests/   # Lint
uv run mypy src/                 # Type check
uv run pytest                    # Test
```

## License

MIT
