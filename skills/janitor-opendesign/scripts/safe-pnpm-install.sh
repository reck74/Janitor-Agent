#!/usr/bin/env bash
# ============================================================
# safe-pnpm-install.sh
# Wrapper defensivo para `pnpm install` en Open Design.
#
# POR QUÉ EXISTE (2026-08-19):
#   Un `pnpm install --frozen-lockfile` con Node equivocado
#   segfaulteó (SIGSEGV en uv_kill) y el crash de GPU client
#   desincronizó el bridge PRIME NVIDIA↔AMD (pantalla congelada).
#
# DEFENSAS:
#   A. Gate de versión Node (check-node-version.sh) — aborta
#      ANTES de instalar si el major no coincide con engines.node.
#   B. systemd-run con CPUQuota=70% MemoryMax=6G — un crash o
#      runaway no puede tumbar la sesión gráfica.
#   C. Si pnpm falla: purga ~/.cache/pnpm (queda corrupto tras
#      segfault, vimos el coredump de 89MB) y reporta exit real.
#
# NOTA: NO se hace backup de node_modules — es reproducible desde
# pnpm-lock.yaml y un rsync de 2.1GB a /tmp (tmpfs = RAM) puede
# inducir el OOM que este script previene.
#
# USO:
#   bash scripts/safe-pnpm-install.sh install --frozen-lockfile
#   bash scripts/safe-pnpm-install.sh install
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OD_INSTALL_DIR="${OD_INSTALL_DIR:-${OD_SOURCE_DIR:-${HOME}/open-design}}"

# A) Gate de versión Node — exit 2 si hay mismatch.
bash "${SCRIPT_DIR}/check-node-version.sh"

if [[ ! -f "${OD_INSTALL_DIR}/package.json" ]]; then
  echo "ERROR: ${OD_INSTALL_DIR}/package.json no existe." >&2
  exit 1
fi

cd "${OD_INSTALL_DIR}"

# B) Caps de recursos si systemd-run está disponible.
# Nota: en --scope solo valen propiedades de resource control;
# Restart= no aplica (es de unidades service, no scopes).
PNPM_CMD=(pnpm)
if command -v systemd-run >/dev/null 2>&1; then
  PNPM_CMD=(systemd-run --user --scope --quiet
    --property=CPUQuota=70%
    --property=MemoryMax=6G
    --unit="janitor-opendesign-pnpm-$$"
    pnpm)
fi

echo "==> Ejecutando: ${PNPM_CMD[*]} $*"
set +e
"${PNPM_CMD[@]}" "$@"
EXIT_CODE=$?
set -e

# C) Cleanup si falla + reporte honesto del exit code real.
if [[ ${EXIT_CODE} -ne 0 ]]; then
  echo "ERROR: pnpm falló con exit ${EXIT_CODE}." >&2
  if [[ -d "${HOME}/.cache/pnpm" ]]; then
    echo "==> Purgando ~/.cache/pnpm (puede quedar corrupto tras el fallo)"
    rm -rf "${HOME}/.cache/pnpm"
  fi
  echo ""
  echo "Diagnóstico:"
  echo "  - Segfault de Node: coredumpctl list --no-pager | tail -5"
  echo "  - Versión de Node:  bash ${SCRIPT_DIR}/check-node-version.sh"
  echo "  - Red:              curl -sI https://registry.npmjs.org/ | head -1"
  echo ""
  echo "Reintento limpio:"
  echo "  rm -rf ${OD_INSTALL_DIR}/node_modules"
  echo "  bash ${SCRIPT_DIR}/safe-pnpm-install.sh install --frozen-lockfile"
fi
exit "${EXIT_CODE}"
