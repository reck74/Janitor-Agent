#!/usr/bin/env bash
# n8n-auth.sh — Obtain a fresh n8n session cookie for API calls
# n8n's /api/v1/ requires X-N8N-API-KEY which is masked on creation.
# Workaround: use /rest/ endpoints with cookie-based auth.
#
# Source (skill-bundled): skills/devops/janitor-n8n/scripts/n8n-auth.sh
# Runtime copy:           ~/.janitor/docker/n8n-auth.sh
#
# Usage: source ~/.janitor/docker/n8n-auth.sh
# Output: Sets $N8N_COOKIE_JAR with a valid cookie file path
#         Cookie expires in 7 days (n8n default)
set -euo pipefail

# Load credentials from ~/.janitor/.env if not already in environment
JANITOR_ENV="${JANITOR_HOME:-$HOME/.janitor}/.env"
if [[ -z "${N8N_USER_PASSWORD:-}" && -f "$JANITOR_ENV" ]]; then
    while IFS='=' read -r key val; do
        [[ "$key" =~ ^N8N_ ]] && export "$key=$val"
    done < "$JANITOR_ENV"
fi

N8N_URL="${N8N_API_URL:-http://127.0.0.1:5678}"
N8N_EMAIL="${N8N_USER_EMAIL:-janitor@example.com}"
N8N_PASS="${N8N_USER_PASSWORD:?N8N_USER_PASSWORD not set in env or ~/.janitor/.env}"
COOKIE_JAR="/tmp/n8n-session-$$.txt"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q '^janitor-n8n$'; then
    echo "ERROR: janitor-n8n container not running" >&2
    return 1 2>/dev/null || exit 1
fi

# Login
RESP=$(curl -s -c "$COOKIE_JAR" -o /dev/null -w "%{http_code}" \
    -X POST "${N8N_URL}/rest/login" \
    -H "Content-Type: application/json" \
    -d "{\"emailOrLdapLoginId\":\"${N8N_EMAIL}\",\"password\":\"${N8N_PASS}\"}" 2>/dev/null)

if [[ "$RESP" != "200" ]]; then
    echo "ERROR: n8n login failed (HTTP ${RESP})" >&2
    rm -f "$COOKIE_JAR"
    return 1 2>/dev/null || exit 1
fi

# Verify cookie exists
if ! grep -q "n8n-auth" "$COOKIE_JAR" 2>/dev/null; then
    echo "ERROR: n8n cookie not set" >&2
    rm -f "$COOKIE_JAR"
    return 1 2>/dev/null || exit 1
fi

export N8N_COOKIE_JAR="$COOKIE_JAR"
echo "$COOKIE_JAR"
