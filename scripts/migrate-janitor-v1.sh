#!/usr/bin/env bash
# migrate-janitor-v1.sh — move an existing ~/.janitor to the current layout:
# the whole chain in janitor/migrations/ (v1, then v2).
#
# Usage: bash scripts/migrate-janitor-v1.sh [--dry-run]
#
# The `janitor` launcher runs these migrations automatically on first start
# (marker: ~/.janitor/.layout_version); this script is the manual entry point.
#
#   * backs up config, SOUL.md, honcho.json, the skin, skills/ and a consistent
#     copy of state.db to ~/.janitor/.backup/ before changing anything;
#   * v1: adds skills.external_dirs + plugins.enabled: [janitor]; removes Janitor
#     skill copies that match what was shipped (edited ones are kept, reported);
#     refreshes skins/sentry-janitor.yaml only if you never edited it;
#   * v2: retires the skills Janitor no longer ships (see migrate-janitor-v2.sh).
#
# Never touches Docker containers/volumes, .env, shell RC lines or systemd.
# Idempotent: on a home already at the current layout it changes nothing.
#
# Home: $JANITOR_HOME, else ~/.janitor. HERMES_HOME is deliberately ignored so
# a stock Hermes home (~/.hermes) is never migrated by mistake.

set -euo pipefail

DRY_RUN=()
case "${1:-}" in
    "") ;;
    --dry-run) DRY_RUN=(--dry-run) ;;
    -h|--help)
        sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
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
