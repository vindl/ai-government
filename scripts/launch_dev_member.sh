#!/usr/bin/env bash
# Launch a Claude Code dev fleet member with role-specific prompt.
#
# Usage: ./scripts/launch_dev_member.sh <role>
# Roles: coder, reviewer, pm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ROLE="${1:-}"

if [[ -z "$ROLE" ]]; then
    echo "Usage: $0 <role>"
    echo "Available roles: coder, reviewer, pm"
    exit 1
fi

ROLE_DIR="$PROJECT_ROOT/theseus/$ROLE"

if [[ ! -d "$ROLE_DIR" ]]; then
    echo "Error: Unknown role '$ROLE'. Available roles:"
    ls "$PROJECT_ROOT/theseus/"
    exit 1
fi

echo "Launching dev fleet member: $ROLE"
echo "Using prompt: $ROLE_DIR/CLAUDE.md"
echo "---"

exec claude --system-prompt "$(cat "$ROLE_DIR/CLAUDE.md")" \
    --cwd "$PROJECT_ROOT"
