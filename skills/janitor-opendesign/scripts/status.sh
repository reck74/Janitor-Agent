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

# Daemon
DAEMON_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${DAEMON_PORT}/api/health" 2>/dev/null || echo "000")
if [[ "${DAEMON_HEALTH}" == "200" ]]; then
  VERSION=$(curl -s "http://127.0.0.1:${DAEMON_PORT}/api/health" | grep -oE '"version":"[^"]*"' || echo "unknown")
  echo "  Daemon  http://127.0.0.1:${DAEMON_PORT}  OK  (${VERSION})"
else
  echo "  Daemon  http://127.0.0.1:${DAEMON_PORT}  DOWN  (HTTP ${DAEMON_HEALTH})"
fi

# Web
WEB_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${WEB_PORT}/" 2>/dev/null || echo "000")
if [[ "${WEB_CODE}" == "200" ]]; then
  echo "  Web     http://127.0.0.1:${WEB_PORT}  OK"
else
  echo "  Web     http://127.0.0.1:${WEB_PORT}  DOWN  (HTTP ${WEB_CODE})"
fi

# MCP endpoint (lo que configura el cliente MCP externo)
if [[ "${DAEMON_HEALTH}" == "200" ]]; then
  echo ""
  echo "  MCP endpoint para clientes externos:"
  echo "    http://127.0.0.1:${DAEMON_PORT}/mcp"
fi
