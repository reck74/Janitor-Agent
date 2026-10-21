#!/usr/bin/env bash
# Deploy local Honcho. The implementation is scripts/setup-honcho.sh, which
# janitor-install.sh also runs during base install (AGENTS.md directive #8).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
export JANITOR_SOURCE_DIR="${JANITOR_SOURCE_DIR:-$REPO_ROOT}"
exec bash "$REPO_ROOT/scripts/setup-honcho.sh" "$@"
