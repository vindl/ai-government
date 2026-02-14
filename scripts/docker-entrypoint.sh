#!/usr/bin/env bash
set -euo pipefail

# --- Validate prerequisites ---

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "ERROR: GH_TOKEN environment variable is required" >&2
  exit 1
fi

if [[ ! -d "${HOME}/.claude" ]]; then
  echo "ERROR: ~/.claude must be mounted (Claude OAuth credentials)" >&2
  exit 1
fi

REPO_URL="${REPO_URL:-https://github.com/vindl/ai-government.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

# --- Configure git auth ---

git config --global url."https://${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
git config --global user.name "ai-government-bot"
git config --global user.email "bot@ai-government.local"

# --- Clone repo ---

WORK_DIR="${HOME}/repo"
echo "Cloning ${REPO_URL} (branch: ${REPO_BRANCH})..."
git clone --branch "${REPO_BRANCH}" --single-branch "${REPO_URL}" "${WORK_DIR}"
cd "${WORK_DIR}"

# --- Install dependencies ---

echo "Installing dependencies..."
uv sync

# --- Print toolchain versions ---

echo "=== Toolchain ==="
echo "Python: $(python --version)"
echo "uv:     $(uv --version)"
echo "Node:   $(node --version)"
echo "gh:     $(gh --version | head -1)"
echo "claude: $(claude --version 2>/dev/null || echo 'not found')"
echo "================="

# --- Map SELF_IMPROVE_* env vars to CLI flags ---

ARGS=()

if [[ -n "${SELF_IMPROVE_MAX_CYCLES:-}" ]]; then
  ARGS+=(--max-cycles "${SELF_IMPROVE_MAX_CYCLES}")
fi

if [[ -n "${SELF_IMPROVE_COOLDOWN:-}" ]]; then
  ARGS+=(--cooldown "${SELF_IMPROVE_COOLDOWN}")
fi

if [[ -n "${SELF_IMPROVE_PROPOSALS:-}" ]]; then
  ARGS+=(--proposals "${SELF_IMPROVE_PROPOSALS}")
fi

if [[ -n "${SELF_IMPROVE_MODEL:-}" ]]; then
  ARGS+=(--model "${SELF_IMPROVE_MODEL}")
fi

if [[ -n "${SELF_IMPROVE_MAX_PR_ROUNDS:-}" ]]; then
  ARGS+=(--max-pr-rounds "${SELF_IMPROVE_MAX_PR_ROUNDS}")
fi

if [[ "${SELF_IMPROVE_DRY_RUN:-false}" == "true" ]]; then
  ARGS+=(--dry-run)
fi

if [[ "${SELF_IMPROVE_VERBOSE:-false}" == "true" ]]; then
  ARGS+=(--verbose)
fi

# --- Run self-improvement loop (exec replaces shell so os.execv works) ---

echo "Starting self-improvement loop with args: ${ARGS[*]:-<none>}"
exec uv run python scripts/self_improve.py "${ARGS[@]}"
