#!/usr/bin/env bash
# migrate-janitor-v0.20.1.sh
#
# Migrates a Janitor install from config schema v33 (v0.20.0 / Hermes
# v2026.8.x) to schema v34 (v0.20.1+janitor.1). Backwards-compatible and
# idempotent: a second run on an already-migrated install is a no-op.
#
# Behavior:
#   --dry-run    : report what would change; do NOT back up or mutate.
#   exit 0       : migration succeeded (or no-op — already at v34).
#   exit 1       : no config found at the resolved home.
#   exit 3       : strict YAML parse failed after the guaranteed backup.
#
# Home precedence: $JANITOR_HOME > $HERMES_HOME > $HOME/.janitor
# (the first non-empty wins; an unset or empty env var falls through).
#
# The script creates a timestamped backup BEFORE invoking the migration
# wrapper, but only when the schema-diff actually needs to run. An
# already-migrated install (no v33 inputs and a v34 _config_version stamp)
# exits 0 without creating a new backup — a second run is a true no-op.
#
# Schema diff is delegated to the merged
# ``hermes_cli.update_cmd._run_migrate_config_fresh`` wrapper, which uses
# freshly-reloaded config modules. This script does NOT shell out to
# ``python -m hermes_cli.config migrate`` (that command does not exist).
#
# The script NEVER touches Docker volumes or ``$JANITOR_HOME/secrets/``.

set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

# Resolve home: JANITOR_HOME > HERMES_HOME > HOME/.janitor
if [ -n "${JANITOR_HOME:-}" ]; then
    HOME_DIR="$JANITOR_HOME"
    # The merged wrappers read via hermes_cli.config.get_config_path() →
    # get_hermes_home() → $HERMES_HOME. Mirror JANITOR_HOME into HERMES_HOME
    # so the wrapper resolves to the same path the script picked.
    export HERMES_HOME="$JANITOR_HOME"
elif [ -n "${HERMES_HOME:-}" ]; then
    HOME_DIR="$HERMES_HOME"
else
    HOME_DIR="${HOME:-}/.janitor"
fi

CONFIG="$HOME_DIR/config.yaml"

if [ ! -f "$CONFIG" ]; then
    echo "No config at $CONFIG — nothing to migrate" >&2
    exit 1
fi

# Determine UTC timestamp for the backup filename.
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$CONFIG.bak.$TIMESTAMP"

# Read raw + display version. The Janitor fork stamps its PEP 440 version
# (`0.20.1+janitor.1`) in `hermes_cli/__init__.py`; the user-facing form
# replaces the first `+` with `-` (`0.20.1-janitor.1`). We hardcode the
# strings here so the script is self-contained — the alternative (parsing
# `hermes_cli/__init__.py`) couples this script to that file's layout.
RAW_VERSION="0.20.1+janitor.1"
DISPLAY_VERSION="0.20.1-janitor.1"

# Detect v33 inputs from the raw file (no YAML parsing yet — only string
# matches). v33 detection:
#   - raw _config_version: 33
#   - real v34 input under display.personality (non-empty)
#   - real v34 input under agent.system_prompt (non-empty)
# Obsolete root `personality.selected` is intentionally NOT consulted.
# Also treat a missing or stale (<v34) _config_version as "needs the v34
# stamp" so a brand-new minimal config picks up the current schema.
RAW_CONFIG_VER=$(grep -m1 '^_config_version:' "$CONFIG" 2>/dev/null \
    | awk '{print $2}' || echo "")
HAS_V34_INPUTS=0
if awk '
    /^display:[[:space:]]*$/ { in_display=1; next }
    /^[^[:space:]]/ { in_display=0 }
    in_display && /^[[:space:]]+personality:[[:space:]]+[a-zA-Z]/ { found=1 }
    END { exit !found }
' "$CONFIG" 2>/dev/null; then
    HAS_V34_INPUTS=1
fi
if [ "$HAS_V34_INPUTS" = "0" ]; then
    if awk '
        /^agent:[[:space:]]*$/ { in_agent=1; next }
        /^[^[:space:]]/ { in_agent=0 }
        in_agent && /^[[:space:]]+system_prompt:[[:space:]]+[^[:space:]]/ { found=1 }
        END { exit !found }
    ' "$CONFIG" 2>/dev/null; then
        HAS_V34_INPUTS=1
    fi
fi

NEEDS_MIGRATION=0
if [ "$RAW_CONFIG_VER" = "33" ]; then
    NEEDS_MIGRATION=1
elif [ "$HAS_V34_INPUTS" = "1" ]; then
    NEEDS_MIGRATION=1
elif [ -z "$RAW_CONFIG_VER" ] || [ "$RAW_CONFIG_VER" -lt "34" ] 2>/dev/null; then
    NEEDS_MIGRATION=1
fi

# --dry-run short-circuits BEFORE any backup or mutation.
if [ "$DRY_RUN" = "1" ]; then
    echo "Dry run: would migrate $CONFIG"
    echo "  current raw _config_version: ${RAW_CONFIG_VER:-<missing>}"
    if [ "$NEEDS_MIGRATION" = "1" ]; then
        echo "  target: v34 (migration needed)"
    else
        echo "  target: v34 (already migrated; no-op)"
    fi
    echo "Raw version: $RAW_VERSION"
    echo "Display version: $DISPLAY_VERSION"
    exit 0
fi

# Idempotency: if migration is not needed, exit 0 without creating a backup.
if [ "$NEEDS_MIGRATION" = "0" ]; then
    echo "Config already at v34 — nothing to migrate."
    echo
    echo "Raw version: $RAW_VERSION"
    echo "Display version: $DISPLAY_VERSION"
    exit 0
fi

# Migration is needed — back up before any mutation.
cp "$CONFIG" "$BACKUP"
echo "Backed up: $BACKUP"

# Locate a Python interpreter that has both PyYAML and the merged
# hermes_cli.update_cmd wrappers. Prefer the project-local .venv.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif [ -x "$REPO_ROOT/venv/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/venv/bin/python3"
else
    PYTHON_BIN="python3"
fi
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"

# Strict-parse YAML. A parse failure aborts with exit 3, leaves the live
# file byte-identical, and prints rollback guidance naming the backup.
set +e
"$PYTHON_BIN" -c "
import sys
try:
    import yaml
except ImportError:
    print('PyYAML is required for migration; install with: pip install pyyaml', file=sys.stderr)
    sys.exit(2)
try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f'Config at {sys.argv[1]} is not a YAML mapping', file=sys.stderr)
        sys.exit(2)
except yaml.YAMLError as e:
    print(f'Strict YAML parse failed: {e}', file=sys.stderr)
    sys.exit(3)
" "$CONFIG"
PARSE_RC=$?
set -e

if [ "$PARSE_RC" != "0" ]; then
    if [ "$PARSE_RC" = "3" ]; then
        echo
        echo "Migration aborted: config could not be parsed."
        echo "Your live config is byte-identical to: $BACKUP"
        echo "To rollback: cp $BACKUP $CONFIG"
        exit 3
    fi
    exit "$PARSE_RC"
fi

# Invoke the fresh wrappers in an isolated Python subprocess so a partially-
# broken venv doesn't bleed into the running session.
set +e
"$PYTHON_BIN" - "$CONFIG" <<'PYEOF'
import sys

try:
    from hermes_cli.update_cmd import (
        _run_config_check_fresh,
        _run_migrate_config_fresh,
    )
except Exception as exc:
    print(f"Failed to import fresh config wrappers: {exc}", file=sys.stderr)
    sys.exit(2)

try:
    current, latest = _run_config_check_fresh()
except Exception as exc:
    print(f"Config version check failed: {exc}", file=sys.stderr)
    sys.exit(2)

if not (isinstance(current, int) and isinstance(latest, int)):
    print(
        f"Config version check returned non-integer values: "
        f"{current!r}, {latest!r}",
        file=sys.stderr,
    )
    sys.exit(2)

if current == latest:
    print(f"Config already at v{latest}; no migration needed.")
    sys.exit(0)

if current > latest:
    print(
        f"Config version {current} > latest {latest}; "
        f"leaving untouched (downgrade detected)."
    )
    sys.exit(0)

try:
    results = _run_migrate_config_fresh(interactive=False, quiet=True)
except Exception as exc:
    print(f"Config migration raised: {exc}", file=sys.stderr)
    sys.exit(3)

for warning in (results.get("warnings", []) if isinstance(results, dict) else []) or []:
    if warning:
        print(f"  WARNING: {warning}", file=sys.stderr)
PYEOF
PY_RC=$?
set -e

if [ "$PY_RC" != "0" ]; then
    echo
    echo "Migration failed (exit $PY_RC)."
    echo "Your live config is byte-identical to: $BACKUP"
    echo "To rollback: cp $BACKUP $CONFIG"
    exit "$PY_RC"
fi

# Fresh post-check after a supported migration (best-effort).
set +e
"$PYTHON_BIN" - <<'PYEOF'
import sys
try:
    from hermes_cli.update_cmd import _run_config_check_fresh
    cur, lat = _run_config_check_fresh()
    if isinstance(cur, int) and isinstance(lat, int) and cur < lat:
        print(
            f"WARNING: config still at v{cur} (target v{lat}) after migration."
        )
except Exception:
    pass
PYEOF
set -e

echo
echo "Raw version: $RAW_VERSION"
echo "Display version: $DISPLAY_VERSION"
echo
echo "To rollback: cp $BACKUP $CONFIG"
exit 0