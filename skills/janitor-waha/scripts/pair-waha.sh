#!/usr/bin/env bash
# pair-waha.sh — automate WhatsApp session creation + pairing for janitor-waha
# Bundled with the janitor-waha skill.
#
# Usage:
#   pair-waha.sh <phone-in-international-format>   # pairing code (no QR scan needed)
#   pair-waha.sh --qr                              # QR code as PNG (private temporary file)
#   pair-waha.sh                                   # QR (default if no args)
#
# Examples:
#   pair-waha.sh 573001234567       # pair via 8-digit code (no QR)
#   pair-waha.sh --qr               # generate a private QR PNG; print its path
#
# After running with a phone number, type the printed 8-char code in WhatsApp on your
# phone (Settings → Linked Devices → Link with phone number).

set -euo pipefail
# Enter this installation's PM Python; load profile secrets without shell evaluation.
if [[ "${JANITOR_SERVICE_ENV:-}" != "1" ]]; then
    skill_source="$(readlink -f "${BASH_SOURCE[0]}")"
    skill_root="$(cd "$(dirname "$skill_source")/../../.." && pwd)"
    launcher="$skill_root/scripts/janitor"
    [[ -x "$launcher" ]] || launcher="$(command -v janitor || true)"
    [[ -n "$launcher" && -x "$launcher" ]] || { echo "Install/repair Janitor before deploying this skill." >&2; exit 1; }
    export JANITOR_HOME="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
    exec "$launcher" --run-module janitor_ext.optional_deploy "$skill_source" "$@"
fi
umask 077

ENV_FILE="${ENV_FILE:-${HERMES_HOME:-$HOME/.janitor}/docker/waha.env}"
BASE_URL="${WAHA_BASE_URL:-http://127.0.0.1:3000}"
SESSION_NAME="${WAHA_SESSION:-default}"
[[ "$SESSION_NAME" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Invalid WAHA session name" >&2; exit 2; }
QR_OUTPUT="${WAHA_QR_OUTPUT:-}"

# Colors
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GRN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# === Preflight ===

[ -f "$ENV_FILE" ] || { log_err "waha.env no encontrado en $ENV_FILE. Run deploy.sh first."; exit 1; }
WAHA_API_KEY=$(grep '^WAHA_API_KEY=' "$ENV_FILE" | cut -d= -f2)
[ -n "$WAHA_API_KEY" ] || { log_err "WAHA_API_KEY empty in $ENV_FILE"; exit 1; }

if ! curl -sS --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}' -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/health" | grep -q 200; then
    log_err "WAHA no responde en $BASE_URL/health. Stack levantado?"
    log_err "Solución: docker ps --filter name=janitor-waha"
    exit 1
fi

# Reuse live sessions. A repeated pairing command must never log out a healthy device.
EXISTING_STATUS=$(curl -fsS --connect-timeout 5 --max-time 15 -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions?all=true" | \
    "$JANITOR_SERVICE_PYTHON" -c "import sys, json; ss=json.load(sys.stdin); print(next((s.get('status', 'UNKNOWN') for s in ss if s['name']=='$SESSION_NAME'), 'ABSENT'))")

CREATE_SESSION=true
case "$EXISTING_STATUS" in
    WORKING)
        log_info "Sesión '$SESSION_NAME' ya está vinculada y WORKING. No requiere emparejamiento."
        exit 0
        ;;
    STARTING|SCAN_QR_CODE)
        CREATE_SESSION=false
        log_info "Reutilizando sesión '$SESSION_NAME' ($EXISTING_STATUS)."
        ;;
    FAILED|STOPPED)
        log_info "Recuperando sesión '$SESSION_NAME' ($EXISTING_STATUS)..."
        curl -fsS --connect-timeout 5 --max-time 15 -X POST -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME/stop" > /dev/null
        curl -fsS --connect-timeout 5 --max-time 15 -X POST -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME/logout" > /dev/null
        curl -fsS --connect-timeout 5 --max-time 15 -X DELETE -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME" > /dev/null
        sleep 2
        ;;
    ABSENT) ;;
    *)
        log_err "Estado de sesión desconocido ($EXISTING_STATUS). No se modificó la sesión."
        exit 1
        ;;
esac

if [ "$CREATE_SESSION" = true ]; then
    # === Ensure NOWEB engine (avoids GOWS bug from WAHA 2026.7.2) ===
    CURRENT_DEFAULT=$(grep '^WHATSAPP_DEFAULT_ENGINE=' "$ENV_FILE" | cut -d= -f2)
    if [ "$CURRENT_DEFAULT" != "NOWEB" ]; then
        log_warn "WHATSAPP_DEFAULT_ENGINE=$CURRENT_DEFAULT (should be NOWEB)"
        log_warn "Applying fix: WAHA 2026.7.2 + GOWS has pairing code bug."
        sed -i 's/^WHATSAPP_DEFAULT_ENGINE=.*/WHATSAPP_DEFAULT_ENGINE=NOWEB/' "$ENV_FILE"
        log_warn "Edited $ENV_FILE. Restart container to apply:"
        log_warn "  cd ~/.janitor/docker && docker compose --env-file waha.env -f waha-compose.yml restart"
        log_warn "Continuing with --engine NOWEB for this session anyway."
    fi

    log_info "Creando sesión '$SESSION_NAME' con engine NOWEB..."
    CREATE_RESP=$(curl -fsS --connect-timeout 5 --max-time 15 -X POST -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
        -d "{\"name\":\"$SESSION_NAME\",\"config\":{\"engine\":\"NOWEB\"}}" \
        "$BASE_URL/api/sessions")
    echo "$CREATE_RESP" | "$JANITOR_SERVICE_PYTHON" -m json.tool 2>/dev/null || echo "$CREATE_RESP"

    sleep 2

    log_info "Iniciando sesión..."
    curl -fsS --connect-timeout 5 --max-time 15 -X POST -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME/start" | \
        "$JANITOR_SERVICE_PYTHON" -m json.tool 2>/dev/null
fi

# Wait for SCAN_QR_CODE
log_info "Esperando estado SCAN_QR_CODE (max 15s)..."
for i in $(seq 1 15); do
    STATUS=$(curl -fsS --connect-timeout 5 --max-time 15 -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME" | \
        "$JANITOR_SERVICE_PYTHON" -c "import sys, json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
    if [ "$STATUS" = "WORKING" ]; then
        log_info "Sesión '$SESSION_NAME' ya está vinculada y WORKING."
        exit 0
    fi
    if [ "$STATUS" = "SCAN_QR_CODE" ]; then
        log_info "Sesión lista para autenticar (status=$STATUS en ${i}s)"
        break
    fi
    if [ "$STATUS" = "FAILED" ]; then
        log_err "Sesión en FAILED state. Logs:"
        docker logs janitor-waha --tail 20 >&2
        exit 1
    fi
    sleep 1
done

if [ "$STATUS" != "SCAN_QR_CODE" ]; then
    log_err "Sesión no llegó a SCAN_QR_CODE (status=$STATUS)"
    exit 1
fi

# === Branch: pairing code (phone) vs QR ===

if [ "${1:-}" = "--qr" ] || [ -z "${1:-}" ]; then
    # --- QR code flow ---
    log_info "Obteniendo QR code..."
    # Keep a valid QR available for the image viewer; remove failed downloads.
    if [ -z "$QR_OUTPUT" ]; then
        scratch_dir="${TMPDIR:-${HERMES_HOME:-$HOME/.janitor}/cache/scratch}"
        mkdir -p "$scratch_dir"
        scratch_dir="$(cd "$scratch_dir" && pwd)"
        QR_OUTPUT=$(mktemp "$scratch_dir/janitor-waha-qr.XXXXXX")
        trap 'rm -f -- "$QR_OUTPUT"' EXIT
    fi
    curl -fsS --connect-timeout 5 --max-time 15 -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/$SESSION_NAME/auth/qr" -o "$QR_OUTPUT"
    if [ -s "$QR_OUTPUT" ] && file "$QR_OUTPUT" | grep -q "PNG image"; then
        chmod 600 "$QR_OUTPUT"
        trap - EXIT
        log_info "QR guardado en $QR_OUTPUT"
        log_info "Elimina el archivo después de vincular el dispositivo."
        log_info "Abriéndolo con xdg-open..."
        xdg-open "$QR_OUTPUT" 2>/dev/null || log_warn "No se pudo abrir automáticamente. Abrilo manualmente: $QR_OUTPUT"
    else
        log_err "No se pudo generar QR válido (output type: $(file -b "$QR_OUTPUT" 2>/dev/null || echo unknown))"
        exit 1
    fi
else
    # --- Pairing code flow ---
    PHONE="$1"
    # Validate: digits only, 10-15 chars
    if ! echo "$PHONE" | grep -qE '^[0-9]{10,15}$'; then
        log_err "Phone '$PHONE' no parece número internacional válido (10-15 dígitos, sin +)."
        log_err "Ejemplo: 573001234567 (Colombia, 12 dígitos)"
        exit 1
    fi

    log_info "Pidiendo pairing code para $PHONE..."
    CODE_RESP=$(curl -fsS --connect-timeout 5 --max-time 15 -X POST -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
        -d "{\"phoneNumber\":\"$PHONE\"}" \
        "$BASE_URL/api/$SESSION_NAME/auth/request-code")

    CODE=$(echo "$CODE_RESP" | "$JANITOR_SERVICE_PYTHON" -c "import sys, json; print(json.load(sys.stdin).get('code','?'))" 2>/dev/null)

    if [ -z "$CODE" ] || [ "$CODE" = "?" ]; then
        log_err "No se pudo obtener código. Respuesta:"
        echo "$CODE_RESP" | "$JANITOR_SERVICE_PYTHON" -m json.tool 2>/dev/null || echo "$CODE_RESP"
        log_err "Logs del contenedor:"
        docker logs janitor-waha --tail 20 >&2
        exit 1
    fi

    echo ""
    echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GRN}PAIRING CODE:${NC}  ${YLW}${CODE}${NC}"
    echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  En tu celular con WhatsApp:"
    echo "    1. Settings → Linked Devices"
    echo "    2. 'Link a device'"
    echo "    3. Choose 'Link with phone number' (no QR)"
    echo "    4. Enter code:  ${YLW}${CODE}${NC}"
    echo ""
    echo -e "  ${YLW}The code expires in ~60-90 seconds. If it times out, re-run this script.${NC}"
    echo ""
    echo "  Waiting for WORKING transition (max 90s)..."
    for i in $(seq 1 18); do
        STATUS=$(curl -fsS --connect-timeout 5 --max-time 15 -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME" | \
            "$JANITOR_SERVICE_PYTHON" -c "import sys, json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
        if [ "$STATUS" = "WORKING" ]; then
            log_info "Sesión WORKING (en $((i*5))s)"
            ME=$(curl -fsS --connect-timeout 5 --max-time 15 -H "X-Api-Key: $WAHA_API_KEY" "$BASE_URL/api/sessions/$SESSION_NAME/me" 2>/dev/null)
            echo "    $ME" | "$JANITOR_SERVICE_PYTHON" -m json.tool 2>/dev/null | head -5
            echo ""
            log_info "Test sending a message:"
            echo "    curl -X POST -H \"X-Api-Key: \$WAHA_API_KEY\" -H \"Content-Type: application/json\" \\"
            echo "      -d '{\"session\":\"$SESSION_NAME\",\"chatId\":\"${PHONE}@c.us\",\"text\":\"Hi!\"}' \\"
            echo "      $BASE_URL/api/sendText"
            exit 0
        fi
        if [ "$STATUS" = "FAILED" ]; then
            log_err "Sesión FAILED. Possible incorrect or rejected code."
            log_err "Logs:"
            docker logs janitor-waha --since 30s 2>&1 | grep -iE "error|warn|code" | tail -10 >&2
            exit 1
        fi
        sleep 5
    done

    log_warn "Sesión sigue en $STATUS tras 90s. Did you enter the code on your phone?"
    log_warn "If you did and it expired, run: $0 $PHONE"
fi
