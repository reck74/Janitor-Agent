#!/usr/bin/env bash
# migrate-janitor-v2.sh — move an existing ~/.janitor to Janitor layout v2.
#
# Usage: bash scripts/migrate-janitor-v2.sh [--dry-run]
#
# The `janitor` launcher runs this migration automatically on first start
# (marker: ~/.janitor/.layout_version); this script is the manual entry point.
# A pre-1.0 home gets the v1 steps too, in the same run and the same backup.
#
#   * backs up config, SOUL.md, honcho.json, the skin, skills/ and a consistent
#     copy of state.db to ~/.janitor/.backup/v2-<timestamp>/ before changing
#     anything;
#   * removes copies of retired Janitor skills (janitor-core, janitor-config-audit,
#     janitor-browser, the agents/ group, ...) and of janitor-repo-research-agent
#     (now janitor-repo-research) only when they match what Janitor shipped, and
#     reports the ones you edited (kept as-is);
#   * drops retired names from skills.disabled / skills.platform_disabled /
#     janitor.skills, renames janitor-repo-research-agent, and repoints
#     skills.external_dirs entries that named a retired Janitor directory.
#
# Never touches Docker containers/volumes, .env, shell RC lines or systemd.
# Idempotent: a second run reports "already uses layout v2" and changes nothing.
#
# Home: $JANITOR_HOME, else ~/.janitor. HERMES_HOME is deliberately ignored so
# a stock Hermes home (~/.hermes) is never migrated by mistake.

set -euo pipefail

DRY_RUN=()
case "${1:-}" in
    "") ;;
    --dry-run) DRY_RUN=(--dry-run) ;;
    -h|--help)
        sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    *)
        echo "Usage: $0 [--dry-run]" >&2
        exit 2
        ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${JANITOR_HOME:-${HOME}/.janitor}"

PYTHON=python3
for candidate in "$REPO_ROOT/.venv/bin/python3" "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/venv/bin/python3"; do
    if [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

cd "$REPO_ROOT"
exec env PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m janitor.migrations --home "$HOME_DIR" ${DRY_RUN[@]+"${DRY_RUN[@]}"}
