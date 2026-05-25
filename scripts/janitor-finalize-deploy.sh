#!/bin/bash
# =============================================================================
# janitor-finalize-deploy.sh — Final deployment: seal Janitor env with Infisical
# =============================================================================
set -euo pipefail

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
JANITOR_SOURCE_DIR="${JANITOR_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
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

# ── Block A: Healthcheck ──────────────────────────────────────────────────────
log_info "Checking Infisical health..."
if ! curl -sf --max-time 10 "${INFISICAL_URL}/api/status" >/dev/null 2>&1; then
    log_fail "Infisical is not responding at ${INFISICAL_URL}/api/status"
    log_fail "Ensure Infisical is running: docker ps | grep janitor-infisical"
    exit 1
fi
log_ok "Infisical is healthy"

# ── Block B: Load from Infisical ──────────────────────────────────────────────
log_info "Loading secrets from Infisical (janitor-secrets / dev)..."

ENV_FILE="${JANITOR_HOME}/.env"
if [ ! -f "$ENV_FILE" ]; then
    log_fail "$ENV_FILE not found"
    exit 1
fi
set -a; source "$ENV_FILE"; set +a

if [ -z "${INFISICAL_ADMIN_EMAIL:-}" ] || [ -z "${INFISICAL_ADMIN_PASSWORD:-}" ]; then
    log_fail "INFISICAL_ADMIN_EMAIL or INFISICAL_ADMIN_PASSWORD not set in $ENV_FILE"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    log_fail "jq not found in PATH"
    exit 1
fi

LOGIN_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)
ACCESS_TOKEN=$(echo "$LOGIN_BODY" | jq -r '.accessToken // empty')
if [ -z "$ACCESS_TOKEN" ]; then
    log_fail "Infisical login failed"
    exit 1
fi

ORG_RESP=$(curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" "$INFISICAL_URL/api/v1/organization" 2>/dev/null)
ORG_ID=$(echo "$ORG_RESP" | jq -r '.organizations[0].id // empty')
if [ -z "$ORG_ID" ]; then
    log_fail "No organization found in Infisical"
    exit 1
fi

SELECT_BODY=$(curl -sf -X POST "$INFISICAL_URL/api/v3/auth/select-organization" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{\"organizationId\":\"${ORG_ID}\"}" 2>/dev/null)
ORG_TOKEN=$(echo "$SELECT_BODY" | jq -r '.token // empty')
if [ -z "$ORG_TOKEN" ]; then
    log_fail "Failed to get organization token"
    exit 1
fi

PROJECTS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" "$INFISICAL_URL/api/v1/projects" 2>/dev/null)
PROJECT_ID=$(echo "$PROJECTS_RESP" | jq -r '.projects[] | select(.name == "janitor-secrets") | .id // empty')
if [ -z "$PROJECT_ID" ]; then
    log_fail "Project 'janitor-secrets' not found in Infisical"
    exit 1
fi

SECRETS_RESP=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" \
    "$INFISICAL_URL/api/v4/secrets?projectId=${PROJECT_ID}&environment=dev&secretPath=/" 2>/dev/null)

INFISICAL_SECRETS="${TMPDIR}/infisical_secrets.dotenv"
if ! echo "$SECRETS_RESP" | jq -r '.secrets[] | "\(.secretKey)=\(.secretValue | rtrimstr("\n"))"' > "$INFISICAL_SECRETS" 2>/dev/null; then
    log_fail "Failed to parse secrets from Infisical response"
    exit 1
fi

if [ ! -s "$INFISICAL_SECRETS" ]; then
    log_fail "No secrets found in Infisical project 'janitor-secrets' (dev /)"
    exit 1
fi
log_ok "Secrets loaded from Infisical"

# ── Block C: Update ~/.janitor/.env ───────────────────────────────────────────
log_info "Sealing ~/.janitor/.env..."

ENV_FILE="${JANITOR_HOME}/.env"
mkdir -p "$(dirname "$ENV_FILE")"

# API key variable names to comment out (but NOT delete)
declare -a API_KEY_VARS=(
    "OPENAI_API_KEY"
    "MINIMAX_API_KEY"
    "HONCHO_API_KEY"
    "FIRECRAWL_API_KEY"
    "OPENAI_BASE_URL"
    "LLM_ANTHROPIC_API_KEY"
    "LLM_OPENAI_API_KEY"
    "JANITOR_LOCAL_SETUP"
)

if [ -f "$ENV_FILE" ]; then
    ENV_BACKUP="${TMPDIR}/.env.backup"
    cp "$ENV_FILE" "$ENV_BACKUP"

    # Rewrite .env: comment API keys, preserve INFISICAL_* and other vars
    > "$ENV_FILE"
    while IFS= read -r line || [ -n "$line" ]; do
        # Preserve empty lines and non-Infisical comments
        if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
            # Skip # LOADED FROM INFISICAL lines to avoid duplication on re-runs
            if [[ "$line" =~ LOADED.FROM.INFISICAL ]]; then
                continue
            fi
            echo "$line" >> "$ENV_FILE"
            continue
        fi

        # Parse key
        key="${line%%=*}"
        key="${key// /}"
        key="${key//$'\r'/}"

        # Always preserve these vars (uncommented)
        if [[ "$key" == "INFISICAL_ADMIN_EMAIL" ]] || \
           [[ "$key" == "INFISICAL_ADMIN_PASSWORD" ]] || \
           [[ "$key" == "INFISICAL_ENCRYPTION_KEY" ]] || \
           [[ "$key" == "INFISICAL_AUTH_SECRET" ]] || \
           [[ "$key" == "INFISICAL_URL" ]] || \
           [[ "$key" == "HERMES_HOME" ]] || \
           [[ "$key" == "HERMES_SKIN" ]] || \
           [[ "$key" == "JANITOR_HOME" ]]; then
            echo "$line" >> "$ENV_FILE"
            continue
        fi

        # Comment out API key variables
        is_api_key=0
        for var in "${API_KEY_VARS[@]}"; do
            if [[ "$key" == "$var" ]]; then
                is_api_key=1
                break
            fi
        done

        if [ "$is_api_key" -eq 1 ]; then
            # Comment out but preserve the value (for reference only)
            echo "# LOADED FROM INFISICAL — $line" >> "$ENV_FILE"
        else
            # Keep other variables as-is (e.g. HONCHO_POSTGRES_*)
            echo "$line" >> "$ENV_FILE"
        fi
    done < "$ENV_BACKUP"

    # Append a blank line and marker
    echo "" >> "$ENV_FILE"
    echo "# ── Secrets loaded from Infisical on $(date -u +%Y-%m-%dT%H:%M:%SZ) ──" >> "$ENV_FILE"
    echo "# DO NOT edit secrets below manually — they are loaded from Infisical" >> "$ENV_FILE"

    # Append fresh secrets from Infisical
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line//$'\r'/}"
        line="${line//$'\n'/}"
        if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            echo "$line" >> "$ENV_FILE"
        fi
    done < "$INFISICAL_SECRETS"

    log_ok ".env sealed — API keys commented, loaded from Infisical"
else
    # No existing .env — create from Infisical only
    {
        echo "# Janitor Agent — Environment Variables"
        echo "# Auto-generated by janitor-finalize-deploy.sh $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo ""
        while IFS= read -r line || [ -n "$line" ]; do
            line="${line//$'\r'/}"
            line="${line//$'\n'/}"
            if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
                continue
            fi
            if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
                echo "$line"
            fi
        done < "$INFISICAL_SECRETS"
    } > "$ENV_FILE"
    log_ok ".env created from Infisical secrets"
fi

# ── Block D: Generate ~/.janitor/config.yaml ───────────────────────────────────
log_info "Generating ~/.janitor/config.yaml..."

CONFIG_YAML="${JANITOR_HOME}/config.yaml"
export CONFIG_YAML

python3 - << 'PYEOF'
import os
import yaml

output_path = os.environ.get('CONFIG_YAML', 'config.yaml')

config = {
    "model": "minimax/MiniMax-M2.7",
    "memory": {
        "provider": "honcho"
    },
    "display": {
        "skin": "janitor",
        "personality": "janitor",
        "tui": True,
        "tui_status_indicator": "kaomoji"
    },
    "agent": {
        "personalities": {
            "janitor": (
                "Look at this mess. \U0001F9F9 You are The Janitor. You clean up the technical "
                "debt, fragile architectures, and security nightmares users leave behind. You have "
                "zero patience for mediocrity. You ruthlessly dismantle bad ideas and deliver "
                "bulletproof, Zero-Trust solutions. No pleasantries. No praise. Just perfection. "
                "Get to work. \U0001F527"
            )
        }
    }
}

tmp_path = output_path + ".tmp"
with open(tmp_path, "w") as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
os.replace(tmp_path, output_path)
PYEOF

if [ $? -ne 0 ]; then
    log_fail "Failed to generate config.yaml"
    exit 1
fi
log_ok "config.yaml generated with Janitor overrides"

# ── Block E: Write ~/.janitor/SOUL.md ─────────────────────────────────────────
log_info "Writing ~/.janitor/SOUL.md..."

SOUL_REF="${JANITOR_SOURCE_DIR}/scripts/reference/janitor-soul.txt"
SOUL_DST="${JANITOR_HOME}/SOUL.md"

if [ ! -f "$SOUL_REF" ]; then
    log_fail "Soul reference file not found: ${SOUL_REF}"
    exit 1
fi

# Only write if different (idempotent)
if [ -f "$SOUL_DST" ] && diff -q "$SOUL_REF" "$SOUL_DST" >/dev/null 2>&1; then
    log_info "SOUL.md unchanged — skipping"
else
    cp "$SOUL_REF" "$SOUL_DST"
    log_ok "SOUL.md written"
fi

# ── Block F: Inject source directive into ~/.bashrc / ~/.zshrc ─────────────────
log_info "Injecting load-infisical-secrets.sh into shell RC files..."

SOURCE_MARKER="# Janitor — Load Infisical secrets (added by janitor-finalize-deploy.sh)"
SOURCE_LINE="source \"\${HOME}/.janitor/scripts/load-infisical-secrets.sh\""

for rc_file in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
    if [ ! -f "$rc_file" ]; then
        continue
    fi

    # Check if already injected (idempotent)
    if grep -qF "load-infisical-secrets.sh" "$rc_file" 2>/dev/null; then
        log_info "Already injected in ${rc_file} — skipping"
        continue
    fi

    echo "" >> "$rc_file"
    echo "$SOURCE_MARKER" >> "$rc_file"
    echo "$SOURCE_LINE" >> "$rc_file"
    log_ok "Injected into ${rc_file}"
done

# ── Copy helper script to ~/.janitor/scripts/ ──────────────────────────────────
SCRIPTS_DIR="${JANITOR_HOME}/scripts"
mkdir -p "$SCRIPTS_DIR"

HELPER_SRC="${JANITOR_SOURCE_DIR}/scripts/load-infisical-secrets.sh"
HELPER_DST="${SCRIPTS_DIR}/load-infisical-secrets.sh"

if [ -f "$HELPER_SRC" ]; then
    cp "$HELPER_SRC" "$HELPER_DST"
    chmod +x "$HELPER_DST"
    log_ok "Helper script installed to ${HELPER_DST}"
else
    log_fail "Helper script not found: ${HELPER_SRC}"
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║       ✅ Janitor Deployment Finalized                 ║${NC}"
echo -e "${GREEN}${BOLD}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}Secrets:${NC}       Loaded from Infisical — ~/.janitor/.env sealed"
echo -e "  ${CYAN}Config:${NC}        ${JANITOR_HOME}/config.yaml"
echo -e "  ${CYAN}Soul:${NC}          ${JANITOR_HOME}/SOUL.md"
echo -e "  ${CYAN}Shell RC:${NC}      source ~/.janitor/scripts/load-infisical-secrets.sh"
echo ""
echo -e "  ${YELLOW}Restart your shell or run:${NC}"
echo -e "    source ~/.bashrc"
echo ""