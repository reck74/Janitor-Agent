#!/bin/bash
# =============================================================================
# load-infisical-secrets.sh — Load Janitor secrets from Infisical into environment
# =============================================================================
# Sourced by ~/.bashrc / ~/.zshrc on every shell start.
# Exports all secrets from Infisical (janitor-secrets / dev) as environment variables.
# Idempotent — safe to source multiple times.
#
# Usage: source ~/.janitor/scripts/load-infisical-secrets.sh
#
# Exits 0 on success. Exits 1 if Infisical is unavailable.
# Does NOT fall back to ~/.janitor/.env — hard error if Infisical is down.
# =============================================================================

set -euo pipefail

INFISICAL_URL="${INFISICAL_URL:-http://localhost:8080}"
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"

if [[ -n "${_JANITOR_INFISICAL_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: load-infisical-secrets.sh must be sourced, not executed directly." >&2
    echo "Usage: source ~/.janitor/scripts/load-infisical-secrets.sh" >&2
    exit 1
fi

ENV_FILE="$JANITOR_HOME/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found." >&2
    exit 1
fi
set -a; source "$ENV_FILE"; set +a

if [ -z "${INFISICAL_ADMIN_EMAIL:-}" ] || [ -z "${INFISICAL_ADMIN_PASSWORD:-}" ]; then
    echo "Error: INFISICAL_ADMIN_EMAIL or INFISICAL_ADMIN_PASSWORD not set in $ENV_FILE." >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq not found in PATH." >&2
    exit 1
fi

if ! curl -sf --max-time 5 "${INFISICAL_URL}/api/status" >/dev/null 2>&1; then
    echo "Error: Infisical is not reachable at ${INFISICAL_URL}." >&2
    echo "Ensure the Infisical container is running: docker ps | grep infisical" >&2
    exit 1
fi

LOGIN_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)
ACCESS_TOKEN=$(echo "$LOGIN_BODY" | jq -r '.accessToken // empty')
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: Infisical login failed." >&2
    exit 1
fi

ORG_RESP=$(curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" "$INFISICAL_URL/api/v1/organization" 2>/dev/null)
ORG_ID=$(echo "$ORG_RESP" | jq -r '.organizations[0].id // empty')
if [ -z "$ORG_ID" ]; then
    echo "Error: No organization found in Infisical." >&2
    exit 1
fi

SELECT_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/select-organization" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{\"organizationId\":\"${ORG_ID}\"}" 2>/dev/null)
ORG_TOKEN=$(echo "$SELECT_BODY" | jq -r '.token // empty')
if [ -z "$ORG_TOKEN" ]; then
    echo "Error: Failed to get organization token." >&2
    exit 1
fi

PROJECTS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" "$INFISICAL_URL/api/v1/projects" 2>/dev/null)
PROJECT_ID=$(echo "$PROJECTS_RESP" | jq -r '.projects[] | select(.name == "janitor-secrets") | .id // empty')
if [ -z "$PROJECT_ID" ]; then
    echo "Error: Project 'janitor-secrets' not found in Infisical." >&2
    exit 1
fi

SECRETS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" \
    "$INFISICAL_URL/api/v4/secrets?projectId=${PROJECT_ID}&environment=dev&secretPath=/" 2>/dev/null)

TMPDIR=$(mktemp -d)
trap "rm -rf '$TMPDIR'" EXIT

if ! echo "$SECRETS_RESP" | jq -r '.secrets[] | "\(.secretKey)=\(.secretValue | rtrimstr("\n"))"' > "$TMPDIR/secrets.dotenv" 2>/dev/null; then
    echo "Error: Failed to parse secrets from Infisical response." >&2
    exit 1
fi

if [ ! -s "$TMPDIR/secrets.dotenv" ]; then
    echo "Error: No secrets found in Infisical project 'janitor-secrets' (dev /)." >&2
    exit 1
fi

set -a
while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
        export "$line"
    fi
done < "$TMPDIR/secrets.dotenv"
set +a

export _JANITOR_INFISICAL_LOADED=1

return 0 2>/dev/null || exit 0
