#!/usr/bin/env bash
set -euo pipefail

# Enter this installation's PM Python; load profile secrets without shell evaluation.
if [[ "${JANITOR_SERVICE_ENV:-}" != "1" ]]; then
    skill_source="$(readlink -f "${BASH_SOURCE[0]}")"
    skill_root="$(cd "$(dirname "$skill_source")/../../.." && pwd)"
    launcher="$skill_root/scripts/janitor"
    [[ -x "$launcher" ]] || launcher="$(command -v janitor || true)"
    [[ -n "$launcher" && -x "$launcher" ]] || { echo "Install/repair Janitor before deploying this skill." >&2; exit 1; }
    export JANITOR_HOME="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
    exec "$launcher" --run-module janitor_ext.optional_deploy "$skill_source" "$@"
fi
umask 077
exec "$JANITOR_SERVICE_PYTHON" -m pm.launch install agent-browser chromium cua-driver
