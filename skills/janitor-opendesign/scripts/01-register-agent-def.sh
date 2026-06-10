#!/usr/bin/env bash
# ============================================================
# 01-register-agent-def.sh
# Copia la definición del agente Janitor a la copia local
# del source tree de Open Design.
#
# Ubicación esperada del script (relativa a la skill):
#   integrations/janitor-agent/01-register-agent-def.sh
# ============================================================
set -euo pipefail

OD_SOURCE_DIR="${OD_SOURCE_DIR:-${HOME}/open-design}"
JANITOR_DEF_SRC="$(dirname "$0")/agent-defs/janitor.ts"
JANITOR_DEF_DST="${OD_SOURCE_DIR}/apps/daemon/src/runtimes/defs/janitor.ts"

if [[ ! -d "${OD_SOURCE_DIR}" ]]; then
  echo "ERROR: OD_SOURCE_DIR no existe: ${OD_SOURCE_DIR}" >&2
  echo "Ejecuta primero opendesign-install o especifica OD_SOURCE_DIR." >&2
  exit 1
fi

if [[ ! -f "${JANITOR_DEF_SRC}" ]]; then
  echo "ERROR: Fuente no encontrada: ${JANITOR_DEF_SRC}" >&2
  exit 1
fi

echo "[janitor-integration] Copiando definición del agente a ${JANITOR_DEF_DST}"
mkdir -p "$(dirname "${JANITOR_DEF_DST}")"
cp "${JANITOR_DEF_SRC}" "${JANITOR_DEF_DST}"
echo "[janitor-integration] OK — agente registrado: janitor"
