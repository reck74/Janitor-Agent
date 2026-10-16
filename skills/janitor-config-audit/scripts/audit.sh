#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$script_dir/../../.." && pwd)"
if [[ "${JANITOR_SERVICE_ENV:-}" != "1" ]]; then
    launcher="$root/scripts/janitor"
    [[ -x "$launcher" ]] || launcher="$(command -v janitor || true)"
    [[ -n "$launcher" ]] || { echo 'Repair the Janitor PM runtime before auditing.' >&2; exit 1; }
    exec "$launcher" --run-module janitor_ext.optional_deploy "$0" "$@"
fi
exec "$JANITOR_SERVICE_PYTHON" "$script_dir/audit.py" "$@"
