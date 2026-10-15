#!/usr/bin/env bash
set -euo pipefail
skill_source="$(readlink -f "${BASH_SOURCE[0]}")"
source_dir="$(cd "$(dirname "$skill_source")/../../.." && pwd)"
launcher="$source_dir/scripts/janitor"
[[ -x "$launcher" ]] || launcher="$(command -v janitor || true)"
[[ -n "$launcher" && -x "$launcher" ]] || { echo "Install/repair Janitor before deploying Honcho." >&2; exit 1; }
exec "$launcher" --run-module janitor_ext.honcho "$@"
