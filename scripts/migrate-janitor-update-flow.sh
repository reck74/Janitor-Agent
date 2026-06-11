#!/usr/bin/env bash
# migrate-janitor-update-flow.sh
# Post-refactor migration helper for the janitor update flow change.
#
# What this script does:
#  1. Verifies the new janitor_update_core.py exists in the install dir.
#  2. If the local janitor-core has diverged branches (3 ahead / 30 behind,
#     for example), offers a one-line recovery command.
#  3. No-op on installs that are already current.
#
# This script is safe to run repeatedly. It never touches ~/.janitor/
# configuration files or skill bundles.

set -euo pipefail

JANITOR_CORE="${JANITOR_CORE:-$HOME/.janitor/janitor-core}"

echo "Janitor update-flow migration helper"
echo " install dir: $JANITOR_CORE"
echo

if [ ! -d "$JANITOR_CORE/.git" ]; then
  echo "✗ $JANITOR_CORE is not a git checkout."
  echo "  Reinstall with: curl -fsSL https://github.com/reck74/Janitor-Agent/raw/main/scripts/janitor-install.sh | bash"
  exit 1
fi

cd "$JANITOR_CORE"

# Check whether the new core file is present.
if [ -f "$JANITOR_CORE/janitor_update_core.py" ]; then
  echo "✓ janitor_update_core.py present — this install already has the new update flow."
  echo
  echo "If you previously hit the 'Fast-forward not possible' error, your local branch"
  echo "has diverged from origin/main. Run:"
  echo
  echo "  cd $JANITOR_CORE && git fetch origin && git reset --hard origin/main"
  echo
  echo "This discards any local commits ahead of origin/main. If you have uncommitted"
  echo "work you want to keep, stash it first:"
  echo
  echo "  cd $JANITOR_CORE && git stash push --include-untracked -m 'pre-reset-save'"
  echo
  exit 0
fi

# Old install — explain that the next janitor update will fetch the new code.
echo "⚠ janitor_update_core.py NOT present."
echo "  This install predates the update-flow refactor."
echo
echo "Run 'janitor update' to pull the new flow into place. If your local"
echo "branch has diverged from origin/main (e.g. you have un-pushed local"
echo "commits), the new flow will automatically run:"
echo
echo "  git reset --hard origin/main"
echo
echo "after printing a 'Fast-forward not possible' warning."
echo
echo "Your local un-pushed commits will be discarded. Back them up first"
echo "if you want to keep them:"
echo
echo "  cd $JANITOR_CORE && git log --oneline origin/main..HEAD"
echo "  cd $JANITOR_CORE && git stash push --include-untracked -m 'pre-update-save'"
