#!/usr/bin/env bash
# =========================================================
# Janitor — n8n Deploy Script
#
# Despliega n8n self-host con Docker Compose. Idempotente:
# - No regenera credenciales si n8n.env ya existe (preserva encryption key).
# - No duplica N8N_API_URL en ~/.janitor/.env.
#
# El compose y el script auth helper se copian desde este directorio
# (skill self-contained) a ~/.janitor/docker/ para que el stack viva
# en el layout estandar de janitor (janitor_cli.py:25, AGENTS.md #5).
# =========================================================
set -euo pipefail

# Resolve skill-bundled paths (this script lives in skills/devops/janitor-n8n/scripts/).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
DOCKER_DIR="${JANITOR_HOME}/docker"

COMPOSE_SRC="${SCRIPT_DIR}/n8n-compose.yml"
COMPOSE_DST="${DOCKER_DIR}/n8n-compose.yml"

ENV_FILE="${DOCKER_DIR}/n8n.env"
LOCAL_FILES="${DOCKER_DIR}/local-files"
AUTH_SRC="${SCRIPT_DIR}/n8n-auth.sh"
AUTH_DST="${DOCKER_DIR}/n8n-auth.sh"
JANITOR_ENV="${JANITOR_HOME}/.env"
N8N_URL="http://127.0.0.1:5678"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

# ─── 1. Check Docker ───────────────────────────────────────────
check_docker() {
    log_info "Verificando Docker..."
    if ! command -v docker >/dev/null 2>&1; then
        log_fail "Docker CLI no encontrado. Instala Docker: https://get.docker.com"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log_fail "El daemon de Docker no esta corriendo. Inicialo con: sudo systemctl start docker"
        exit 1
    fi
    log_ok "Docker disponible."
}

# ─── 2. Generate env file (NEVER overwrite if exists) ─────────
generate_env() {
    log_info "Verificando ${ENV_FILE}..."
    if [[ -f "$ENV_FILE" ]]; then
        log_ok "n8n.env ya existe — preservando encryption key (no se regenera)."
        return 0
    fi
    log_info "Generando encryption key con openssl rand..."
    local enc_key
    enc_key=$(openssl rand -hex 32)

    mkdir -p "$DOCKER_DIR"
    cat > "$ENV_FILE" <<EOF
# n8n — Self-hosted local instance for Janitor
# Generado por janitor-n8n/scripts/deploy.sh el $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# chmod 600 aplicado. NO subir a repositorios publicos.

# Encryption key for n8n credential store (AES-256)
N8N_ENCRYPTION_KEY=${enc_key}

# Timezone
GENERIC_TIMEZONE=America/Mexico_City
EOF
    chmod 600 "$ENV_FILE"
    log_ok "n8n.env generado en ${ENV_FILE} (chmod 600)."
}

# ─── 3. Copy bundled compose file + auth helper to ~/.janitor/docker/ ──
ensure_files() {
    if [[ ! -f "$COMPOSE_SRC" ]]; then
        log_fail "Compose fuente no encontrado: ${COMPOSE_SRC}"
        exit 1
    fi
    if [[ ! -f "$AUTH_SRC" ]]; then
        log_fail "Auth helper fuente no encontrado: ${AUTH_SRC}"
        exit 1
    fi

    mkdir -p "$DOCKER_DIR" "$LOCAL_FILES"
    cp -f "$COMPOSE_SRC" "$COMPOSE_DST"
    cp -f "$AUTH_SRC" "$AUTH_DST"
    chmod +x "$AUTH_DST"
    log_ok "Compose copiado a ${COMPOSE_DST}"
    log_ok "Auth helper copiado a ${AUTH_DST}"
    log_ok "local-files dir listo: ${LOCAL_FILES}"
}

# ─── 4. Launch ────────────────────────────────────────────────
launch() {
    log_info "Pulling imagenes..."
    if ! docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" pull; then
        log_warn "docker compose pull tuvo errores — continuando con imagenes cacheadas."
    fi
    log_info "Levantando stack (docker compose up -d)..."
    if ! docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" up -d; then
        log_fail "docker compose up fallo."
        log_info "Logs: docker compose -f ${COMPOSE_DST} logs"
        exit 1
    fi
    log_ok "Contenedor janitor-n8n lanzado."
}

# ─── 5. Wait for health ───────────────────────────────────────
wait_for_health() {
    local timeout="${1:-180}"
    local elapsed=0
    local interval=5

    log_info "Esperando healthcheck de janitor-n8n (timeout: ${timeout}s)..."
    while (( elapsed < timeout )); do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' janitor-n8n 2>/dev/null || echo "starting")
        if [[ "$status" == "healthy" ]]; then
            log_ok "n8n healthy en ${N8N_URL} tras ${elapsed}s."
            return 0
        fi
        printf "\r  ${CYAN}...${NC} %ss / %ss (status: %s)   " "$elapsed" "$timeout" "$status"
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo
    log_warn "n8n no alcanzo estado healthy en ${timeout}s."
    docker logs janitor-n8n --tail 30 || true
    return 1
}

# ─── 6. Verify endpoint ───────────────────────────────────────
verify_endpoint() {
    log_info "Verificando endpoint ${N8N_URL}/healthz..."
    local response
    response=$(curl -s -o /dev/null -w "%{http_code}" "${N8N_URL}/healthz" 2>/dev/null || echo "000")
    if [[ "$response" == "200" ]]; then
        log_ok "n8n responde en ${N8N_URL}/healthz (HTTP 200)."
    else
        log_warn "Endpoint respondio HTTP ${response} — puede necesitar mas tiempo."
    fi
}

# ─── 7. Inject vars into ~/.janitor/.env ──────────────────────
inject_janitor_env() {
    if [[ ! -f "$JANITOR_ENV" ]]; then
        log_warn "${JANITOR_ENV} no existe — creando."
        touch "$JANITOR_ENV"
    fi

    # Idempotente: eliminar entradas previas antes de appendear.
    local tmp
    tmp=$(mktemp)
    grep -v '^N8N_API_URL=' "$JANITOR_ENV" 2>/dev/null | grep -v '^# n8n —' > "$tmp" || true
    {
        echo ""
        echo "# n8n — Self-hosted local instance (inyectado por deploy.sh)"
        echo "N8N_API_URL=${N8N_URL}"
    } >> "$tmp"
    mv "$tmp" "$JANITOR_ENV"

    log_ok "N8N_API_URL inyectado en ${JANITOR_ENV}."
}

print_summary() {
    echo ""
    echo -e "${BOLD}═══ n8n desplegado ═══${NC}"
    echo ""
    docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" ps 2>/dev/null || true
    echo ""
    echo -e "Endpoints:"
    echo -e "  ${CYAN}Web UI${NC}:   ${N8N_URL}"
    echo -e "  ${CYAN}Health${NC}:  curl ${N8N_URL}/healthz"
    echo ""
    echo -e "Archivos (runtime en ${DOCKER_DIR}):"
    echo -e "  ${CYAN}Compose${NC}: ${COMPOSE_DST}"
    echo -e "  ${CYAN}Env${NC}:     ${ENV_FILE}"
    echo -e "  ${CYAN}Auth${NC}:    ${AUTH_DST}"
    echo ""
    echo -e "Skill source (bundled): ${SKILL_DIR}"
    echo ""
    echo -e "Gestion:"
    echo -e "  ${CYAN}Logs${NC}:    docker compose -f ${COMPOSE_DST} --env-file ${ENV_FILE} logs -f"
    echo -e "  ${CYAN}Stop${NC}:    docker compose -f ${COMPOSE_DST} --env-file ${ENV_FILE} down"
    echo -e "  ${CYAN}Restart${NC}: docker compose -f ${COMPOSE_DST} --env-file ${ENV_FILE} restart"
    echo ""
    echo -e "${YELLOW}⚠${NC} Crea el usuario Owner desde ${N8N_URL} si aun no existe."
    echo -e "${YELLOW}⚠${NC} Reinicia Janitor para que las herramientas detecten N8N_API_URL."
}

main() {
    echo -e "${BOLD}═══ Janitor — n8n Deploy ═══${NC}"
    echo ""

    check_docker
    generate_env
    ensure_files
    launch

    if wait_for_health 180; then
        verify_endpoint
        inject_janitor_env
        print_summary
        exit 0
    else
        echo ""
        log_fail "n8n no esta healthy. Revisa los logs arriba."
        exit 1
    fi
}

main "$@"
