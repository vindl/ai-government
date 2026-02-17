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

# --- Clone or update repo ---

WORK_DIR="${HOME}/repo"
if [[ -d "${WORK_DIR}/.git" ]]; then
  echo "Repo already exists at ${WORK_DIR}, updating..."
  cd "${WORK_DIR}"
  git fetch origin
  git checkout "${REPO_BRANCH}"
  git reset --hard "origin/${REPO_BRANCH}"
else
  echo "Cloning ${REPO_URL} (branch: ${REPO_BRANCH})..."
  git clone --branch "${REPO_BRANCH}" --single-branch "${REPO_URL}" "${WORK_DIR}"
  cd "${WORK_DIR}"
fi

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

# --- Map LOOP_* env vars to CLI flags ---

ARGS=()

if [[ -n "${LOOP_MAX_CYCLES:-}" ]]; then
  ARGS+=(--max-cycles "${LOOP_MAX_CYCLES}")
fi

if [[ -n "${LOOP_COOLDOWN:-}" ]]; then
  ARGS+=(--cooldown "${LOOP_COOLDOWN}")
fi

if [[ -n "${LOOP_MODEL:-}" ]]; then
  ARGS+=(--model "${LOOP_MODEL}")
fi

if [[ -n "${LOOP_MAX_PR_ROUNDS:-}" ]]; then
  ARGS+=(--max-pr-rounds "${LOOP_MAX_PR_ROUNDS}")
fi

if [[ "${LOOP_DRY_RUN:-false}" == "true" ]]; then
  ARGS+=(--dry-run)
fi

if [[ "${LOOP_VERBOSE:-false}" == "true" ]]; then
  ARGS+=(--verbose)
fi

# --- Run main loop (exec replaces shell so os.execv works) ---

echo "Starting main loop with args: ${ARGS[*]:-<none>}"
exec uv run python scripts/main_loop.py "${ARGS[@]}"
