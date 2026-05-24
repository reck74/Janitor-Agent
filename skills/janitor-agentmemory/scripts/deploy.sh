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

log_info "Installing AgentMemory via npm..."

if ! command -v npm >/dev/null 2>&1; then
    log_warn "npm not found — skipping AgentMemory installation."
    exit 0
fi

set +e
npm install -g @agentmemory/agentmemory 2>&1
NPM_RESULT=$?
set -e

if [ $NPM_RESULT -ne 0 ]; then
    log_fail "npm install -g @agentmemory/agentmemory failed"
    exit 1
fi
log_ok "AgentMemory npm package installed"

NPM_GLOBAL_PREFIX="$(npm prefix -g 2>/dev/null)"
AGENTMEMORY_BIN="${NPM_GLOBAL_PREFIX}/bin/agentmemory"

if [ ! -x "$AGENTMEMORY_BIN" ]; then
    log_warn "agentmemory binary not found at ${AGENTMEMORY_BIN}"
    exit 0
fi

    SVC_DIR="${HOME}/.config/systemd/user"
SVC_FILE="${SVC_DIR}/janitor-agentmemory.service"

mkdir -p "$SVC_DIR"

cat > "$SVC_FILE" << EOF
[Unit]
Description=Janitor AgentMemory Server
After=network.target

[Service]
Type=simple
Environment="PATH=${NPM_GLOBAL_PREFIX}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="NODE_PATH=${NPM_GLOBAL_PREFIX}/lib/node_modules"
ExecStart=${AGENTMEMORY_BIN} --no-engine
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

log_ok "Service file written to ${SVC_FILE}"

set +e
systemctl --user daemon-reload 2>/dev/null
SYSTEMD_RELOAD=$?
set -e

if [ $SYSTEMD_RELOAD -eq 0 ]; then
    systemctl --user enable janitor-agentmemory.service 2>/dev/null
    log_ok "janitor-agentmemory.service enabled"
else
    log_warn "systemd not available — skipping service enable."
fi
