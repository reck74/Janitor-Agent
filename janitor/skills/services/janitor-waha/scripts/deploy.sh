#!/usr/bin/env bash
# deploy.sh — deploy / repair the janitor-waha container (run by `janitor services deploy waha`).
#
# Generates an absolute-path waha-compose.yml at deploy time so that bind mounts
# resolve against the Janitor root home, regardless of where docker compose is
# invoked from. Idempotent: re-runs preserve credentials and the linked session.
# Never prints a secret: credentials stay in waha.env / .env (mode 0600).

set -euo pipefail

# ============= CONFIG =============
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JANITOR_HOME="${JANITOR_HOME:-${HERMES_HOME:-$HOME/.janitor}}"
COMPOSE_DIR="$JANITOR_HOME/docker"
STACK_DIR="$COMPOSE_DIR/waha"
COMPOSE_FILE="$COMPOSE_DIR/waha-compose.yml"
ENV_FILE="$COMPOSE_DIR/waha.env"
SESSIONS_DIR="$STACK_DIR/sessions"
MEDIA_DIR="$STACK_DIR/media"
JANITOR_ENV="$JANITOR_HOME/.env"
CONTAINER_NAME="janitor-waha"
HEALTH_TIMEOUT=90

# ============= COLORS =============
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GRN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ============= STEPS =============

check_docker() {
    if ! docker info >/dev/null 2>&1; then
        log_err "Docker daemon no responde. Verifica que esté corriendo y que tu usuario esté en el grupo docker."
        exit 1
    fi
    log_info "Docker OK: $(docker info --format '{{.ServerVersion}}')"
}

prepare_dirs() {
    mkdir -p "$STACK_DIR" "$SESSIONS_DIR" "$MEDIA_DIR"
    log_info "Dirs listas: $STACK_DIR/{sessions,media}"
}

generate_env() {
    if [ -f "$ENV_FILE" ]; then
        log_info "waha.env ya existe — credenciales preservadas (no se regeneran)"
        return 0
    fi

    WAHA_API_KEY=$(openssl rand -hex 32)
    WAHA_DASHBOARD_USERNAME="admin"
    WAHA_DASHBOARD_PASSWORD=$(openssl rand -hex 24)
    WAHA_SWAGGER_USERNAME="swagger"
    WAHA_SWAGGER_PASSWORD=$(openssl rand -hex 24)

    cat > "$ENV_FILE" <<EOF
# WAHA - WhatsApp HTTP API
# Stack janitor-waha — generado por janitor-waha/scripts/deploy.sh
# https://waha.devlike.pro/

# ====================
# ===== SECURITY =====
# ====================
WAHA_API_KEY=${WAHA_API_KEY}
WAHA_DASHBOARD_USERNAME=${WAHA_DASHBOARD_USERNAME}
WAHA_DASHBOARD_PASSWORD=${WAHA_DASHBOARD_PASSWORD}
WHATSAPP_SWAGGER_USERNAME=${WAHA_SWAGGER_USERNAME}
WHATSAPP_SWAGGER_PASSWORD=${WAHA_SWAGGER_PASSWORD}

WAHA_DASHBOARD_ENABLED=True
WHATSAPP_SWAGGER_ENABLED=True

# ==================
# ===== COMMON =====
# ==================
# NOWEB: engine Node, sin Chromium. Default desde ago 2026.
# GOWS tiene bug confirmado en request-code con WAHA 2026.7.2
# (no parsea link_code_pairing_wrapped_primary_ephemeral_pub)
WHATSAPP_DEFAULT_ENGINE=NOWEB
WAHA_NAMESPACE=all

WAHA_BASE_URL=http://localhost:3000

# ===================
# ===== LOGGING =====
# ===================
WAHA_LOG_FORMAT=PRETTY
WAHA_LOG_LEVEL=info
WAHA_PRINT_QR=False

# =========================
# ===== MEDIA STORAGE =====
# =========================
WAHA_MEDIA_STORAGE=LOCAL
WHATSAPP_FILES_LIFETIME=0
WHATSAPP_FILES_FOLDER=/app/.media
EOF

    chmod 600 "$ENV_FILE"
    log_info "waha.env generado con credenciales random (API key 64 hex, passwords 48 hex)"
}

write_compose() {
    # Always (re)generate the compose file with absolute paths resolved from
    # JANITOR_HOME. The bundled template under scripts/waha-compose.yml is the
    # source of truth for service config — we only swap in absolute volume
    # paths so it works regardless of the cwd used to invoke docker compose.
    log_info "Generando waha-compose.yml con paths absolutos desde JANITOR_HOME=$JANITOR_HOME"

    cat > "$COMPOSE_FILE" <<EOF
# janitor-waha — WhatsApp HTTP API
# Generado por janitor-waha/scripts/deploy.sh — no editar a mano; se sobrescribe.
# Plantilla: janitor/skills/services/janitor-waha/scripts/waha-compose.yml
# https://waha.devlike.pro/docs/how-to/install/
#
# Decisiones de arquitectura (vs. compose oficial):
#  - Imagen core (devlikeapro/waha:latest) en lugar de waha-plus (pagada)
#  - Engine NOWEB (Node, sin Chromium) — sin el bug de pairing-code que tiene
#    GOWS en WAHA 2026.7.2 (no parsea link_code_pairing_wrapped_primary_ephemeral_pub)
#  - Paths absolutos para volúmenes resueltos desde JANITOR_HOME (compose vive en
#    ~/.janitor/docker/, las sesiones viven en ~/.janitor/docker/waha/sessions)
#  - DNS 1.1.1.1/8.8.8.8 explícitos para resolver web.whatsapp.com en redes restrictivas
#  - Solo loopback en 127.0.0.1:3000 — no expuesto al exterior
#  - Sin Postgres/Mongo/MinIO — sesiones y media en volúmenes locales
#  - Log rotation: 100MB x 10 archivos (idéntico a defaults oficiales)
#  - container_name fijo: janitor-waha (para scripting)
#
# ⚠️  WAHA usa un cliente WhatsApp Web no oficial. WhatsApp puede banear cuentas que
#     detecte automatización. Es responsabilidad del operador. Documentado en skill.

services:
  waha:
    restart: unless-stopped
    container_name: janitor-waha

    # Core image (gratis). Cambiar a devlikeapro/waha-plus solo si se compra licencia.
    image: devlikeapro/waha:latest

    # Fix para resolución de web.whatsapp.com en redes restrictivas
    dns:
      - 1.1.1.1
      - 8.8.8.8

    logging:
      driver: 'json-file'
      options:
        max-size: '100m'
        max-file: '10'

    ports:
      # Solo loopback — accesible desde Janitor agent y localhost, no desde LAN
      - '127.0.0.1:3000:3000/tcp'

    volumes:
      # Sesiones (auth de WhatsApp) — persistir entre reinicios del contenedor
      - '${SESSIONS_DIR}:/app/.sessions'
      # Media descargada (imágenes, videos, audio recibidos)
      - '${MEDIA_DIR}:/app/.media'

    env_file:
      - ${ENV_FILE}

    # Healthcheck: WAHA /health requiere API key cuando WAHA_API_KEY está set
    healthcheck:
      test: ['CMD', 'sh', '-c', 'wget -qO- --header="X-Api-Key: \$WAHA_API_KEY" http://127.0.0.1:3000/health | grep -q .']
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 30s
EOF

    chmod 600 "$COMPOSE_FILE"
    log_info "waha-compose.yml escrito en $COMPOSE_FILE"
}

launch() {
    cd "$COMPOSE_DIR"
    log_info "Pull imagen devlikeapro/waha:latest"
    docker compose --env-file waha.env -f waha-compose.yml pull 2>&1 | tail -3

    log_info "Levantando contenedor"
    docker compose --env-file waha.env -f waha-compose.yml up -d
}

wait_for_health() {
    log_info "Esperando healthcheck (max ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [ "$elapsed" -lt "$HEALTH_TIMEOUT" ]; do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
        if [ "$status" = "healthy" ]; then
            log_info "Container healthy (en ${elapsed}s)"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        echo -n "."
    done
    echo ""
    log_err "Container no alcanzó estado healthy en ${HEALTH_TIMEOUT}s"
    log_err "Últimos logs:"
    docker logs "$CONTAINER_NAME" --tail 30 >&2
    exit 1
}

verify_endpoint() {
    local api_key
    api_key=$(grep '^WAHA_API_KEY=' "$ENV_FILE" | cut -d= -f2)
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' \
        -H "X-Api-Key: ${api_key}" http://127.0.0.1:3000/health)
    if [ "$code" = "200" ]; then
        log_info "GET /health → 200 OK"
    else
        log_err "GET /health → HTTP $code"
        exit 1
    fi
}

inject_env() {
    local api_key dash_pass swagger_pass
    api_key=$(grep '^WAHA_API_KEY=' "$ENV_FILE" | cut -d= -f2)
    dash_pass=$(grep '^WAHA_DASHBOARD_PASSWORD=' "$ENV_FILE" | cut -d= -f2)
    swagger_pass=$(grep '^WHATSAPP_SWAGGER_PASSWORD=' "$ENV_FILE" | cut -d= -f2)

    # Eliminar vars previas para evitar duplicados
    sed -i '/^WAHA_BASE_URL=/d'           "$JANITOR_ENV" 2>/dev/null || true
    sed -i '/^WAHA_API_KEY=/d'            "$JANITOR_ENV" 2>/dev/null || true
    sed -i '/^WAHA_DASHBOARD_PASSWORD=/d' "$JANITOR_ENV" 2>/dev/null || true
    sed -i '/^WAHA_SWAGGER_PASSWORD=/d'   "$JANITOR_ENV" 2>/dev/null || true

    {
        echo ""
        echo "# WAHA — WhatsApp HTTP API (self-hosted local)"
        echo "WAHA_BASE_URL=http://127.0.0.1:3000"
        echo "WAHA_API_KEY=${api_key}"
        echo "WAHA_DASHBOARD_PASSWORD=${dash_pass}"
        echo "WAHA_SWAGGER_PASSWORD=${swagger_pass}"
    } >> "$JANITOR_ENV"

    chmod 600 "$JANITOR_ENV"
    log_info "Vars inyectadas en $JANITOR_ENV (WAHA_BASE_URL, WAHA_API_KEY, WAHA_DASHBOARD_PASSWORD, WAHA_SWAGGER_PASSWORD)"
}

print_summary() {
    echo ""
    echo -e "${GRN}janitor-waha desplegado. Solo escucha en 127.0.0.1:3000.${NC}"
    echo ""
    echo "  Credenciales: $ENV_FILE y $JANITOR_ENV (no se imprimen)."
    echo "  Panel web:    http://127.0.0.1:3000/dashboard (usuario admin, contraseña en waha.env)"
    echo ""
    echo "  Siguiente paso: vincular el WhatsApp del usuario (QR o código):"
    echo "    bash $SCRIPT_DIR/pair-waha.sh           # QR"
    echo "    bash $SCRIPT_DIR/pair-waha.sh 573001234567   # código por número"
    echo "  Luego la auditoría de solo lectura: python3 $SCRIPT_DIR/waha_audit.py status"
    echo ""
    echo -e "  ${YLW}WAHA es un cliente no oficial de WhatsApp: WhatsApp puede bloquear la cuenta.${NC}"
    echo ""
}

main() {
    log_info "Iniciando deploy janitor-waha"
    check_docker
    prepare_dirs
    generate_env
    write_compose
    launch
    wait_for_health
    verify_endpoint
    inject_env
    print_summary
}

main "$@"
