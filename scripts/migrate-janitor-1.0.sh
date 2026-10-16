#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$source_dir/scripts/janitor" --run-module janitor_ext.migrate "$@"
