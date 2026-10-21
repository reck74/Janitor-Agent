#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

log_info "Installing Playwright browser automation..."

set +e
if command -v uv >/dev/null 2>&1; then
    uv pip install playwright 2>/dev/null
    uv run playwright install --with-deps chromium < /dev/tty
    RESULT=$?
elif command -v pip >/dev/null 2>&1; then
    pip install playwright 2>/dev/null
    python3 -m playwright install --with-deps chromium < /dev/tty
    RESULT=$?
else
    log_fail "No uv or pip found. Cannot install Playwright."
    exit 1
fi
set -e

if [ $RESULT -ne 0 ]; then
    log_warn "Playwright install had issues — continuing anyway."
    log_info "You can retry later with: uv run playwright install --with-deps chromium"
else
    log_ok "Playwright + Chromium installed"
fi
