#!/bin/bash
# =============================================================================
# vault-bootstrap.sh — Bootstrap Infisical vault with Janitor secrets.
# =============================================================================
# Authenticates against Infisical, creates "janitor-secrets" project,
# and writes all API keys from ~/.janitor/.env as individual secrets.
set -euo pipefail

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
JANITOR_SOURCE_DIR="${JANITOR_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$JANITOR_HOME/.env"
INFISICAL_URL="${INFISICAL_URL:-http://localhost:8080}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

TMPDIR=""
cleanup() {
    if [ -n "$TMPDIR" ] && [ -d "$TMPDIR" ]; then
        rm -rf "$TMPDIR"
    fi
}
trap cleanup EXIT
TMPDIR=$(mktemp -d)

# ── Prerequisites ─────────────────────────────────────────────────────────────
if ! command -v curl >/dev/null 2>&1; then
    log_fail "curl not found"; exit 1
fi

if command -v jq >/dev/null 2>&1; then
    JQ="jq"
elif [ -x "$HOME/bin/jq" ]; then
    JQ="$HOME/bin/jq"
    export PATH="$HOME/bin:$PATH"
else
    log_fail "jq not found. Install: curl -sL https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64 -o ~/bin/jq && chmod +x ~/bin/jq"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    log_fail "$ENV_FILE not found"; exit 1
fi

set -a; source "$ENV_FILE"; set +a

if [ -z "${INFISICAL_ADMIN_EMAIL:-}" ] || [ -z "${INFISICAL_ADMIN_PASSWORD:-}" ]; then
    log_fail "INFISICAL_ADMIN_EMAIL or INFISICAL_ADMIN_PASSWORD not set in $ENV_FILE"
    exit 1
fi

# ── Healthcheck ───────────────────────────────────────────────────────────────
log_info "Checking Infisical health..."
if ! curl -sf "$INFISICAL_URL/api/status" >/dev/null 2>&1; then
    log_fail "Infisical not responding at $INFISICAL_URL/api/status"
    exit 1
fi
log_ok "Infisical is healthy"

# ── Block A: Authentication (3-step flow) ──────────────────────────────────────
log_info "Authenticating against Infisical..."

LOGIN_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)

ACCESS_TOKEN=$(echo "$LOGIN_BODY" | jq -r '.accessToken // empty')
if [ -z "$ACCESS_TOKEN" ]; then
    log_fail "Login failed — no accessToken in response"
    echo "$LOGIN_BODY" | head -3
    exit 1
fi
log_ok "Login succeeded"

ORG_RESP=$(curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" "$INFISICAL_URL/api/v1/organization" 2>/dev/null)
ORG_ID=$(echo "$ORG_RESP" | jq -r '.organizations[0].id // empty')
if [ -z "$ORG_ID" ]; then
    log_fail "No organization found"
    exit 1
fi
log_ok "Organization: ${ORG_ID:0:8}..."

SELECT_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/select-organization" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{\"organizationId\":\"${ORG_ID}\"}" 2>/dev/null)

ORG_TOKEN=$(echo "$SELECT_BODY" | jq -r '.token // empty')
if [ -z "$ORG_TOKEN" ]; then
    log_fail "select-organization failed — no org-scoped token"
    exit 1
fi
log_ok "Org-scoped token acquired"

# ── Block C: Create project ───────────────────────────────────────────────────
log_info "Creating project 'janitor-secrets'..."

PROJECT_ID=""
PROJECTS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" "$INFISICAL_URL/api/v1/projects" 2>/dev/null)
EXISTING=$(echo "$PROJECTS_RESP" | jq -r '.projects[] | select(.name == "janitor-secrets") | .id // empty')

if [ -n "$EXISTING" ]; then
    PROJECT_ID="$EXISTING"
    log_ok "Project 'janitor-secrets' already exists (id: ${PROJECT_ID:0:8}...)"
else
    CREATE_RESP=$(curl -sf -w "\n%{http_code}" -X POST "$INFISICAL_URL/api/v1/projects" \
        -H "Authorization: Bearer ${ORG_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"projectName":"janitor-secrets"}' 2>/dev/null)
    CREATE_STATUS=$(echo "$CREATE_RESP" | tail -1)
    CREATE_BODY=$(echo "$CREATE_RESP" | sed '$d')

    if [ "$CREATE_STATUS" = "200" ] || [ "$CREATE_STATUS" = "201" ]; then
        PROJECT_ID=$(echo "$CREATE_BODY" | jq -r '.project.id // empty')
        log_ok "Project 'janitor-secrets' created (id: ${PROJECT_ID:0:8}...)"
    else
        log_fail "Failed to create project (HTTP $CREATE_STATUS)"
        echo "$CREATE_BODY" | head -5
        exit 1
    fi
fi

if [ -z "$PROJECT_ID" ]; then
    log_fail "Could not determine project ID"
    exit 1
fi

# ── Block D: Discover secret-writing endpoint ─────────────────────────────────
log_info "Discovering secret-writing endpoint..."

SECRETS_ENDPOINT=""
SECRETS_FORMAT=""

PROBE_RESP=$(curl -sf -w "\n%{http_code}" -X POST "$INFISICAL_URL/api/v4/secrets/JANITOR_BOOTSTRAP_PROBE" \
    -H "Authorization: Bearer ${ORG_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"projectId\":\"${PROJECT_ID}\",\"environment\":\"dev\",\"secretPath\":\"/\",\"secretValue\":\"ok\",\"type\":\"shared\"}" 2>/dev/null)
PROBE_STATUS=$(echo "$PROBE_RESP" | tail -1)

if [ "$PROBE_STATUS" = "200" ] || [ "$PROBE_STATUS" = "201" ]; then
    SECRETS_ENDPOINT="/api/v4/secrets"
    SECRETS_FORMAT="v4"
    log_ok "Secret endpoint: POST /api/v4/secrets/:name (v4 plaintext)"
else
    log_fail "Secret endpoint discovery failed (HTTP $PROBE_STATUS)"
    echo "$PROBE_RESP" | sed '$d' | head -5
    echo "FATAL: No working secret-writing endpoint found. Aborting."
    exit 1
fi

# ── Block E: Write secrets ────────────────────────────────────────────────────
log_info "Writing secrets to vault..."

declare -A SECRET_MAP
SECRET_MAP[OPENAI_API_KEY]="${OPENAI_API_KEY:-}"
SECRET_MAP[MINIMAX_API_KEY]="${MINIMAX_API_KEY:-}"
SECRET_MAP[LLM_ANTHROPIC_API_KEY]="${LLM_ANTHROPIC_API_KEY:-}"
SECRET_MAP[LLM_OPENAI_API_KEY]="${LLM_OPENAI_API_KEY:-}"
SECRET_MAP[FIRECRAWL_POSTGRES_USER]="${FIRECRAWL_POSTGRES_USER:-}"
SECRET_MAP[FIRECRAWL_POSTGRES_PASSWORD]="${FIRECRAWL_POSTGRES_PASSWORD:-}"
SECRET_MAP[FIRECRAWL_POSTGRES_DB]="${FIRECRAWL_POSTGRES_DB:-}"
SECRET_MAP[HONCHO_POSTGRES_USER]="${HONCHO_POSTGRES_USER:-}"
SECRET_MAP[HONCHO_POSTGRES_PASSWORD]="${HONCHO_POSTGRES_PASSWORD:-}"
SECRET_MAP[HONCHO_POSTGRES_DB]="${HONCHO_POSTGRES_DB:-}"
SECRET_MAP[INFISICAL_POSTGRES_USER]="${INFISICAL_POSTGRES_USER:-}"
SECRET_MAP[INFISICAL_POSTGRES_PASSWORD]="${INFISICAL_POSTGRES_PASSWORD:-}"
SECRET_MAP[INFISICAL_POSTGRES_DB]="${INFISICAL_POSTGRES_DB:-}"
SECRET_MAP[INFISICAL_ENCRYPTION_KEY]="${INFISICAL_ENCRYPTION_KEY:-}"
SECRET_MAP[INFISICAL_AUTH_SECRET]="${INFISICAL_AUTH_SECRET:-}"

OK_COUNT=0
FAIL_COUNT=0

for KEY in "${!SECRET_MAP[@]}"; do
    VALUE="${SECRET_MAP[$KEY]}"
    if [ -z "$VALUE" ]; then
        log_warn "Skipping $KEY — empty value in .env"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    ESCAPED_VALUE=$(echo "$VALUE" | jq -Rs .)

    RESP=$(curl -sf -w "\n%{http_code}" -X POST "$INFISICAL_URL${SECRETS_ENDPOINT}/${KEY}" \
        -H "Authorization: Bearer ${ORG_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"projectId\":\"${PROJECT_ID}\",\"environment\":\"dev\",\"secretPath\":\"/\",\"secretValue\":${ESCAPED_VALUE},\"type\":\"shared\"}" 2>/dev/null)
    STATUS=$(echo "$RESP" | tail -1)

    if [ "$STATUS" = "200" ] || [ "$STATUS" = "201" ]; then
        log_ok "Volcando $KEY... OK"
        OK_COUNT=$((OK_COUNT + 1))
    else
        log_fail "Volcando $KEY... FAIL (HTTP $STATUS)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# ── Block F: Cleanup probe secret ────────────────────────────────────────────
log_info "Cleaning up probe secret..."
curl -sf -X DELETE "$INFISICAL_URL/api/v4/secrets/JANITOR_BOOTSTRAP_PROBE" \
    -H "Authorization: Bearer ${ORG_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"projectId\":\"${PROJECT_ID}\",\"environment\":\"dev\",\"secretPath\":\"/\"}" >/dev/null 2>&1 || true

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══ Vault Bootstrap Summary ═══${NC}"
echo -e "  Project: janitor-secrets (${PROJECT_ID:0:8}...)"
echo -e "  Secrets written: $OK_COUNT"
echo -e "  Secrets failed:  $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    log_fail "Some secrets failed to write"
    exit 1
fi

log_ok "Vault bootstrap complete — all secrets written"
exit 0