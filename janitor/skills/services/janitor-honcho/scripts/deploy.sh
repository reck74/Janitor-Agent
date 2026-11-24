#!/usr/bin/env bash
# Deploy or repair the local Honcho stack (`janitor services deploy honcho`).
# Idempotent; never removes containers or volumes. All logic lives in
# honcho_setup.py so the guided skill and this entry point share one path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/honcho_setup.py" deploy "$@"
