#!/usr/bin/env bash
# ============================================================
# stop.sh
# Detiene Open Design.
#
# NOTA: `tools-dev stop` solo necesita --namespace (default),
# no requiere --daemon-port/--web-port. start sí los usa.
# ============================================================
set -euo pipefail

OD_INSTALL_DIR="${OD_INSTALL_DIR:-${HOME}/open-design}"

if [[ ! -x "${OD_INSTALL_DIR}/node_modules/.bin/tools-dev" ]]; then
  echo "ERROR: tools-dev no encontrado." >&2
  exit 1
fi

cd "${OD_INSTALL_DIR}"
exec ./node_modules/.bin/tools-dev stop
