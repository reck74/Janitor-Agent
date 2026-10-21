#!/usr/bin/env bash
# ============================================================
# integrate-janitor.sh
# Registra Janitor como agente de coding en el source tree
# local de Open Design y arranca el stack con puertos
# persistentes.
#
# USO:
#   ./integrate-janitor.sh              # solo registra (idempotente)
#   ./integrate-janitor.sh start        # registra + arranca stack
#   ./integrate-janitor.sh stop         # detiene con puertos correctos
#   ./integrate-janitor.sh status       # health check
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OD_SOURCE_DIR="${OD_SOURCE_DIR:-${HOME}/open-design}"

DAEMON_PORT="${OD_DAEMON_PORT:-45351}"
WEB_PORT="${OD_WEB_PORT:-45343}"
export OD_DAEMON_PORT OD_WEB_PORT

ACTION="${1:-register}"

echo "=========================================="
echo " Janitor Agent Integration — Open Design"
echo "=========================================="
echo "  OD_SOURCE_DIR: ${OD_SOURCE_DIR}"
echo "  Puertos fijos: daemon=${DAEMON_PORT}, web=${WEB_PORT}"
echo ""

if [[ ! -d "${OD_SOURCE_DIR}" ]]; then
  echo "ERROR: OD_SOURCE_DIR no existe: ${OD_SOURCE_DIR}" >&2
  echo "Ejecuta primero opendesign-install." >&2
  exit 1
fi

if ! command -v janitor &>/dev/null; then
  echo "ERROR: 'janitor' no está en PATH." >&2
  exit 1
fi

# --- Acciones start / stop / status delegan a scripts dedicados ---
case "${ACTION}" in
  start)
    bash "${SCRIPT_DIR}/01-register-agent-def.sh"
    bash "${SCRIPT_DIR}/02-patch-registry.sh"
    bash "${SCRIPT_DIR}/03-copy-icon.sh"
    bash "${SCRIPT_DIR}/04-patch-agent-icon.sh"
    bash "${SCRIPT_DIR}/start.sh"
    exit 0
    ;;
  stop)
    bash "${SCRIPT_DIR}/stop.sh"
    exit 0
    ;;
  status)
    bash "${SCRIPT_DIR}/status.sh"
    exit 0
    ;;
  register)
    echo "(modo: solo registrar, sin arrancar)"
    echo ""
    ;;
  *)
    echo "Acción desconocida: ${ACTION}" >&2
    echo "Uso: $0 [register|start|stop|status]" >&2
    exit 1
    ;;
esac

# --- Modo register: ejecuta los 4 pasos ---
JANITOR_VERSION=$(janitor --version 2>/dev/null | head -1 || echo "desconocida")
echo "  Janitor: ${JANITOR_VERSION}"
echo ""

echo "==> Paso 1/4: Registrar definición del agente"
bash "${SCRIPT_DIR}/01-register-agent-def.sh"
echo ""

echo "==> Paso 2/4: Patchear registry.ts"
bash "${SCRIPT_DIR}/02-patch-registry.sh"
echo ""

echo "==> Paso 3/4: Copiar icono PNG"
bash "${SCRIPT_DIR}/03-copy-icon.sh"
echo ""

echo "==> Paso 4/4: Patcher AgentIcon.tsx"
bash "${SCRIPT_DIR}/04-patch-agent-icon.sh"
echo ""

echo "=========================================="
echo " Integración completa!"
echo ""
echo " Próximos pasos:"
echo "   ${SCRIPT_DIR}/integrate-janitor.sh start    # arrancar con puertos fijos"
echo "   ${SCRIPT_DIR}/integrate-janitor.sh status   # health check"
echo "   ${SCRIPT_DIR}/integrate-janitor.sh stop     # detener"
echo ""
echo " Endpoint MCP persistente:"
echo "   http://127.0.0.1:${DAEMON_PORT}/mcp"
echo "=========================================="
