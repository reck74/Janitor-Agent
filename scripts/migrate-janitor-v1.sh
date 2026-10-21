#!/usr/bin/env bash
# migrate-janitor-v1.sh — move an existing ~/.janitor to the Janitor 1.0 layout.
#
# Usage: bash scripts/migrate-janitor-v1.sh [--dry-run]
#
# The `janitor` launcher runs this migration automatically on first start
# (marker: ~/.janitor/.layout_version); this script is the manual entry point.
#
#   * backs up config, SOUL.md, honcho.json, the skin, skills/ and a consistent
#     copy of state.db to ~/.janitor/.backup/v1-<timestamp>/ before changing
#     anything;
#   * adds skills.external_dirs + plugins.enabled: [janitor] to config.yaml;
#   * removes only Janitor skill copies that still match the bundled manifest
#     hash, and reports the ones you edited (kept as-is);
#   * refreshes skins/sentry-janitor.yaml only if you never edited it.
#
# Never touches Docker containers/volumes, .env, shell RC lines or systemd.
# Idempotent: a second run reports "already uses layout v1" and changes nothing.
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
