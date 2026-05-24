#!/bin/bash
# =============================================================================
# migrate-janitor-minimal.sh — Migrate existing Janitor install to minimal model
# =============================================================================
# This script helps users transition from the old full-stack installer
# (Infisical + Honcho + Firecrawl) to the new minimal model where only
# Honcho is fundamental and everything else is an optional skill.
#
# What it does:
#   1. Backs up existing ~/.janitor config
#   2. Detects Infisical shell RC snippets
#   3. Offers to export Infisical secrets to ~/.janitor/.env
#   4. Removes Infisical RC injection (with confirmation)
#   5. Preserves Docker volumes
# =============================================================================

set -euo pipefail

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
BACKUP_DIR="${JANITOR_HOME}/.backup/migration-$(date +%Y%m%d-%H%M%S)"

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

main() {
    echo -e "${BOLD}═══ Janitor Migration: Full Stack → Minimal ═══${NC}"
    echo ""
    log_info "This script migrates your Janitor installation from the old"
    log_info "full-stack model to the new minimal model."
    echo ""
    log_warn "It will NOT delete Docker volumes or secrets."
    echo ""
    read -r -p "Continue? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi

        log_info "Creating backup at ${BACKUP_DIR}..."
    mkdir -p "$BACKUP_DIR"
    cp -r "${JANITOR_HOME}/.env" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "${JANITOR_HOME}/config.yaml" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "${JANITOR_HOME}/SOUL.md" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "${JANITOR_HOME}/honcho.json" "$BACKUP_DIR/" 2>/dev/null || true
    log_ok "Backup created at ${BACKUP_DIR}"

        echo ""
    log_info "Checking shell RC files for Infisical injection..."
    local found_infisical=false
    for rc_file in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
        if [ -f "$rc_file" ] && grep -q "load-infisical-secrets.sh" "$rc_file" 2>/dev/null; then
            log_warn "Found Infisical snippet in ${rc_file}"
            found_infisical=true
            read -r -p "Remove Infisical source line from ${rc_file}? (y/N): " remove_rc
            if [[ "$remove_rc" == "y" || "$remove_rc" == "Y" ]]; then
                grep -v "load-infisical-secrets.sh" "$rc_file" > "${rc_file}.tmp" && mv "${rc_file}.tmp" "$rc_file"
                grep -v "janitor-finalize-deploy.sh" "$rc_file" > "${rc_file}.tmp" && mv "${rc_file}.tmp" "$rc_file"
                log_ok "Cleaned ${rc_file}"
            fi
        fi
    done

    if [ "$found_infisical" = false ]; then
        log_ok "No Infisical RC snippets found."
    fi

        if command -v infisical >/dev/null 2>&1; then
        echo ""
        log_info "Infisical CLI detected."
        read -r -p "Export Infisical secrets to ~/.janitor/.env? (y/N): " export_secrets
        if [[ "$export_secrets" == "y" || "$export_secrets" == "Y" ]]; then
            set +e
            infisical export --path=/janitor --env=prod --format=dotenv > "${JANITOR_HOME}/.env.infisical-export" 2>/dev/null
            EXPORT_RESULT=$?
            set -e
            if [ $EXPORT_RESULT -eq 0 ]; then
                cat "${JANITOR_HOME}/.env.infisical-export" >> "${JANITOR_HOME}/.env"
                rm -f "${JANITOR_HOME}/.env.infisical-export"
                log_ok "Infisical secrets appended to ~/.janitor/.env"
            else
                log_warn "Infisical export failed — secrets remain in vault only."
            fi
        fi
    fi

        echo ""
    echo -e "${GREEN}${BOLD}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║          ✅ Migration Complete                                       ║${NC}"
    echo -e "${GREEN}${BOLD}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log_info "Backup: ${BACKUP_DIR}"
    log_info "Next steps:"
    echo "  • Review your ~/.janitor/.env"
    echo "  • Install optional skills as needed:"
    echo "      bash skills/janitor-vault/scripts/deploy.sh"
    echo "      bash skills/janitor-firecrawl/scripts/deploy.sh"
    echo "  • Restart Janitor: janitor"
    echo ""
}

main "$@"
