#!/usr/bin/env bash
# Shared first-run configuration; runtime acquisition belongs to bootstrap.
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HERMES_HOME="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
exec "$source_dir/scripts/janitor" --run-module janitor_ext.install --home "$HERMES_HOME" "$@"
