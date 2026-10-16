#!/usr/bin/env bash
# ============================================================
# status.sh
# Verifica que Open Design esté corriendo en los puertos
# persistentes esperados.
# ============================================================
set -euo pipefail

DAEMON_PORT="${OD_DAEMON_PORT:-45351}"
WEB_PORT="${OD_WEB_PORT:-45343}"

echo "Open Design — Status (puertos persistentes)"
echo "--------------------------------------------"

# Keep diagnostics bounded even if a service accepts connections but stalls.
http_status() {
  local code
  if code=$(curl --connect-timeout 2 --max-time 5 -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null); then
    printf '%s' "$code"
  else
    printf '000'
  fi
}
EXIT_CODE=0

# Daemon
DAEMON_HEALTH=$(http_status "http://127.0.0.1:${DAEMON_PORT}/api/health")
if [[ "${DAEMON_HEALTH}" == "200" ]]; then
  VERSION=$(curl --connect-timeout 2 --max-time 5 -s "http://127.0.0.1:${DAEMON_PORT}/api/health" | grep -oE '"version":"[^"]*"' || echo "unknown")
  echo "  Daemon  http://127.0.0.1:${DAEMON_PORT}  OK  (${VERSION})"
else
  EXIT_CODE=1
  echo "  Daemon  http://127.0.0.1:${DAEMON_PORT}  DOWN  (HTTP ${DAEMON_HEALTH})"
fi

# Web
WEB_CODE=$(http_status "http://127.0.0.1:${WEB_PORT}/")
if [[ "${WEB_CODE}" == "200" ]]; then
  echo "  Web     http://127.0.0.1:${WEB_PORT}  OK"
else
  EXIT_CODE=1
  echo "  Web     http://127.0.0.1:${WEB_PORT}  DOWN  (HTTP ${WEB_CODE})"
fi

# MCP endpoint (lo que configura el cliente MCP externo)
if [[ "${DAEMON_HEALTH}" == "200" ]]; then
  echo ""
  echo "  Configuración MCP stdio para clientes externos:"
  echo "    http://127.0.0.1:${DAEMON_PORT}/api/mcp/install-info"
fi

exit "${EXIT_CODE}"
