#!/bin/bash
# =============================================================================
# verify-vault.sh — TDD assertion script for Infisical vault bootstrap.
# =============================================================================
# Must be run AFTER vault-bootstrap.sh.
# Exits 0 if all assertions pass, exits 1 with descriptive message on failure.
set -euo pipefail

# ── Path conventions ─────────────────────────────────────────────────────────
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
ENV_FILE="$JANITOR_HOME/.env"
INFISICAL_URL="${INFISICAL_URL:-http://localhost:8080}"

# ── jq check ──────────────────────────────────────────────────────────────────
if ! command -v jq >/dev/null 2>&1; then
    if [ -x "$HOME/bin/jq" ]; then
        export PATH="$HOME/bin:$PATH"
    else
        echo "FATAL: jq not found. Install with: curl -sL https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64 -o ~/bin/jq && chmod +x ~/bin/jq"
        exit 1
    fi
fi

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
PASS=0
FAIL=0

assert_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
assert_fail() { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL + 1)); }

# ── Load env ──────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "FATAL: $ENV_FILE not found"
    exit 1
fi
set -a; source "$ENV_FILE"; set +a

if [ -z "${INFISICAL_ADMIN_EMAIL:-}" ] || [ -z "${INFISICAL_ADMIN_PASSWORD:-}" ]; then
    echo "FATAL: INFISICAL_ADMIN_EMAIL or INFISICAL_ADMIN_PASSWORD not set in $ENV_FILE"
    exit 1
fi

# ── Step 1: Healthcheck ──────────────────────────────────────────────────────
echo "=== Step 1: Infisical healthcheck ==="
if curl -sf "$INFISICAL_URL/api/status" >/dev/null 2>&1; then
    assert_pass "Infisical is healthy"
else
    assert_fail "Infisical is not responding at $INFISICAL_URL/api/status"
fi

# ── Step 2: Authenticate (3-step flow) ────────────────────────────────────────
echo "=== Step 2: Authenticate ==="

# Step 2a: Login
LOGIN_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)

if [ -z "$LOGIN_BODY" ]; then
    assert_fail "Login failed — empty response"
    echo "FATAL: Cannot proceed without authentication"
    exit 1
fi

ACCESS_TOKEN=$(echo "$LOGIN_BODY" | jq -r '.accessToken // empty')
if [ -z "$ACCESS_TOKEN" ]; then
    assert_fail "Login response missing accessToken"
    echo "FATAL: Cannot proceed without access token"
    exit 1
fi
assert_pass "Login succeeded"

# Step 2b: Get organization ID
ORG_RESP=$(curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" "$INFISICAL_URL/api/v1/organization" 2>/dev/null)
ORG_ID=$(echo "$ORG_RESP" | jq -r '.organizations[0].id // empty')
if [ -z "$ORG_ID" ]; then
    assert_fail "No organization found"
    echo "FATAL: Cannot proceed without organization"
    exit 1
fi
assert_pass "Organization found: ${ORG_ID:0:8}..."

# Step 2c: Select organization (get org-scoped token)
SELECT_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/select-organization" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{\"organizationId\":\"${ORG_ID}\"}" 2>/dev/null)

ORG_TOKEN=$(echo "$SELECT_BODY" | jq -r '.token // empty')
if [ -z "$ORG_TOKEN" ]; then
    assert_fail "select-organization failed — no org-scoped token"
    echo "FATAL: Cannot proceed without org-scoped token"
    exit 1
fi
assert_pass "Org-scoped token acquired"

# ── Step 3: Verify project exists ────────────────────────────────────────────
echo "=== Step 3: Verify project 'janitor-secrets' exists ==="

PROJECTS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" "$INFISICAL_URL/api/v1/projects" 2>/dev/null)
PROJECT_COUNT=$(echo "$PROJECTS_RESP" | jq -r '.projects | length')

JANITOR_PROJECT=$(echo "$PROJECTS_RESP" | jq -r '.projects[] | select(.name == "janitor-secrets")')
PROJECT_ID=$(echo "$JANITOR_PROJECT" | jq -r '.id // empty')

if [ -z "$PROJECT_ID" ]; then
    assert_fail "Project 'janitor-secrets' not found (found $PROJECT_COUNT projects)"
else
    assert_pass "Project 'janitor-secrets' found (id: ${PROJECT_ID:0:8}...)"
fi

# ── Step 4: Verify at least 5 secrets exist ───────────────────────────────────
echo "=== Step 4: Verify secrets exist ==="

if [ -z "$PROJECT_ID" ]; then
    assert_fail "Cannot verify secrets — project not found"
else
    SECRETS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" \
        "$INFISICAL_URL/api/v3/secrets/raw?workspaceId=${PROJECT_ID}&environment=dev&secretPath=/" 2>/dev/null)
    SECRET_COUNT=$(echo "$SECRETS_RESP" | jq -r '.secrets | length')

    if [ "$SECRET_COUNT" -ge 5 ]; then
        assert_pass "Found $SECRET_COUNT secrets (>= 5 required)"
    else
        assert_fail "Found $SECRET_COUNT secrets (need >= 5)"
    fi
fi

# ── Step 5: Verify FIRECRAWL_POSTGRES_DB value matches .env ──────────────────
echo "=== Step 5: Verify secret value integrity ==="

if [ -z "$PROJECT_ID" ]; then
    assert_fail "Cannot verify secret values — project not found"
else
    SECRET_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" \
        "$INFISICAL_URL/api/v3/secrets/raw/FIRECRAWL_POSTGRES_DB?workspaceId=${PROJECT_ID}&environment=dev&secretPath=/" 2>/dev/null)

    VAULT_VALUE=$(echo "$SECRET_RESP" | jq -r '.secret.secretValue // empty')
    ENV_VALUE="${FIRECRAWL_POSTGRES_DB:-}"

    if [ -z "$VAULT_VALUE" ]; then
        assert_fail "Secret FIRECRAWL_POSTGRES_DB not found in vault"
    elif [ "$VAULT_VALUE" = "$ENV_VALUE" ]; then
        assert_pass "FIRECRAWL_POSTGRES_DB value matches .env"
    else
        assert_fail "FIRECRAWL_POSTGRES_DB value mismatch (vault: ${VAULT_VALUE:0:3}..., env: ${ENV_VALUE:0:3}...)"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0