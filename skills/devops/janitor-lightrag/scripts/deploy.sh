#!/usr/bin/env bash
# =========================================================
# Janitor — LightRAG Deploy Script
#
# Despliega LightRAG self-host con Docker Compose (2 containers:
# lightrag app + postgres pgvector). Idempotente:
# - No regenera credenciales si lightrag.env ya existe (preserva volumenes).
# - No duplica LIGHTRAG_API_URL en ~/.janitor/.env.
#
# Prerequisite: janitor-honcho debe estar desplegado ANTES (necesitamos
# la red externa janitor-honcho-network para alcanzar Ollama).
#
# Modelo: scripts/deploy.sh de janitor-firecrawl y setup-n8n.sh.
# =========================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JANITOR_HOME="${HERMES_HOME:-$HOME/.janitor}"

DOCKER_DIR="${JANITOR_HOME}/docker"
ENV_FILE="${DOCKER_DIR}/lightrag.env"
COMPOSE_DST="${DOCKER_DIR}/lightrag-compose.yml"
COMPOSE_SRC="${SCRIPT_DIR}/lightrag-compose.yml"
JANITOR_ENV="${JANITOR_HOME}/.env"

LIGHTRAG_URL="http://127.0.0.1:9621"

# Colores (mismo esquema que deploy.sh de janitor-firecrawl)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}�${NC} $1"; }
log_fail()  { echo -e "${RED}�${NC} $1"; }

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

# ─── 2. Check janitor-honcho network exists ───────────────────
check_honcho_network() {
    if ! docker network inspect janitor-honcho-network >/dev/null 2>&1; then
        log_fail "La red externa 'janitor-honcho-network' no existe."
        log_info "Despliega janitor-honcho ANTES de este servicio:"
        log_info "  bash ~/.janitor/skills/devops/janitor-honcho/scripts/deploy.sh"
        exit 1
    fi
    log_ok "Red externa janitor-honcho-network detectada."
}

# ─── 3. Generate env file (NEVER overwrite if exists) ─────────
# IDEMPOTENTE: si lightrag.env ya existe, lo preserva para no romper
# volumenes persistentes (postgres data + NetworkX JSON + storage).
generate_lightrag_env() {
    log_info "Verificando ${ENV_FILE}..."
    if [[ -f "$ENV_FILE" ]]; then
        log_ok "lightrag.env ya existe — preservando credenciales (no se regenera)."
        # Validar que tiene las claves obligatorias
        local missing=0
        for key in POSTGRES_PASSWORD LIGHTRAG_API_KEY AUTH_ACCOUNTS; do
            if ! grep -q "^${key}=" "$ENV_FILE"; then
                log_warn "  Falta clave: ${key}"
                missing=1
            fi
        done
        if [[ "$missing" == "1" ]]; then
            log_fail "lightrag.env existe pero esta incompleto. Eliminalo y re-ejecuta: rm ${ENV_FILE}"
            exit 1
        fi
        return 0
    fi

    log_info "Generando credenciales aleatorias (openssl rand)..."
    mkdir -p "$DOCKER_DIR"

    local pg_pass api_key auth_password auth_account
    pg_pass=$(openssl rand -hex 16)
    api_key=$(openssl rand -hex 32)
    auth_password=$(openssl rand -hex 16)
    # AUTH_ACCOUNTS formato LightRAG: 'user:password' (el user es 'admin').
    auth_account="admin:${auth_password}"

    cat > "$ENV_FILE" <<EOF
# =========================================================
# LightRAG — Variables de entorno (self-host local)
# Generado por janitor-lightrag/scripts/deploy.sh
# Fecha: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# NO subir a repositorios publicos — contiene credenciales.
# chmod 600 aplicado.
# =========================================================

# --- PostgreSQL (container janitor-lightrag-db) ---
POSTGRES_PASSWORD=${pg_pass}

# --- LightRAG auth ---
# API key para llamadas REST (header X-API-Key)
LIGHTRAG_API_KEY=${api_key}
# WebUI: user 'admin' + password generado
AUTH_ACCOUNTS=${auth_account}

# --- Storage backends ---
# NetworkXStorage (in-memory + JSON files), NO PGGraphStorage — pgvector:pg18
# no incluye Apache AGE y PGGraphStorage crashea con
# 'function create_graph(unknown) does not exist'.
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

# --- LLM (z.ai coding endpoint) ---
LLM_BINDING=openai
LLM_BINDING_HOST=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5.2
LLM_API_KEY=${ZAI_API_KEY:-}

# --- Embeddings (Honcho Ollama local, cross-network) ---
EMBEDDING_BINDING=ollama
EMBEDDING_BINDING_HOST=http://janitor-honcho-ollama:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768

# --- Misc ---
WHITELIST_PATHS=/health
SUMMARY_LANGUAGE=Spanish
ENTITY_EXTRACTION_USE_JSON=true
EOF
    chmod 600 "$ENV_FILE"
    log_ok "lightrag.env generado en ${ENV_FILE} (chmod 600)"
}

# ─── 4. Copy compose from scripts/ → ~/.janitor/docker/ ───────
ensure_compose_file() {
    log_info "Sincronizando compose a ${COMPOSE_DST}..."
    mkdir -p "$DOCKER_DIR"

    if [[ ! -f "$COMPOSE_SRC" ]]; then
        log_fail "Compose fuente no encontrado: ${COMPOSE_SRC}"
        exit 1
    fi

    cp -f "$COMPOSE_SRC" "$COMPOSE_DST"
    log_ok "Compose actualizado."
}

# ─── 5. Launch ────────────────────────────────────────────────
launch() {
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

# ─── 6. Wait for health ───────────────────────────────────────
wait_for_health() {
    local timeout="${1:-240}"
    local elapsed=0
    local interval=5

    log_info "Esperando health check de janitor-lightrag (timeout: ${timeout}s)..."
    while [[ $elapsed -lt $timeout ]]; do
        local health
        health=$(docker inspect --format='{{.State.Health.Status}}' janitor-lightrag 2>/dev/null || echo "starting")
        if [[ "$health" == "healthy" ]]; then
            log_ok "LightRAG healthy en ${LIGHTRAG_URL}"
            return 0
        fi
        echo -ne "\r  ${CYAN}...${NC} ${elapsed}s / ${timeout}s (status: ${health})   "
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo
    log_warn "LightRAG no paso health check en ${timeout}s."
    log_info "Estado actual de contenedores:"
    docker compose -f "$COMPOSE_DST" ps || true
    log_info "Logs: docker logs janitor-lightrag --tail 50"
    return 1
}

# ─── 7. Inject LIGHTRAG_API_URL into ~/.janitor/.env ──────────
inject_janitor_env() {
    log_info "Inyectando LIGHTRAG_API_URL en ${JANITOR_ENV}..."

    if [[ ! -f "$JANITOR_ENV" ]]; then
        log_warn "${JANITOR_ENV} no existe — creando."
        touch "$JANITOR_ENV"
    fi

    # Idempotente: eliminar entrada previa antes de appendear.
    local tmp
    tmp=$(mktemp)
    grep -v '^LIGHTRAG_API_URL=' "$JANITOR_ENV" 2>/dev/null | grep -v '^LIGHTRAG_API_KEY=' > "$tmp" || true

    # Extraer LIGHTRAG_API_KEY + AUTH_ACCOUNTS del env file generado.
    local api_key auth_password
    api_key=$(grep '^LIGHTRAG_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
    auth_password=$(grep '^AUTH_ACCOUNTS=' "$ENV_FILE" | cut -d= -f2- | cut -d: -f2-)

    {
        echo ""
        echo "# LightRAG — Self-hosted local instance (inyectado por deploy.sh)"
        echo "LIGHTRAG_API_URL=${LIGHTRAG_URL}"
        echo "LIGHTRAG_API_KEY=${api_key}"
        echo "LIGHTRAG_WEBUI_USER=admin"
        echo "LIGHTRAG_WEBUI_PASSWORD=${auth_password}"
    } >> "$tmp"
    mv "$tmp" "$JANITOR_ENV"

    log_ok "LIGHTRAG_API_URL/KEY inyectados en ${JANITOR_ENV}."
    log_warn "Reinicia Janitor para activar el tool lightrag."
}

# ─── 8. Verify endpoint ───────────────────────────────────────
verify_endpoint() {
    log_info "Verificando endpoint ${LIGHTRAG_URL}/health..."
    local response
    response=$(curl -s -o /dev/null -w "%{http_code}" "${LIGHTRAG_URL}/health" 2>/dev/null || echo "000")
    if [[ "$response" == "200" ]]; then
        log_ok "LightRAG responde en ${LIGHTRAG_URL}/health (HTTP 200)"
    else
        log_warn "Endpoint respondio HTTP ${response} — puede necesitar mas tiempo."
    fi
}

# ─── Summary ──────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}═══ LightRAG desplegado ═══${NC}"
    echo ""
    docker compose -f "$COMPOSE_DST" ps 2>/dev/null || true
    echo ""
    echo -e "Endpoints:"
    echo -e "  ${CYAN}Health${NC}:    curl ${LIGHTRAG_URL}/health"
    echo -e "  ${CYAN}WebUI${NC}:     ${LIGHTRAG_URL}"
    echo -e "  ${CYAN}API base${NC}:  ${LIGHTRAG_URL}"
    echo ""
    echo -e "Auth:"
    echo -e "  ${CYAN}API header${NC}: X-API-Key: \$LIGHTRAG_API_KEY"
    echo -e "  ${CYAN}WebUI${NC}:     admin / \$LIGHTRAG_WEBUI_PASSWORD"
    echo ""
    echo -e "Gestion:"
    echo -e "  ${CYAN}Logs${NC}:    docker compose -f ${COMPOSE_DST} logs -f"
    echo -e "  ${CYAN}Stop${NC}:    docker compose -f ${COMPOSE_DST} down"
    echo -e "  ${CYAN}Restart${NC}: bash ${SCRIPT_DIR}/deploy.sh"
    echo ""
    echo -e "${YELLOW}⚠${NC} Reinicia Janitor para activar el tool lightrag."
    echo ""
    echo -e "Nota: GLM-5.2 es un modelo de razonamiento — queries tardan 60-120s."
    echo -e "      Esto es normal, no un timeout."
}

# ─── Main ─────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}═══ Janitor — LightRAG Deploy ═══${NC}"
    echo ""
    check_docker
    check_honcho_network
    generate_lightrag_env
    ensure_compose_file
    launch

    if wait_for_health 240; then
        inject_janitor_env
        verify_endpoint
        print_summary
        exit 0
    else
        echo ""
        log_fail "LightRAG no esta healthy. Revisa los logs arriba."
        exit 1
    fi
}

main "$@"
