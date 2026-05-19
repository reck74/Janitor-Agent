#!/bin/bash
# =============================================================================
# load-infisical-secrets.sh — Load Janitor secrets from Infisical into environment
# =============================================================================
# Sourced by ~/.bashrc / ~/.zshrc on every shell start.
# Exports all secrets from Infisical (/janitor/prod) as environment variables.
# Idempotent — safe to source multiple times.
#
# Usage: source ~/.janitor/scripts/load-infisical-secrets.sh
#
# Exits 0 on success. Exits 1 if Infisical is unavailable.
# Does NOT fall back to ~/.janitor/.env — hard error if Infisical is down.
# =============================================================================

set -euo pipefail

# Default Infisical URL (can be overridden by environment)
INFISICAL_URL="${INFISICAL_URL:-http://localhost:8080}"

# Guard: only run once per session (allow re-source without re-fetching)
if [[ -n "${_JANITOR_INFISICAL_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi

# Guard: must be sourced, not executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: load-infisical-secrets.sh must be sourced, not executed directly." >&2
    echo "Usage: source ~/.janitor/scripts/load-infisical-secrets.sh" >&2
    exit 1
fi

# Check if infisical CLI is available
if ! command -v infisical >/dev/null 2>&1; then
    echo "Error: infisical CLI not found in PATH." >&2
    echo "Install: curl -fsSL https://dl.infisical.com/install.sh | sh" >&2
    exit 1
fi

# Export secrets from Infisical
# --format=dotenv outputs KEY=VALUE per line, suitable for sourcing
set -a
# shellcheck disable=SC2093
if ! infisical export \
    --url "$INFISICAL_URL" \
    --path="/janitor" \
    --env=prod \
    --format=dotenv \
    --silent \
    > /dev/null 2>&1; then
    set +a

    # Check if it's an auth failure vs Infisical being down
    if curl -sf --max-time 5 "${INFISICAL_URL}/api/v1/health" >/dev/null 2>&1; then
        echo "Error: Infisical is reachable but authentication failed or /janitor path is inaccessible." >&2
        echo "Run 'infisical login' or check secret permissions." >&2
    else
        echo "Error: Infisical is not reachable at ${INFISICAL_URL}" >&2
        echo "Ensure the Infisical container is running: docker ps | grep infisical" >&2
    fi
    exit 1
fi
set +a

# Mark as loaded (prevents double-fetching on re-source)
export _JANITOR_INFISICAL_LOADED=1

return 0 2>/dev/null || exit 0