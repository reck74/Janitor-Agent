#!/usr/bin/env bash
# =========================================================
# Janitor — LightRAG Deploy Script
#
# Despliega LightRAG self-host con Docker Compose (3 containers:
# lightrag app + postgres pgvector + Ollama embeddings). Idempotente:
# - No regenera credenciales si lightrag.env ya existe (preserva volumenes).
# - No duplica LIGHTRAG_API_URL en ~/.janitor/.env.
#
# Embeddings aislados: Ollama propio, sin red ni servicio Honcho.
#
# Modelo: scripts/deploy.sh de janitor-firecrawl y setup-n8n.sh.
# =========================================================
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
        # Current LightRAG requires TOKEN_SECRET and LLM_BINDING_API_KEY.
        # Back up before filling missing fields or moving the retired embedding endpoint.
        if ! grep -q '^TOKEN_SECRET=.' "$ENV_FILE" || ! grep -q '^LLM_BINDING_API_KEY=.' "$ENV_FILE" || grep -q '^EMBEDDING_BINDING_HOST=http://janitor-honcho-ollama:11434$' "$ENV_FILE" || ! grep -q '^POSTGRES_HOST=.' "$ENV_FILE" || ! grep -q '^POSTGRES_PORT=.' "$ENV_FILE" || ! grep -q '^POSTGRES_USER=.' "$ENV_FILE" || ! grep -q '^POSTGRES_DATABASE=.' "$ENV_FILE"; then
            cp -p "$ENV_FILE" "$ENV_FILE.pre-isolated-embeddings.$(date -u +%Y%m%dT%H%M%S%N).bak"
        fi
        if ! grep -q '^TOKEN_SECRET=.' "$ENV_FILE"; then
            printf '\nTOKEN_SECRET=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"
        fi
        if ! grep -q '^LLM_BINDING_API_KEY=.' "$ENV_FILE"; then
            local previous_key
            previous_key=$(grep '^LLM_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)
            [[ -n "$previous_key" ]] || previous_key="${MINIMAX_API_KEY:-}"
            [[ -n "$previous_key" ]] || { log_fail "Configure LLM_BINDING_API_KEY in $ENV_FILE"; return 1; }
            printf '\nLLM_BINDING_API_KEY=%s\n' "$previous_key" >> "$ENV_FILE"
        fi
        if grep -q '^EMBEDDING_BINDING_HOST=http://janitor-honcho-ollama:11434$' "$ENV_FILE"; then
            sed -i 's|^EMBEDDING_BINDING_HOST=.*|EMBEDDING_BINDING_HOST=http://janitor-lightrag-embeddings:11434|; s|^EMBEDDING_MODEL=.*|EMBEDDING_MODEL=nomic-embed-text:v1.5|' "$ENV_FILE"
        fi
        # The application uses POSTGRES_DATABASE; POSTGRES_DB belongs to the DB image.
        local field
        for field in POSTGRES_HOST=lightrag-db POSTGRES_PORT=5432 POSTGRES_USER=lightrag POSTGRES_DATABASE=lightrag; do
            if ! grep -q "^${field%%=*}=." "$ENV_FILE"; then
                printf '\n%s\n' "$field" >> "$ENV_FILE"
            fi
        done
        return 0
    fi

    : "${MINIMAX_API_KEY:?MINIMAX_API_KEY is required for fresh LightRAG deployment}"
    log_info "Generando credenciales aleatorias (openssl rand)..."
    mkdir -p "$DOCKER_DIR"

    local pg_pass api_key auth_password auth_account token_secret
    pg_pass=$(openssl rand -hex 16)
    api_key=$(openssl rand -hex 32)
    token_secret=$(openssl rand -hex 32)
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
POSTGRES_HOST=lightrag-db
POSTGRES_PORT=5432
POSTGRES_USER=lightrag
POSTGRES_DATABASE=lightrag
POSTGRES_PASSWORD=${pg_pass}

# --- LightRAG auth ---
# API key para llamadas REST (header X-API-Key)
LIGHTRAG_API_KEY=${api_key}
# WebUI: user 'admin' + password generado
AUTH_ACCOUNTS=${auth_account}
TOKEN_SECRET=${token_secret}

# --- Storage backends ---
# NetworkXStorage (in-memory + JSON files), NO PGGraphStorage — pgvector:pg18
# no incluye Apache AGE y PGGraphStorage crashea con
# 'function create_graph(unknown) does not exist'.
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

# --- LLM (MiniMax OpenAI-compatible endpoint) ---
LLM_BINDING=openai
LLM_BINDING_HOST=https://api.minimax.io/v1
LLM_MODEL=MiniMax-M2.7
LLM_BINDING_API_KEY=${MINIMAX_API_KEY}

# --- Embeddings (isolated local Ollama) ---
EMBEDDING_BINDING=ollama
EMBEDDING_BINDING_HOST=http://janitor-lightrag-embeddings:11434
EMBEDDING_MODEL=nomic-embed-text:v1.5
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
    docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" pull

    "$JANITOR_SERVICE_PYTHON" -m janitor_ext.volumes --compose "$COMPOSE_DST" --env-file "$ENV_FILE"
    docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" up -d --wait --wait-timeout 180 lightrag-db lightrag-embeddings
    docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" exec -T lightrag-embeddings ollama pull nomic-embed-text:v1.5
    log_info "Levantando stack (docker compose up -d)..."
    if ! docker compose -f "$COMPOSE_DST" --env-file "$ENV_FILE" up -d; then
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
    echo -e "Nota: Las consultas dependen de la latencia del modelo configurado."
    echo -e "      Esto es normal, no un timeout."
}

# ─── Main ─────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}═══ Janitor — LightRAG Deploy ═══${NC}"
    echo ""
    check_docker
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
