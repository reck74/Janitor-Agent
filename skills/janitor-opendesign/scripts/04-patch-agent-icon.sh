#!/usr/bin/env bash
# ============================================================
# 04-patch-agent-icon.sh
# Agrega janitor a ICON_EXT (como 'png') y lo MANTIENE FUERA
# de MONO_ICONS en AgentIcon.tsx.
#
# Idempotente: corre limpio si ya está parcheado.
#
# BUG HISTORICO: la primera versión tenía un if/else al revés —
# el else se saltaba la inserción de ICON_EXT cuando el archivo
# no tenía la entrada. La detección ahora distingue "ya está
# parcheado" vs "no está, agregar".
# ============================================================
set -euo pipefail

OD_SOURCE_DIR="${OD_SOURCE_DIR:-${HOME}/open-design}"
AGENT_ICON="${OD_SOURCE_DIR}/apps/web/src/components/AgentIcon.tsx"

if [[ ! -f "${AGENT_ICON}" ]]; then
  echo "ERROR: AgentIcon.tsx no encontrado: ${AGENT_ICON}" >&2
  exit 1
fi

# --- ICON_EXT: agregar janitor: 'png' después de hermes ---
if grep -q "^  janitor: 'png'" "${AGENT_ICON}"; then
  echo "[janitor-integration] ICON_EXT ya tiene janitor: 'png' — skip"
else
  echo "[janitor-integration] Agregando janitor: 'png' a ICON_EXT"
  # Insertar después de la línea "  hermes: 'svg',"
  # El sed usa 'a' (append after match) con un patrón único:
  # "  hermes: 'svg'," solo aparece una vez en el archivo.
  sed -i "/^  hermes: 'svg',$/a\\  janitor: 'png'," "${AGENT_ICON}"
fi

# --- MONO_ICONS: si está dentro, sacarlo (queremos <img>, no mask) ---
if grep -q "^  'janitor',$" "${AGENT_ICON}"; then
  echo "[janitor-integration] Quitando janitor de MONO_ICONS"
  sed -i "/^  'janitor',$/d" "${AGENT_ICON}"
else
  echo "[janitor-integration] MONO_ICONS ya no contiene janitor — skip"
fi

echo "[janitor-integration] OK — AgentIcon.tsx parcheado para janitor"