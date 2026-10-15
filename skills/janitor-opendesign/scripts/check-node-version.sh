#!/usr/bin/env bash
# ============================================================
# check-node-version.sh
# Gate compartido por todos los scripts de janitor-opendesign.
# Garantiza que el Node ejecutado desde PATH dentro del source
# tree de Open Design coincide con `engines.node` del package.json.
#
# POR QUÉ EXISTE (2026-08-19):
#   open-design v0.18.2 exige Node ~24. Si el mise global del
#   usuario está en Node 26, `pnpm install` segfaultea durante
#   la compilación de better-sqlite3 con node-gyp. El segfault
#   corrompe el bridge PRIME NVIDIA↔AMD y deja el framebuffer
#   del laptop tieso. Solo se recupera con `sddm restart` y se
#   pierde toda la sesión.
#
# COMPORTAMIENTO:
#   - Lee `engines.node` del package.json del source tree.
#   - Resuelve el mismo `node` de PATH que ejecutarán pnpm y tools-dev.
#   - Compara major versions.
#   - Si hay mismatch → exit 2 con mensaje accionable.
#   - No valida un `mise exec` distinto del entorno que usará el comando.
#   - Si no hay `engines.node` → sale 0 (no se puede validar).
#
# USO:
#   source check-node-version.sh   # exit inmediato si falla
#   ./check-node-version.sh        # imprime reporte
# ============================================================
set -euo pipefail

OD_INSTALL_DIR="${OD_INSTALL_DIR:-${OD_SOURCE_DIR:-${HOME}/open-design}}"

if [[ ! -f "${OD_INSTALL_DIR}/package.json" ]]; then
  echo "WARN: ${OD_INSTALL_DIR}/package.json no existe. Gate de versión omitido." >&2
  exit 0
fi

EXPECTED_SPEC="$(grep -oP '"node":\s*"\K[^"]+' "${OD_INSTALL_DIR}/package.json" | head -1 || true)"

if [[ -z "${EXPECTED_SPEC}" ]]; then
  echo "WARN: ${OD_INSTALL_DIR}/package.json no declara engines.node. Gate omitido." >&2
  exit 0
fi

# Extrae el primer major version del spec (~24, ^24, >=24, 24.x, etc.)
EXPECTED_MAJOR="$(echo "${EXPECTED_SPEC}" | grep -oE '[0-9]+' | head -1 || true)"

if [[ -z "${EXPECTED_MAJOR}" ]]; then
  echo "WARN: no se pudo parsear engines.node=\"${EXPECTED_SPEC}\". Gate omitido." >&2
  exit 0
fi

# Check the executable used by the child commands, from their working directory.
# A separate `mise exec` may report Node 24 while PATH still executes Node 26.
ACTUAL_VERSION="$(cd "${OD_INSTALL_DIR}" && node --version 2>/dev/null | tr -d 'v' || true)"

ACTUAL_MAJOR="$(echo "${ACTUAL_VERSION}" | grep -oE '[0-9]+' | head -1 || true)"

if [[ -z "${ACTUAL_MAJOR}" ]]; then
  echo "ERROR: no se pudo resolver node --version. Activa el Node requerido antes de continuar." >&2
  exit 2
fi

if [[ "${ACTUAL_MAJOR}" != "${EXPECTED_MAJOR}" ]]; then
  cat >&2 <<EOF
ERROR: open-design exige Node ${EXPECTED_SPEC} pero el entorno resuelve Node ${ACTUAL_VERSION}.

Las dependencias nativas deben instalarse con el mismo Node compatible
que ejecutará Open Design. Activa el toolchain del proyecto en esta sesión:

  cd ${OD_INSTALL_DIR}
  mise exec -- bash /ruta/a/janitor-opendesign/scripts/safe-pnpm-install.sh install --frozen-lockfile

También puedes anteponer al PATH el binario Node ${EXPECTED_MAJOR} instalado.
No hace falta cambiar el Node global ni crear un segundo archivo mise.

Este script aborta con exit 2 para que las skills no procedan
con un Node incompatible.
EOF
  exit 2
fi

echo "OK: Node ${ACTUAL_VERSION} coincide con engines.node (${EXPECTED_SPEC})." >&2
exit 0
