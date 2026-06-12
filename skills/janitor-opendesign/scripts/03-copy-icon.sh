#!/usr/bin/env bash
# ============================================================
# 03-copy-icon.sh
# Copia el icono PNG de Janitor al public/agent-icons/
# de la copia local de Open Design.
#
# Ubicación esperada del script (relativa a la skill):
#   skills/janitor-opendesign/scripts/03-copy-icon.sh
#
# El icono es una ilustración PNG a color (310x311) del personaje
# "The Janitor" — se renderiza como <img> en lugar de CSS mask.
# Estilo consistente con Devin, Aider, Trae CLI (los otros PNGs).
# ============================================================
set -euo pipefail

OD_SOURCE_DIR="${OD_SOURCE_DIR:-${HOME}/open-design}"
ICON_DST="${OD_SOURCE_DIR}/apps/web/public/agent-icons/janitor.png"

# Buscar el PNG en multiples paths (orden de preferencia):
#   1. Junto al script (skills/janitor-opendesign/icon/)
#   2. Raiz del proyecto de la skill (un nivel arriba de skills/)
SCRIPT_DIR_ABS="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR_ABS}/../.." && pwd)"

ICON_SRC=""
for candidate in \
    "${SCRIPT_DIR_ABS}/icon/janitor.png" \
    "${SKILL_ROOT}/janitor.png"; do
  if [[ -f "${candidate}" ]]; then
    ICON_SRC="${candidate}"
    break
  fi
done

if [[ -z "${ICON_SRC}" ]]; then
  echo "ERROR: janitor.png no encontrado en ninguno de los paths esperados:" >&2
  echo "  - ${SCRIPT_DIR_ABS}/icon/janitor.png" >&2
  echo "  - ${SKILL_ROOT}/janitor.png" >&2
  exit 1
fi

echo "[janitor-integration] Copiando icono a ${ICON_DST}"
cp "${ICON_SRC}" "${ICON_DST}"
echo "[janitor-integration] OK — icono instalado ($(wc -c < "${ICON_DST}") bytes)"