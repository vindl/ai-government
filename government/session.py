"""Session runner — CLI entrypoint for running AI cabinet sessions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anyio

from government.config import OUTPUT_DIR, SessionConfig
from government.models.decision import GovernmentDecision
from government.orchestrator import Orchestrator, SessionResult
from government.output.scorecard import render_scorecard


def load_decisions(path: Path) -> list[GovernmentDecision]:
    """Load decisions from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        return [GovernmentDecision(**d) for d in data]
    return [GovernmentDecision(**data)]


def save_results(results: list[SessionResult], output_dir: Path) -> list[Path]:
    """Save session results as markdown scorecards."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for result in results:
        scorecard = render_scorecard(result)
        filename = f"scorecard_{result.decision.id}_{result.decision.date}.md"
        path = output_dir / filename
        path.write_text(scorecard)
        paths.append(path)
        print(f"  Saved: {path}")

    return paths


async def run_session(decision_file: Path, config: SessionConfig) -> None:
    """Run a full AI cabinet session."""
    print(f"Loading decisions from {decision_file}...")
    decisions = load_decisions(decision_file)
    print(f"  Found {len(decisions)} decision(s)")

    orchestrator = Orchestrator(config)

    print("\nRunning AI cabinet session...")
    results = await orchestrator.run_session(decisions)

    print(f"\nSession complete. Saving {len(results)} scorecard(s)...")
    save_results(results, config.output_dir)

    print("\nDone.")


def check_api_key() -> None:
    """Verify ANTHROPIC_API_KEY is set before running agents.

    The Claude Agent SDK requires authentication. When running in CI or
    headless environments, ANTHROPIC_API_KEY must be set and non-empty.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key.strip():
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set or empty.\n"
            "The Claude Agent SDK requires authentication to run.\n"
            "Set ANTHROPIC_API_KEY in your environment or repository secrets.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run an AI Government cabinet session")
    parser.add_argument(
        "--decision-file",
        type=Path,
        required=True,
        help="Path to JSON file with government decisions",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for output scorecards",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run agents sequentially instead of in parallel",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the Claude model to use",
    )

    args = parser.parse_args()

    check_api_key()

    config = SessionConfig(
        output_dir=args.output_dir,
        parallel_agents=not args.sequential,
        **({"model": args.model} if args.model else {}),
    )

    try:
        anyio.run(run_session, args.decision_file, config)
    except KeyboardInterrupt:
        print("\nSession interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
