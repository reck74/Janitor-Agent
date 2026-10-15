#!/usr/bin/env bash
# Historical command, current migration implementation and portable backup contract.
set -euo pipefail
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --dry-run ) ]]; then
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
fi
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HERMES_HOME="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then
    echo "No config at $HERMES_HOME/config.yaml — nothing to migrate" >&2
    exit 1
fi
if [[ -n "${HERMES_PYTHON:-}" || -n "${__HERMES_TEST_PYTHON:-}" ]]; then
    selected_python="${HERMES_PYTHON:-${__HERMES_TEST_PYTHON:-}}"
elif [[ -x "$source_dir/.hermes/bin/hermes" ]]; then
    exec "$source_dir/scripts/janitor" --run-module janitor_ext.migrate_compat "$@"
else
    selected_python=python3
fi
# -I rejects hostile caller cwd/PYTHONPATH; only this installation supplies modules.
exec "$selected_python" -I -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from janitor_ext.migrate_compat import main; raise SystemExit(main())' "$source_dir" "$@"
