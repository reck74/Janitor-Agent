#!/usr/bin/env bash
# =========================================================
# Janitor — Firecrawl Deploy Script
#
# Despliega Firecrawl self-host con Docker Compose. Idempotente:
# - No regenera credenciales si firecrawl.env ya existe (preserva volumenes).
# - No duplica FIRECRAWL_API_URL/KEY en ~/.janitor/.env.
#
# Modelo: scripts/setup-honcho.sh (mismo patron de logging y errores).
# =========================================================
set -euo pipefail

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
JANITOR_SOURCE_DIR="${JANITOR_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SKILL_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DOCKER_DIR="${JANITOR_HOME}/docker"
ENV_FILE="${DOCKER_DIR}/firecrawl.env"
COMPOSE_DST="${DOCKER_DIR}/firecrawl-compose.yml"
COMPOSE_SRC="${SKILL_SCRIPTS_DIR}/firecrawl-compose.yml"
JANITOR_ENV="${JANITOR_HOME}/.env"

# API key local — DEBE ser identica al TEST_API_KEY del env_file generado.
# Usa espacio (no guion) para coincidir con la imagen upstream de Firecrawl.
# Verificado funcional en produccion (10h+ healthy).
FIRECRAWL_LOCAL_API_KEY="fc janitor-local"
FIRECRAWL_LOCAL_API_URL="http://127.0.0.1:1974"

# Colores (mismo esquema que setup-honcho.sh)
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

# Genera ~/.janitor/docker/firecrawl.env con credenciales aleatorias.
# IDEMPOTENTE: si el archivo ya existe, lo preserva (no rompe volumenes existentes).
generate_firecrawl_env() {
    log_info "Verificando ${ENV_FILE}..."
    if [[ -f "$ENV_FILE" ]]; then
        log_ok "firecrawl.env ya existe — preservando credenciales (no se regenera)."
        # Validar que tiene las claves obligatorias
        local missing=0
        for key in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB USE_DB_AUTHENTICATION \
                   BULL_AUTH_KEY RABBITMQ_DEFAULT_USER RABBITMQ_DEFAULT_PASS \
                   NUQ_RABBITMQ_URL TEST_API_KEY; do
            if ! grep -q "^${key}=" "$ENV_FILE"; then
                log_warn "  Falta clave: ${key}"
                missing=1
            fi
        done
        if [[ "$missing" == "1" ]]; then
            log_fail "firecrawl.env existe pero esta incompleto. Eliminalo y re-ejecuta: rm ${ENV_FILE}"
            exit 1
        fi
        return 0
    fi

    log_info "Generando credenciales aleatorias (openssl rand)..."
    mkdir -p "$DOCKER_DIR"

    local pg_pass bull_key rabbit_pass
    pg_pass=$(openssl rand -hex 16)
    bull_key=$(openssl rand -hex 24)
    rabbit_pass=$(openssl rand -hex 16)

    # NUQ_RABBITMQ_URL embebe la misma password que RABBITMQ_DEFAULT_PASS —
    # si no coinciden, RabbitMQ rechaza la conexion del API.
    local rabbit_url="amqp://firecrawl:${rabbit_pass}@firecrawl-rabbitmq:5672"

    {
        echo "# ========================================================="
        echo "# Firecrawl — Variables de entorno (self-host local)"
        echo "# Generado por janitor-firecrawl/scripts/deploy.sh"
        echo "# Fecha: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "# NO subir a repositorios publicos — contiene credenciales."
        echo "# ========================================================="
        echo ""
        echo "# PostgreSQL — DEBE ser POSTGRES_DB=postgres (constraint pg_cron)"
        echo "POSTGRES_USER=postgres"
        echo "POSTGRES_PASSWORD=${pg_pass}"
        echo "POSTGRES_DB=postgres"
        echo "USE_DB_AUTHENTICATION=false"
        echo ""
        echo "# Bull dashboard auth"
        echo "BULL_AUTH_KEY=${bull_key}"
        echo ""
        echo "# RabbitMQ — RABBITMQ_DEFAULT_PASS debe coincidir con la password"
        echo "# embebida en NUQ_RABBITMQ_URL."
        echo "RABBITMQ_DEFAULT_USER=firecrawl"
        echo "RABBITMQ_DEFAULT_PASS=${rabbit_pass}"
        echo "NUQ_RABBITMQ_URL=${rabbit_url}"
        echo ""
        echo "# API local — TEST_API_KEY DEBE ser 'fc janitor-local' (con espacio)"
        echo "# para coincidir con FIRECRAWL_API_KEY inyectado en ~/.janitor/.env"
        echo "TEST_API_KEY=${FIRECRAWL_LOCAL_API_KEY}"
        echo ""
        echo "# Tuning"
        echo "NUM_WORKERS_PER_QUEUE=8"
        echo "CRAWL_CONCURRENT_REQUESTS=10"
    } > "$ENV_FILE"

    chmod 600 "$ENV_FILE"
    log_ok "firecrawl.env generado en ${ENV_FILE} (chmod 600)"
}

ensure_compose_file() {
    log_info "Copiando compose a ${COMPOSE_DST}..."
    mkdir -p "$DOCKER_DIR"

    if [[ ! -f "$COMPOSE_SRC" ]]; then
        log_fail "Compose fuente no encontrado: ${COMPOSE_SRC}"
        exit 1
    fi

    cp -f "$COMPOSE_SRC" "$COMPOSE_DST"
    log_ok "Compose actualizado."
}

launch_firecrawl() {
    log_info "Pulling imagenes..."
    if ! docker compose -f "$COMPOSE_DST" pull; then
        log_warn "docker compose pull tuvo errores — continuando con imagenes cacheadas."
    fi

    log_info "Levantando stack (docker compose up -d)..."
    if ! docker compose -f "$COMPOSE_DST" up -d; then
        log_fail "docker compose up fallo."
        log_info "Logs: docker compose -f ${COMPOSE_DST} logs"
        exit 1
    fi
    log_ok "Contenedores iniciados."
}

wait_for_health() {
    local timeout="${1:-180}"
    local elapsed=0
    local interval=5

    log_info "Esperando health check de janitor-firecrawl-api (timeout: ${timeout}s)..."
    while [[ $elapsed -lt $timeout ]]; do
        local health
        health=$(docker inspect --format='{{.State.Health.Status}}' janitor-firecrawl-api 2>/dev/null || echo "starting")
        if [[ "$health" == "healthy" ]]; then
            log_ok "Firecrawl healthy en ${FIRECRAWL_LOCAL_API_URL}"
            return 0
        fi
        echo -ne "\r  ${CYAN}...${NC} ${elapsed}s / ${timeout}s (status: ${health})   "
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo
    log_warn "Firecrawl no paso health check en ${timeout}s."
    log_info "Estado actual de contenedores:"
    docker compose -f "$COMPOSE_DST" ps || true
    log_info "Logs: docker logs janitor-firecrawl-api --tail 50"
    return 1
}

# BUG 13 fix: inyecta FIRECRAWL_API_URL + FIRECRAWL_API_KEY en ~/.janitor/.env
# Sin estas variables, el agente Janitor es ciego a Firecrawl aunque este healthy
# (ver tools/web_tools.py:245 y plugins/web/firecrawl/provider.py:127).
inject_firecrawl_env() {
    log_info "Inyectando FIRECRAWL_API_URL/KEY en ${JANITOR_ENV}..."

    if [[ ! -f "$JANITOR_ENV" ]]; then
        log_warn "${JANITOR_ENV} no existe — creando."
        touch "$JANITOR_ENV"
    fi

    # Idempotente: eliminar lineas previas de Firecrawl antes de appendear.
    # Usa tmp file para evitar -i que tiene comportamiento distinto en macOS/BSD.
    local tmp
    tmp=$(mktemp)
    grep -v '^FIRECRAWL_API_URL=' "$JANITOR_ENV" 2>/dev/null | grep -v '^FIRECRAWL_API_KEY=' > "$tmp" || true
    {
        echo ""
        echo "# Firecrawl — Self-hosted local instance (inyectado por deploy.sh)"
        echo "FIRECRAWL_API_URL=${FIRECRAWL_LOCAL_API_URL}"
        echo "FIRECRAWL_API_KEY=${FIRECRAWL_LOCAL_API_KEY}"
    } >> "$tmp"
    mv "$tmp" "$JANITOR_ENV"

    log_ok "FIRECRAWL_API_URL y FIRECRAWL_API_KEY inyectados."
    log_warn "Reinicia Janitor para que las herramientas web se activen."
}

verify_scrape() {
    log_info "Verificando endpoint /v0/scrape con example.com..."
    local response
    if ! response=$(curl -sf -X POST "${FIRECRAWL_LOCAL_API_URL}/v0/scrape" \
            -H "Authorization: Bearer ${FIRECRAWL_LOCAL_API_KEY}" \
            -H "Content-Type: application/json" \
            -d '{"url":"https://example.com","formats":["markdown"]}' 2>&1); then
        log_warn "Scrape de prueba fallo (Firecrawl puede tardar en calentar)."
        log_info "Intenta manualmente: curl -X POST ${FIRECRAWL_LOCAL_API_URL}/v0/scrape \\"
        log_info "  -H 'Authorization: Bearer ${FIRECRAWL_LOCAL_API_KEY}' \\"
        log_info "  -H 'Content-Type: application/json' \\"
        log_info "  -d '{\"url\":\"https://example.com\",\"formats\":[\"markdown\"]}'"
        return 0
    fi

    if echo "$response" | grep -q '"success":true'; then
        log_ok "Scrape de prueba exitoso — Firecrawl 100% funcional."
    else
        log_warn "Scrape respondio pero sin success:true: ${response:0:200}..."
    fi
}

print_summary() {
    echo ""
    echo -e "${BOLD}═══ Firecrawl desplegado ═══${NC}"
    echo ""
    docker compose -f "$COMPOSE_DST" ps 2>/dev/null || true
    echo ""
    echo -e "Endpoints:"
    echo -e "  ${CYAN}Health${NC}:  curl ${FIRECRAWL_LOCAL_API_URL}/v0/health/liveness"
    echo -e "  ${CYAN}Scrape${NC}:  POST ${FIRECRAWL_LOCAL_API_URL}/v0/scrape"
    echo -e "  ${CYAN}Crawl${NC}:   POST ${FIRECRAWL_LOCAL_API_URL}/v0/crawl"
    echo ""
    echo -e "API Key (header Authorization): ${BOLD}${FIRECRAWL_LOCAL_API_KEY}${NC}"
    echo ""
    echo -e "Gestion:"
    echo -e "  ${CYAN}Logs${NC}:    docker compose -f ${COMPOSE_DST} logs -f"
    echo -e "  ${CYAN}Stop${NC}:    docker compose -f ${COMPOSE_DST} down"
    echo -e "  ${CYAN}Restart${NC}: docker compose -f ${COMPOSE_DST} restart"
    echo ""
    echo -e "${YELLOW}⚠${NC} Reinicia Janitor para activar las herramientas web (web_search, web_extract)."
}

main() {
    echo -e "${BOLD}═══ Janitor — Firecrawl Deploy ═══${NC}"
    echo ""
    check_docker
    generate_firecrawl_env
    ensure_compose_file
    launch_firecrawl

    if wait_for_health 180; then
        inject_firecrawl_env
        verify_scrape || true
        print_summary
        exit 0
    else
        echo ""
        log_fail "Firecrawl no esta healthy. Revisa los logs arriba."
        exit 1
    fi
}

main "$@"
