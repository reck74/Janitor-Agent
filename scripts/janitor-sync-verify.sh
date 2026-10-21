#!/usr/bin/env bash
# janitor-sync-verify.sh — the post-`chore(sync)` gate for the Janitor fork.
#
# Usage: scripts/janitor-sync-verify.sh [--base REF] [--skip-tui] [--skip-desktop]
#
#   1. no merge-conflict markers in files that differ from upstream;
#   2. `python -m janitor.overlay check` — every divergence from the upstream
#      base is fork-owned or a declared touchpoint (janitor/overlay.yaml);
#   3. the Janitor Python suite (tests/janitor/, via scripts/run_tests.sh);
#   4. the desktop build-overlay unit tests (node --test);
#   5. the TUI gate: `npm run build:ink`, `npm run build` + `npm test` in
#      ui-tui (directive #7).
#
# --base defaults to `upstream.base` in janitor/overlay.yaml. After merging a
# new upstream tag, set that field to the tag's commit in the same PR.
# A missing base commit (shallow clone) is fetched from upstream by SHA.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASE=""
RUN_TUI=1
RUN_DESKTOP=1
while [ $# -gt 0 ]; do
    case "$1" in
        --base) BASE="${2:?--base needs a ref}"; shift 2 ;;
        --skip-tui) RUN_TUI=0; shift ;;
        --skip-desktop) RUN_DESKTOP=0; shift ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

PYTHON=python3
for candidate in .venv/bin/python venv/bin/python .venv/Scripts/python.exe; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
done

step() { printf '\n▶ %s\n' "$1"; }

if [ -z "$BASE" ]; then
    BASE="$("$PYTHON" -c 'from janitor.overlay import load_overlay; print(load_overlay().upstream_base)')"
fi
UPSTREAM_URL="$("$PYTHON" -c 'import yaml; print(yaml.safe_load(open("janitor/overlay.yaml"))["upstream"]["repo"])')"

step "Upstream base ${BASE}"
if ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
    echo "  fetching ${BASE} from ${UPSTREAM_URL}"
    git fetch --quiet --depth=1 --no-tags "$UPSTREAM_URL" "$BASE"
fi

step "Conflict markers"
markers="$(git diff --name-only --no-renames --diff-filter=d "$BASE" \
    | while IFS= read -r path; do
        [ -f "$path" ] && grep -lE '^(<<<<<<<|>>>>>>>)( |$)' -- "$path" || true
      done)"
if [ -n "$markers" ]; then
    echo "✗ unresolved conflict markers in:" >&2
    printf '  %s\n' $markers >&2
    exit 1
fi
echo "✓ none"

step "Overlay check"
"$PYTHON" -m janitor.overlay check --base "$BASE"

step "Janitor Python suite (tests/janitor/)"
scripts/run_tests.sh tests/janitor/

if [ "$RUN_DESKTOP" -eq 1 ]; then
    step "Desktop build overlay"
    node --test apps/desktop-janitor/scripts/build.test.mjs
fi

if [ "$RUN_TUI" -eq 1 ]; then
    step "TUI gate (ui-tui: build + test)"
    # build.mjs bundles @hermes/ink from source, but vitest resolves the
    # package entry (packages/hermes-ink/dist), so build it first like CI.
    (cd ui-tui && npm run build:ink && npm run build && npm test)
fi

printf '\n✓ janitor-sync-verify passed against %s\n' "$BASE"
