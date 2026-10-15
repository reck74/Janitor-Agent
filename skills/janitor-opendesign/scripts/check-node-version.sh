#!/usr/bin/env bash
# ============================================================
# check-node-version.sh
# Gate compartido por todos los scripts de janitor-opendesign.
# Garantiza que el Node que resuelve `mise` dentro del source
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
#   - Resuelve `node --version` dentro del source tree (mise-aware).
#   - Compara major versions.
#   - Si hay mismatch → exit 2 con mensaje accionable.
#   - Si no hay mise → usa `node` del PATH y avisa con WARN.
#   - Si no hay `engines.node` → sale 0 (no se puede validar).
#
# USO:
#   source check-node-version.sh   # exit inmediato si falla
#   ./check-node-version.sh        # imprime reporte
# ============================================================
set -euo pipefail

OD_INSTALL_DIR="${OD_INSTALL_DIR:-${HOME}/open-design}"

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

# Resuelve la versión real de node (mise-aware si está disponible)
if command -v mise >/dev/null 2>&1; then
  ACTUAL_VERSION="$(cd "${OD_INSTALL_DIR}" && mise exec -- node --version 2>/dev/null | tr -d 'v' || true)"
else
  ACTUAL_VERSION="$(node --version 2>/dev/null | tr -d 'v' || true)"
fi

ACTUAL_MAJOR="$(echo "${ACTUAL_VERSION}" | grep -oE '[0-9]+' | head -1 || true)"

if [[ -z "${ACTUAL_MAJOR}" ]]; then
  echo "WARN: no se pudo resolver node --version. Gate omitido." >&2
  exit 0
fi

if [[ "${ACTUAL_MAJOR}" != "${EXPECTED_MAJOR}" ]]; then
  cat >&2 <<EOF
ERROR: open-design exige Node ${EXPECTED_SPEC} pero el entorno resuelve Node ${ACTUAL_VERSION}.

Esto CRASHEA la instalación:
  - pnpm install compila better-sqlite3 con node-gyp.
  - Si el major de Node no coincide, el binario falla con
    segfault en uv_kill (corrupcion del bridge PRIME GPU).
  - Consecuencia: pantalla congelada, sddm restart necesario.

CORRECCIÓN (elige UNA):
  1. Crear override local solo para este proyecto:
       cd ${OD_INSTALL_DIR}
       echo '[tools]' > .mise.toml
       echo 'node = "${EXPECTED_MAJOR}.18.1"' >> .mise.toml
       echo 'pnpm = "10.33.2"' >> .mise.toml
       rm -rf node_modules ~/.cache/pnpm
       pnpm install --frozen-lockfile

  2. Cambiar el Node global de mise:
       mise global node@${EXPECTED_MAJOR}.18.1

  3. Prefijar el PATH para esta sesión:
       export PATH="\$HOME/.local/share/mise/installs/node/${EXPECTED_MAJOR}.18.1/bin:\$PATH"

Este script aborta con exit 2 para que las skills no procedan
con un Node incompatible.
EOF
  exit 2
fi

echo "OK: Node ${ACTUAL_VERSION} coincide con engines.node (${EXPECTED_SPEC})." >&2
exit 0
