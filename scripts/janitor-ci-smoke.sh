#!/usr/bin/env bash
# Full Linux acceptance. CI must provide isolated HOME and usable Docker.
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$source_dir/janitor_ext/ci_smoke.py" --source "$source_dir"
