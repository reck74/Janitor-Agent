#!/usr/bin/env bash
# Compatibility entrypoint; the optional skill owns deployment.
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$source_dir/skills/janitor-honcho/scripts/deploy.sh" "$@"
