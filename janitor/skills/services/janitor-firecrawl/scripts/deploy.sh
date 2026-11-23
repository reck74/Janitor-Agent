#!/usr/bin/env bash
# Deploy or repair the local Firecrawl stack (`janitor services deploy firecrawl`).
# Idempotent; never removes containers or volumes and never touches the profile
# config (activation is a separate, confirmed step of the skill). All logic lives
# in firecrawl_setup.py so the guided skill and this entry point share one path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/firecrawl_setup.py" deploy "$@"
