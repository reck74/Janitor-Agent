#!/usr/bin/env bash
# ============================================================
# start.sh
# Inicia Open Design con puertos persistentes (mismos siempre).
#
# POR QUÉ:
#   Open Design expone un servidor MCP. Si los puertos cambian
#   en cada reinicio, la configuración del cliente MCP se rompe
#   y hay que reconfigurar el endpoint a mano.
#
# PUERTOS POR DEFECTO:
#   - Daemon: 45351 (API + MCP)
#   - Web:    45343 (interfaz gráfica)
#
# CONFIGURAR EN OTRO LADO:
#   OD_DAEMON_PORT=45351 OD_WEB_PORT=45343 ./start.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OD_INSTALL_DIR="${OD_INSTALL_DIR:-${HOME}/open-design}"

DAEMON_PORT="${OD_DAEMON_PORT:-45351}"
WEB_PORT="${OD_WEB_PORT:-45343}"

if [[ ! -x "${OD_INSTALL_DIR}/node_modules/.bin/tools-dev" ]]; then
  echo "ERROR: tools-dev no encontrado en ${OD_INSTALL_DIR}/node_modules/.bin/" >&2
  echo "¿Ejecutaste pnpm install en el source tree?" >&2
  exit 1
fi

echo "==========================================="
echo " Open Design — Start (puertos persistentes)"
echo "==========================================="
echo "  Daemon: http://127.0.0.1:${DAEMON_PORT}"
echo "  Web:    http://127.0.0.1:${WEB_PORT}"
echo "  MCP:    http://127.0.0.1:${DAEMON_PORT}/mcp"
echo "==========================================="

cd "${OD_INSTALL_DIR}"
exec ./node_modules/.bin/tools-dev start \
  --daemon-port "${DAEMON_PORT}" \
  --web-port    "${WEB_PORT}"
