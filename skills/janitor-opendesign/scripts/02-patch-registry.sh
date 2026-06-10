#!/usr/bin/env bash
# ============================================================
# 02-patch-registry.sh
# Agrega janitorAgentDef a BASE_AGENT_DEFS en registry.ts.
#
# PATTERN FIJO: el script anterior usaba un sed glob que matcheaba
# la línea del import en vez de la línea del array, causando que
# janitor quedara importado PERO no incluido en BASE_AGENT_DEFS.
#
# Solución: buscar la línea exacta del array que contiene
# "hermesAgentDef," y agregar janitor DESPUÉS de esa línea.
# ============================================================
set -euo pipefail

OD_SOURCE_DIR="${OD_SOURCE_DIR:-${HOME}/open-design}"
REGISTRY="${OD_SOURCE_DIR}/apps/daemon/src/runtimes/registry.ts"

if [[ ! -f "${REGISTRY}" ]]; then
  echo "ERROR: registry.ts no encontrado: ${REGISTRY}" >&2
  exit 1
fi

# --- Idempotencia: si janitor ya está importado, skip ---
if grep -q "from './defs/janitor.js'" "${REGISTRY}"; then
  echo "[janitor-integration] registry ya tiene import de janitor — skip"
else
  echo "[janitor-integration] Agregando import de janitor en registry.ts"
  sed -i "s|import { hermesAgentDef } from './defs/hermes.js';|import { hermesAgentDef } from './defs/hermes.js';\nimport { janitorAgentDef } from './defs/janitor.js';|" "${REGISTRY}"
fi

# --- Idempotencia: si janitor ya está en BASE_AGENT_DEFS, skip ---
if grep -q "janitorAgentDef," "${REGISTRY}"; then
  echo "[janitor-integration] BASE_AGENT_DEFS ya incluye janitorAgentDef — skip"
else
  echo "[janitor-integration] Agregando janitorAgentDef a BASE_AGENT_DEFS"
  # Buscar la línea EXACTA del array que tiene hermesAgentDef,
  # no la del import. Usamos un patrón más preciso:
  # "  hermesAgentDef," (con 2 espacios de indentación)
  sed -i '/^  hermesAgentDef,$/a\  janitorAgentDef,' "${REGISTRY}"
fi

echo "[janitor-integration] OK — registry parcheado para janitor"