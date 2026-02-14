"""Central configuration for the AI Government system."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
SEED_DIR = DATA_DIR / "seed"

# Model defaults
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS_PER_AGENT = 16384
MAX_TOKENS_PER_SESSION = 200000


@dataclass(frozen=True)
class SessionConfig:
    """Configuration for a single AI cabinet session."""

    model: str = field(default_factory=lambda: os.environ.get("AI_GOV_MODEL", DEFAULT_MODEL))
    max_tokens_per_agent: int = field(
        default_factory=lambda: int(os.environ.get("AI_GOV_MAX_TOKENS_AGENT", str(MAX_TOKENS_PER_AGENT)))
    )
    max_tokens_per_session: int = field(
        default_factory=lambda: int(os.environ.get("AI_GOV_MAX_TOKENS", str(MAX_TOKENS_PER_SESSION)))
    )
    output_dir: Path = OUTPUT_DIR
    parallel_agents: bool = True
