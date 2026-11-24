#!/usr/bin/env bash
# Deploy or repair n8n (`janitor services deploy n8n`). Running that command is the
# user's confirmation, hence --yes. Idempotent; never removes containers or volumes.
# All logic lives in n8n_setup.py so the guided skill and this entry point share one path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/n8n_setup.py" deploy --yes "$@"
