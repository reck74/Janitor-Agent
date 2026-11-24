#!/usr/bin/env bash
# Deploy or repair NocoDB (`janitor services deploy nocodb`). Running that command is the
# user's confirmation, hence --yes. Idempotent; never removes containers or volumes.
# All logic lives in nocodb_setup.py so the guided skill and this entry point share one path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/nocodb_setup.py" deploy --yes "$@"
