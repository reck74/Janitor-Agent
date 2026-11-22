#!/usr/bin/env bash
# pair-waha.sh — link the user's WhatsApp to the local janitor-waha (QR or pairing code).
#
# Usage:
#   pair-waha.sh [--qr]                 QR as PNG (default)
#   pair-waha.sh <phone>                pairing code (international, digits only, no +)
#   pair-waha.sh --reset [--qr|<phone>] unlink and recreate the session first (the user
#                                       re-links the phone; only with the user's yes)
#
# The session is created with the NOWEB store enabled: without it WAHA cannot return
# messages and the audit has nothing to read. An already WORKING session is left alone
# unless --reset is given. This script never sends a WhatsApp message.

set -euo pipefail

ROOT="${JANITOR_HOME:-${HERMES_HOME:-$HOME/.janitor}}"
ENV_FILE="${ENV_FILE:-$ROOT/docker/waha.env}"
BASE_URL="${WAHA_BASE_URL:-http://127.0.0.1:3000}"
SESSION_NAME="${WAHA_SESSION:-default}"
QR_OUTPUT="${WAHA_QR_OUTPUT:-$ROOT/docker/waha/qr.png}"
SESSION_CONFIG='{"engine":"NOWEB","noweb":{"store":{"enabled":true,"fullSync":true}}}'

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GRN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YLW}[AVISO]${NC} $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

RESET=0
if [ "${1:-}" = "--reset" ]; then RESET=1; shift; fi
MODE="${1:---qr}"

[ -f "$ENV_FILE" ] || { log_err "No existe $ENV_FILE. Primero: janitor services deploy waha"; exit 1; }
WAHA_API_KEY=$(grep '^WAHA_API_KEY=' "$ENV_FILE" | cut -d= -f2)
[ -n "$WAHA_API_KEY" ] || { log_err "WAHA_API_KEY vacío en $ENV_FILE"; exit 1; }

api() {  # api METHOD PATH [JSON]
    local method="$1" path="$2" data="${3:-}"
    if [ -n "$data" ]; then
        curl -s -X "$method" -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
            -d "$data" "$BASE_URL$path"
    else
        curl -s -X "$method" -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL$path"
    fi
}
session_status() {
    api GET "/api/sessions/$SESSION_NAME" | python3 -c \
        "import sys, json
try: print(json.load(sys.stdin).get('status') or 'ABSENT')
except Exception: print('ABSENT')"
}

if ! curl -s -o /dev/null -w '%{http_code}' -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/health" | grep -q 200; then
    log_err "WAHA no responde en $BASE_URL/health. Mira: janitor services status waha"
    exit 1
fi

STATUS=$(session_status)
if [ "$STATUS" = "WORKING" ] && [ "$RESET" = 0 ]; then
    log_info "La sesión '$SESSION_NAME' ya está vinculada (WORKING). Nada que hacer."
    exit 0
fi

if [ "$RESET" = 1 ] && [ "$STATUS" != "ABSENT" ]; then
    log_warn "Desvinculando y borrando la sesión '$SESSION_NAME' (el teléfono deberá volver a vincularse)."
    api POST "/api/sessions/$SESSION_NAME/stop" >/dev/null || true
    api POST "/api/sessions/$SESSION_NAME/logout" >/dev/null || true
    api DELETE "/api/sessions/$SESSION_NAME" >/dev/null || true
    sleep 2
    STATUS=ABSENT
fi

if [ "$STATUS" = "ABSENT" ]; then
    log_info "Creando la sesión '$SESSION_NAME' (NOWEB con store de mensajes)..."
    api POST "/api/sessions" "{\"name\":\"$SESSION_NAME\",\"config\":$SESSION_CONFIG}" >/dev/null
    sleep 2
fi
if [ "$(session_status)" != "SCAN_QR_CODE" ]; then
    api POST "/api/sessions/$SESSION_NAME/start" >/dev/null || true
fi

log_info "Esperando el estado SCAN_QR_CODE (máx. 15 s)..."
for _ in $(seq 1 15); do
    STATUS=$(session_status)
    [ "$STATUS" = "SCAN_QR_CODE" ] && break
    if [ "$STATUS" = "FAILED" ]; then
        log_err "La sesión quedó en FAILED. Revisa: docker logs janitor-waha --tail 30"
        exit 1
    fi
    sleep 1
done
[ "$STATUS" = "SCAN_QR_CODE" ] || { log_err "La sesión no llegó a SCAN_QR_CODE (estado: $STATUS)."; exit 1; }

if [ "$MODE" = "--qr" ]; then
    mkdir -p "$(dirname "$QR_OUTPUT")"
    api GET "/api/$SESSION_NAME/auth/qr" > "$QR_OUTPUT"
    chmod 600 "$QR_OUTPUT"
    if [ -s "$QR_OUTPUT" ] && head -c 8 "$QR_OUTPUT" | grep -q PNG; then
        log_info "QR guardado en $QR_OUTPUT (caduca en ~60 s; vuelve a ejecutar si expira)."
        echo "  WhatsApp → Ajustes → Dispositivos vinculados → Vincular un dispositivo → escanear."
    else
        log_err "WAHA no devolvió un PNG válido."
        exit 1
    fi
else
    PHONE="$MODE"
    if ! echo "$PHONE" | grep -qE '^[0-9]{10,15}$'; then
        log_err "'$PHONE' no es un número internacional (10-15 dígitos, sin +). Ej.: 573001234567"
        exit 1
    fi
    CODE=$(api POST "/api/$SESSION_NAME/auth/request-code" "{\"phoneNumber\":\"$PHONE\"}" | \
        python3 -c "import sys, json
try: print(json.load(sys.stdin).get('code') or '')
except Exception: print('')")
    [ -n "$CODE" ] || { log_err "WAHA no devolvió código. Revisa: docker logs janitor-waha --tail 30"; exit 1; }
    echo ""
    echo -e "  Código de vinculación: ${YLW}${CODE}${NC}  (caduca en ~60 s)"
    echo "  WhatsApp → Ajustes → Dispositivos vinculados → Vincular con número de teléfono."
fi

echo "  Esperando a que la sesión pase a WORKING (máx. 90 s)..."
for i in $(seq 1 18); do
    STATUS=$(session_status)
    if [ "$STATUS" = "WORKING" ]; then
        log_info "Vinculado (en $((i*5)) s)."
        exit 0
    fi
    if [ "$STATUS" = "FAILED" ]; then
        log_err "La vinculación falló. Revisa: docker logs janitor-waha --since 60s"
        exit 1
    fi
    sleep 5
done
log_warn "Sigue en $STATUS tras 90 s. ¿Escaneó el QR / escribió el código? Si caducó, repite."
exit 1
