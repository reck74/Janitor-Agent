#!/bin/bash

# LEGACY: This script is deprecated. Use setup-honcho.sh for minimal installs.
# For full stack, install individual skills: janitor-vault, janitor-firecrawl, etc.

# =============================================================================
# setup-stack.sh — Central Docker ecosystem orchestrator for Janitor.
# =============================================================================

set -euo pipefail

# ── Path conventions ─────────────────────────────────────────────────────────
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
JANITOR_SOURCE_DIR="${JANITOR_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# ── Aesthetic ─────────────────────────────────────────────────────────────────
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

# ── Docker check (soft-fail — allows cloud-only mode) ──────────────────────────
check_docker() {
    log_info "Checking Docker..."

    if ! command -v docker >/dev/null 2>&1; then
        log_warn "Docker CLI not found. Attempting install..."
        set +e
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh 2>/dev/null && \
            sh /tmp/get-docker.sh 2>/dev/null
        DOCKER_INSTALLED=$?
        set -e
        if [ $DOCKER_INSTALLED -ne 0 ]; then
            log_fail "Docker install failed. Cannot proceed with Local Setup."
            exit 1
        fi
    fi

    # Capturamos la salida para distinguir entre 'daemon muerto' y 'permisos denegados'
    DOCKER_OUTPUT=$(docker info 2>&1)
    if [ $? -ne 0 ]; then
        if echo "$DOCKER_OUTPUT" | grep -q "permission denied"; then
            log_warn "Permission denied on docker.sock. Auto-fixing group permissions..."
            sudo usermod -aG docker "$USER"
            echo -e "\033[1;33m[DevSecOps] Tu usuario ha sido añadido al grupo 'docker'.\033[0m"
            echo -e "\033[1;31m[ACCIÓN REQUERIDA] Linux requiere recargar la sesión. Ejecuta 'newgrp docker' o cierra y vuelve a abrir tu terminal, y luego ejecuta el instalador nuevamente.\033[0m"
            exit 1
        else
            log_warn "Docker daemon not running. Attempting to start service..."
            set +e
            sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null
            sleep 3
            set -e
            if ! docker info >/dev/null 2>&1; then
                log_fail "FATAL: Docker daemon is dead. Please start Docker Desktop or the docker service manually."
                exit 1
            fi
        fi
    fi

    log_ok "Docker is available and running."
}

# ── Infisical key generation ───────────────────────────────────────────────────
generate_infisical_keys() {
    log_info "Generating Infisical keys if missing..."

    local env_file="${JANITOR_HOME}/.env"
    mkdir -p "$(dirname "$env_file")"

    # INFISICAL_ENCRYPTION_KEY — 16 bytes hex
    if ! grep -q "INFISICAL_ENCRYPTION_KEY=" "$env_file" 2>/dev/null; then
        local enc_key
        if command -v openssl >/dev/null 2>&1; then
            enc_key=$(openssl rand -hex 16)
        else
            enc_key=$(python3 -c "import secrets; print(secrets.token_hex(16))")
        fi
        echo "INFISICAL_ENCRYPTION_KEY=${enc_key}" >> "$env_file"
        log_ok "INFISICAL_ENCRYPTION_KEY generated"
    else
        log_info "INFISICAL_ENCRYPTION_KEY already exists — preserving"
    fi

    # INFISICAL_AUTH_SECRET — 32 bytes hex
    if ! grep -q "INFISICAL_AUTH_SECRET=" "$env_file" 2>/dev/null; then
        local auth_secret
        if command -v openssl >/dev/null 2>&1; then
            auth_secret=$(openssl rand -hex 32)
        else
            auth_secret=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        fi
        echo "INFISICAL_AUTH_SECRET=${auth_secret}" >> "$env_file"
        log_ok "INFISICAL_AUTH_SECRET generated"
    else
        log_info "INFISICAL_AUTH_SECRET already exists — preserving"
    fi

    # INFISICAL_ADMIN_EMAIL / INFISICAL_ADMIN_PASSWORD — for bootstrap login
    if ! grep -q "INFISICAL_ADMIN_EMAIL=" "$env_file" 2>/dev/null; then
        echo "INFISICAL_ADMIN_EMAIL=admin@janitor.local" >> "$env_file"
        log_ok "INFISICAL_ADMIN_EMAIL set"
    else
        log_info "INFISICAL_ADMIN_EMAIL already exists — preserving"
    fi
    if ! grep -q "INFISICAL_ADMIN_PASSWORD=" "$env_file" 2>/dev/null; then
        local admin_pw
        if command -v openssl >/dev/null 2>&1; then
            admin_pw=$(openssl rand -hex 16)
        else
            admin_pw=$(python3 -c "import secrets; print(secrets.token_hex(16))")
        fi
        echo "INFISICAL_ADMIN_PASSWORD=${admin_pw}" >> "$env_file"
        log_ok "INFISICAL_ADMIN_PASSWORD generated"
    else
        log_info "INFISICAL_ADMIN_PASSWORD already exists — preserving"
    fi

    return 0
}

# ── Infisical secrets injection ───────────────────────────────────────────────
do_infisical() {
    log_info "Checking Infisical CLI..."

    if ! command -v infisical >/dev/null 2>&1; then
        log_warn "Infisical CLI not found. Attempting auto-installation..."
        if [ -f /etc/debian_version ]; then
            set +e
            curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' -o /tmp/infisical_setup.sh
            sudo -E bash /tmp/infisical_setup.sh < /dev/tty
            sudo apt-get update < /dev/tty
            sudo apt-get install -y infisical < /dev/tty
            set -e
        else
            log_warn "Non-Debian OS detected. Cannot auto-install Infisical CLI."
        fi
    fi

    if command -v infisical >/dev/null 2>&1; then
        log_info "Infisical CLI detected — attempting authentication check..."
        set +e
        infisical secrets sync --path=/janitor --env=prod --format=dotenv --output=/tmp/infisical-check 2>/dev/null
        INFISICAL_AUTH=$?
        set -e

        if [ $INFISICAL_AUTH -ne 0 ]; then
            log_warn "Infisical not authenticated or secrets unavailable — using ~/.janitor/.env fallback."
            return 0
        fi

        log_info "Infisical authenticated — merging secrets into ~/.janitor/.env"
        if infisical export --path=/janitor --env=prod --format=dotenv >> "${JANITOR_HOME}/.env" 2>/dev/null; then
            log_ok "Infisical secrets merged"
        else
            log_warn "Infisical export failed — falling back to ~/.janitor/.env"
        fi
    else
        log_warn "Infisical CLI not available — skipping secrets injection."
    fi

    return 0
}

# ── Honcho env generation ──────────────────────────────────────────────────────
generate_honcho_env() {
    log_info "Generating PostgreSQL credentials and honcho.env..."

    local env_file="${JANITOR_HOME}/.env"
    mkdir -p "$(dirname "$env_file")"

    # ── Honcho PostgreSQL credentials ──────────────────────────────────────────
    if ! grep -q "HONCHO_POSTGRES_USER=" "$env_file" 2>/dev/null; then
        local hongo_user="janitor_$(date +%s | sha256sum | head -c 8)"
        echo "HONCHO_POSTGRES_USER=${hongo_user}" >> "$env_file"
        log_ok "HONCHO_POSTGRES_USER generated"
    else
        log_info "HONCHO_POSTGRES_USER already exists — preserving"
    fi

    if ! grep -q "HONCHO_POSTGRES_PASSWORD=" "$env_file" 2>/dev/null; then
        local hongo_pass
        if command -v openssl >/dev/null 2>&1; then
            hongo_pass=$(openssl rand -base64 24)
        else
            hongo_pass=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        fi
        echo "HONCHO_POSTGRES_PASSWORD=${hongo_pass}" >> "$env_file"
        log_ok "HONCHO_POSTGRES_PASSWORD generated"
    else
        log_info "HONCHO_POSTGRES_PASSWORD already exists — preserving"
    fi

    if ! grep -q "HONCHO_POSTGRES_DB=" "$env_file" 2>/dev/null; then
        echo "HONCHO_POSTGRES_DB=honcho" >> "$env_file"
        log_ok "HONCHO_POSTGRES_DB set"
    else
        log_info "HONCHO_POSTGRES_DB already exists — preserving"
    fi

    # ── Firecrawl PostgreSQL credentials ────────────────────────────────────────
    if ! grep -q "FIRECRAWL_POSTGRES_USER=" "$env_file" 2>/dev/null; then
        local fc_user="janitor_fc_$(date +%s | sha256sum | head -c 8)"
        echo "FIRECRAWL_POSTGRES_USER=${fc_user}" >> "$env_file"
        log_ok "FIRECRAWL_POSTGRES_USER generated"
    else
        log_info "FIRECRAWL_POSTGRES_USER already exists — preserving"
    fi

    if ! grep -q "FIRECRAWL_POSTGRES_PASSWORD=" "$env_file" 2>/dev/null; then
        local fc_pass
        if command -v openssl >/dev/null 2>&1; then
            fc_pass=$(openssl rand -base64 24)
        else
            fc_pass=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        fi
        echo "FIRECRAWL_POSTGRES_PASSWORD=${fc_pass}" >> "$env_file"
        log_ok "FIRECRAWL_POSTGRES_PASSWORD generated"
    else
        log_info "FIRECRAWL_POSTGRES_PASSWORD already exists — preserving"
    fi

    if ! grep -q "FIRECRAWL_POSTGRES_DB=" "$env_file" 2>/dev/null; then
        echo "FIRECRAWL_POSTGRES_DB=firecrawl" >> "$env_file"
        log_ok "FIRECRAWL_POSTGRES_DB set"
    else
        log_info "FIRECRAWL_POSTGRES_DB already exists — preserving"
    fi

    # ── Firecrawl Bull auth key (queue authentication) ────────────────────────────
    if ! grep -q "BULL_AUTH_KEY=" "$env_file" 2>/dev/null; then
        local bull_key
        if command -v openssl >/dev/null 2>&1; then
            bull_key=$(openssl rand -hex 32)
        else
            bull_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        fi
        echo "BULL_AUTH_KEY=${bull_key}" >> "$env_file"
        log_ok "BULL_AUTH_KEY generated"
    else
        log_info "BULL_AUTH_KEY already exists — preserving"
    fi

    # ── Infisical PostgreSQL credentials ────────────────────────────────────────
    if ! grep -q "INFISICAL_POSTGRES_USER=" "$env_file" 2>/dev/null; then
        local inf_user="janitor_inf_$(date +%s | sha256sum | head -c 8)"
        echo "INFISICAL_POSTGRES_USER=${inf_user}" >> "$env_file"
        log_ok "INFISICAL_POSTGRES_USER generated"
    else
        log_info "INFISICAL_POSTGRES_USER already exists — preserving"
    fi

    if ! grep -q "INFISICAL_POSTGRES_PASSWORD=" "$env_file" 2>/dev/null; then
        local inf_pass
        if command -v openssl >/dev/null 2>&1; then
            inf_pass=$(openssl rand -hex 24)
        else
            inf_pass=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
        fi
        echo "INFISICAL_POSTGRES_PASSWORD=${inf_pass}" >> "$env_file"
        log_ok "INFISICAL_POSTGRES_PASSWORD generated"
    else
        log_info "INFISICAL_POSTGRES_PASSWORD already exists — preserving"
    fi

    if ! grep -q "INFISICAL_POSTGRES_DB=" "$env_file" 2>/dev/null; then
        echo "INFISICAL_POSTGRES_DB=infisical_db" >> "$env_file"
        log_ok "INFISICAL_POSTGRES_DB set"
    else
        log_info "INFISICAL_POSTGRES_DB already exists — preserving"
    fi

    # ── Build honcho.env from ~/.janitor/.env ───────────────────────────────────
    log_info "Generating honcho.env from ~/.janitor/.env..."

    local src_env="${JANITOR_HOME}/.env"
    local dst_env="${JANITOR_HOME}/honcho.env"

    if [ ! -f "$src_env" ]; then
        log_warn "No ~/.janitor/.env found — honcho.env will be empty."
        touch "$dst_env"
        return 0
    fi

    # Extract keys from ~/.janitor/.env
    set +e
    MINIMAX_KEY=$(grep -v '^#' "$src_env" | grep -m1 '^MINIMAX_API_KEY=' | cut -d '=' -f2-)
    OPENAI_KEY=$(grep -v '^#' "$src_env" | grep -m1 '^OPENAI_API_KEY=' | cut -d '=' -f2-)
    INFISICAL_ENC=$(grep -v '^#' "$src_env" | grep -m1 '^INFISICAL_ENCRYPTION_KEY=' | cut -d '=' -f2-)
    INFISICAL_AUTH=$(grep -v '^#' "$src_env" | grep -m1 '^INFISICAL_AUTH_SECRET=' | cut -d '=' -f2-)
    set -e

    {
        echo "# Auto-generated by setup-stack.sh — do not edit manually"
        echo "TRANSPORT=anthropic"
        echo "BASE_URL=https://api.minimax.io/anthropic"
        [ -n "$MINIMAX_KEY" ] && echo "LLM_ANTHROPIC_API_KEY=${MINIMAX_KEY}"
        [ -n "$OPENAI_KEY" ] && echo "LLM_OPENAI_API_KEY=${OPENAI_KEY}"
        [ -n "$INFISICAL_ENC" ] && echo "INFISICAL_ENCRYPTION_KEY=${INFISICAL_ENC}"
        [ -n "$INFISICAL_AUTH" ] && echo "INFISICAL_AUTH_SECRET=${INFISICAL_AUTH}"
    } > "$dst_env"

    log_ok "honcho.env written to ${dst_env}"
    return 0
}

# ── Compose file setup ─────────────────────────────────────────────────────────
ensure_compose_file() {
    log_info "Setting up compose files..."

    local compose_src_dir="${JANITOR_SOURCE_DIR}/skills/janitor-onboarding/scripts"
    local compose_dst_dir="${JANITOR_HOME}/docker"

    # Map of source filename → destination filename
    local -A COMPOSE_FILES=(
        ["docker-compose.yml"]="docker-compose.yml"
        ["honcho-compose.yml"]="honcho-compose.yml"
        ["firecrawl-compose.yml"]="firecrawl-compose.yml"
    )

    mkdir -p "$compose_dst_dir"

    local src dst
    for src_name in "${!COMPOSE_FILES[@]}"; do
        dst_name="${COMPOSE_FILES[$src_name]}"
        src="${compose_src_dir}/${src_name}"
        dst="${compose_dst_dir}/${dst_name}"

        if [ ! -f "$src" ]; then
            log_fail "Source compose file not found: ${src}"
            return 1
        fi

        cp -f "$src" "$dst"
        log_ok "Compose file updated at ${dst}"
    done

    return 0
}

# ── Health check helper ────────────────────────────────────────────────────────
wait_for_health() {
    local url="$1"
    local name="$2"
    local timeout="${3:-60}"
    local elapsed=0
    local interval=5

    log_info "Waiting for $name to be healthy (timeout: ${timeout}s)..."

    while [ $elapsed -lt $timeout ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            log_ok "$name is healthy"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -ne "\r  ${CYAN}...${NC} ${elapsed}s / ${timeout}s   "
    done
    echo
    log_warn "$name did not become healthy within ${timeout}s — check logs with: docker compose --env-file ~/.janitor/.env -f ${JANITOR_HOME}/docker/docker-compose.yml logs"
    return 1
}

# ── Stack launch ───────────────────────────────────────────────────────────────
launch_stack() {
    log_info "Launching Janitor stack..."

    local compose_dir="${JANITOR_HOME}/docker"

    local -a STACKS=("infisical" "honcho" "firecrawl")
    local -A COMPOSE_MAP=(
        ["infisical"]="docker-compose.yml"
        ["honcho"]="honcho-compose.yml"
        ["firecrawl"]="firecrawl-compose.yml"
    )

    local stack compose_file
    for stack in "${STACKS[@]}"; do
        compose_file="${compose_dir}/${COMPOSE_MAP[$stack]}"
        if [ ! -f "$compose_file" ]; then
            log_fail "Compose file not found at ${compose_file} — run ensure_compose_file first."
            return 1
        fi
    done

    # ── JIT clone: Honcho source for local build ────────────────────────────────
    local HONCHO_SRC_DIR="${JANITOR_HOME}/src/honcho"
    if [ ! -d "$HONCHO_SRC_DIR" ]; then
        log_info "Cloning Honcho source code for local build..."
        mkdir -p "${JANITOR_HOME}/src"
        set +e
        git clone https://github.com/plastic-labs/honcho.git "$HONCHO_SRC_DIR" 2>&1 | while IFS= read -r line; do
            echo -e "  ${CYAN}…${NC} $line"
        done
        CLONE_RESULT=$?
        set -e
        if [ $CLONE_RESULT -ne 0 ]; then
            log_warn "Honcho clone failed — Honcho stack will not build. Continuing with other stacks."
        else
            log_ok "Honcho source cloned to ${HONCHO_SRC_DIR}"
        fi
    else
        log_info "Honcho source already present at ${HONCHO_SRC_DIR} — skipping clone."
    fi

    # ── JIT clone: Firecrawl source for local DB build ──────────────────────────
    local FIRECRAWL_SRC_DIR="${JANITOR_HOME}/src/firecrawl"
    if [ ! -d "$FIRECRAWL_SRC_DIR" ]; then
        log_info "Cloning Firecrawl source code for local DB build..."
        mkdir -p "${JANITOR_HOME}/src"
        set +e
        git clone https://github.com/mendableai/firecrawl.git "$FIRECRAWL_SRC_DIR" 2>&1 | while IFS= read -r line; do
            echo -e "  ${CYAN}…${NC} $line"
        done
        CLONE_RESULT=$?
        set -e
        if [ $CLONE_RESULT -ne 0 ]; then
            log_warn "Firecrawl clone failed — Firecrawl DB will use generic Postgres. Continuing with other stacks."
        else
            log_ok "Firecrawl source cloned to ${FIRECRAWL_SRC_DIR}"
        fi
else
        log_info "Firecrawl source already present at ${FIRECRAWL_SRC_DIR} — skipping clone."
    fi

    # ── Idempotent patch: align cron.database_name with FIRECRAWL_POSTGRES_DB ──
    # The upstream Dockerfile hardcodes cron.database_name = 'postgres', but pg_cron
    # can only be CREATE EXTENSION'd in the database matching cron.database_name.
    # Our compose sets POSTGRES_DB=${FIRECRAWL_POSTGRES_DB} (typically 'firecrawl'),
    # so the init script fails. This sed aligns them on every launch.
    local FC_DOCKERFILE="${FIRECRAWL_SRC_DIR}/apps/nuq-postgres/Dockerfile"
    if [ -f "$FC_DOCKERFILE" ]; then
        DBNAME=$(grep -oP '^FIRECRAWL_POSTGRES_DB=\K.+' ~/.janitor/.env 2>/dev/null || true)
        if [ -z "$DBNAME" ]; then
            log_fail "FIRECRAWL_POSTGRES_DB not set in ~/.janitor/.env — cannot patch pg_cron config"
            return 1
        fi
        sed -ri "s/(cron\.database_name = ')[^']*(')/\1${DBNAME}\2/" "$FC_DOCKERFILE"
        log_ok "Patched cron.database_name = '${DBNAME}' in ${FC_DOCKERFILE}"
    else
        log_warn "Firecrawl Dockerfile not found at ${FC_DOCKERFILE} — skipping pg_cron patch"
    fi

    local total=${#STACKS[@]}
    local idx=0
    for stack in "${STACKS[@]}"; do
        idx=$((idx + 1))
        compose_file="${compose_dir}/${COMPOSE_MAP[$stack]}"
        log_info "Launching ${stack} stack (${idx}/${total})..."

        set +e
        if grep -q 'build:' "$compose_file" 2>/dev/null; then
            log_info "Building ${stack} from source..."
            docker compose --env-file ~/.janitor/.env -f "$compose_file" build 2>&1 | while IFS= read -r line; do
                echo -e "  ${CYAN}…${NC} $line"
            done
            PULL_RESULT=$?
        else
            docker compose --env-file ~/.janitor/.env -f "$compose_file" pull 2>&1 | while IFS= read -r line; do
                echo -e "  ${CYAN}…${NC} $line"
            done
            PULL_RESULT=$?
        fi
        set -e

        if [ $PULL_RESULT -ne 0 ]; then
            log_warn "Docker pull had issues for ${stack} — continuing with existing images."
        fi

        # ── Volume guard: nuke stale firecrawl-pgdata before first up ──────────
        # The init scripts only run on empty data volumes. If pg_cron was
        # previously missing (cron.database_name mismatch), the volume holds a
        # half-initialized cluster that will never re-run initdb. Removing it
        # forces a clean init on the next `up -d`.
        if [ "$stack" = "firecrawl" ]; then
            docker compose --env-file ~/.janitor/.env -f "$compose_file" down 2>/dev/null || true
            docker volume rm janitor-firecrawl-pgdata 2>/dev/null || true
        fi

        log_info "Starting ${stack} containers..."
        if ! docker compose --env-file ~/.janitor/.env -f "$compose_file" up -d; then
            log_fail "docker compose up failed for ${stack}"
            return 1
        fi
        log_ok "${stack} stack started"

        if [ $idx -lt $total ]; then
            log_info "Waiting 5s before launching next stack..."
            sleep 15
        fi
    done

    # Health checks (non-fatal — warn but don't fail)
    wait_for_health "http://localhost:8080/api/status" "Infisical" 60 || true
    wait_for_health "http://localhost:1973/health" "Honcho" 60 || true
    wait_for_health "http://localhost:1974/v0/health/liveness" "Firecrawl" 180 || true

    log_ok "Stack launched"
    return 0
}

# ── Systemd unit installation ──────────────────────────────────────────────────
install_systemd_unit() {
    log_info "Installing systemd user service..."

    local svc_dir="${HOME}/.config/systemd/user"
    local svc_file="${svc_dir}/janitor-stack.service"

    mkdir -p "$svc_dir"

    cat > "$svc_file" << 'EOF'
[Unit]
Description=Janitor Docker Stack (Infisical + Honcho + Firecrawl)
After=network.target docker.service
Wants=network.target docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/bash -c 'echo "Waiting for Docker daemon..."; while ! docker info >/dev/null 2>&1; do sleep 2; done; echo "Docker ready. Stabilizing networking..."; sleep 5'
WorkingDirectory=%h/.janitor/docker
ExecStart=/bin/bash -c 'cd %h/.janitor/docker && docker compose --env-file %h/.janitor/.env -f docker-compose.yml up -d && sleep 15 && docker compose --env-file %h/.janitor/.env -f honcho-compose.yml up -d && sleep 15 && docker compose --env-file %h/.janitor/.env -f firecrawl-compose.yml up -d'
ExecStop=/bin/bash -c 'cd %h/.janitor/docker && docker compose --env-file %h/.janitor/.env -f firecrawl-compose.yml down 2>/dev/null; docker compose --env-file %h/.janitor/.env -f honcho-compose.yml down 2>/dev/null; docker compose --env-file %h/.janitor/.env -f docker-compose.yml down 2>/dev/null'
TimeoutStartSec=600
TimeoutStopSec=60

[Install]
WantedBy=default.target
EOF

    log_ok "Service file written to ${svc_file}"

    # Reload systemd and enable
    set +e
    systemctl --user daemon-reload 2>/dev/null
    SYSTEMD_RELOAD=$?
    set -e

    if [ $SYSTEMD_RELOAD -eq 0 ]; then
        systemctl --user enable janitor-stack.service 2>/dev/null
        log_ok "janitor-stack.service enabled"
    else
        log_warn "systemd not available — skipping service enable."
    fi

    return 0
}

# ── AgentMemory native install (npm + systemd) ──────────────────────────────────
install_agentmemory() {
    log_info "Installing AgentMemory via npm..."

    if ! command -v npm >/dev/null 2>&1; then
        log_warn "npm not found — skipping AgentMemory installation."
        return 0
    fi

    # Install globally
    set +e
    npm install -g @agentmemory/agentmemory 2>&1 | while IFS= read -r line; do
        echo -e "  ${CYAN}…${NC} $line"
    done
    NPM_RESULT=$?
    set -e

    if [ $NPM_RESULT -ne 0 ]; then
        log_fail "npm install -g @agentmemory/agentmemory failed"
        return 1
    fi
    log_ok "AgentMemory npm package installed"

    # Resolve the global bin directory dynamically
    NPM_GLOBAL_PREFIX="$(npm prefix -g 2>/dev/null)"
    AGENTMEMORY_BIN="${NPM_GLOBAL_PREFIX}/bin/agentmemory"

    if [ ! -x "$AGENTMEMORY_BIN" ]; then
        log_warn "agentmemory binary not found at ${AGENTMEMORY_BIN} — skipping systemd unit."
        return 0
    fi

    # Write systemd user unit
    local svc_dir="${HOME}/.config/systemd/user"
    local svc_file="${svc_dir}/janitor-agentmemory.service"

    mkdir -p "$svc_dir"

    cat > "$svc_file" << EOF
[Unit]
Description=Janitor AgentMemory Server
After=network.target

[Service]
Type=simple
Environment="PATH=${NPM_GLOBAL_PREFIX}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="NODE_PATH=${NPM_GLOBAL_PREFIX}/lib/node_modules"
ExecStart=${AGENTMEMORY_BIN} --no-engine
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

    log_ok "Service file written to ${svc_file}"

    # Reload systemd
    set +e
    systemctl --user daemon-reload 2>/dev/null
    SYSTEMD_RELOAD=$?
    set -e

    if [ $SYSTEMD_RELOAD -eq 0 ]; then
        systemctl --user enable janitor-agentmemory.service 2>/dev/null
        log_ok "janitor-agentmemory.service enabled"
    else
        log_warn "systemd not available — skipping service enable."
    fi

    return 0
}

# ── Playwright install (non-fatal) ─────────────────────────────────────────────
install_playwright() {
    log_info "Checking Playwright installation..."

    if ! command -v playwright >/dev/null 2>&1 && ! command -v npx >/dev/null 2>&1; then
        log_warn "Playwright CLI not found — skipping installation."
        return 0
    fi

    log_info "Installing Playwright with chromium..."
    set +e
    if command -v uv >/dev/null 2>&1; then
        uv run playwright install --with-deps chromium 2>&1 | while IFS= read -r line; do
            echo -e "  ${CYAN}…${NC} $line"
        done
        PW_RESULT=$?
    elif command -v npx >/dev/null 2>&1; then
        npx playwright install --with-deps chromium 2>&1 | while IFS= read -r line; do
            echo -e "  ${CYAN}…${NC} $line"
        done
        PW_RESULT=$?
    else
        log_warn "No uv or npx found — cannot install Playwright."
        PW_RESULT=1
    fi
    set -e

    if [ $PW_RESULT -ne 0 ]; then
        log_warn "Playwright install failed — continuing anyway."
    else
        log_ok "Playwright installed"
    fi

    return 0
}

bootstrap_vault() {
    log_info "Checking Infisical vault bootstrap..."

    if ! curl -sf http://localhost:8080/api/status >/dev/null 2>&1; then
        log_warn "Infisical not responding — skipping vault bootstrap"
        return 0
    fi

    set -a; source "$JANITOR_HOME/.env"; set +a

    if [ -z "${INFISICAL_ADMIN_EMAIL:-}" ] || [ -z "${INFISICAL_ADMIN_PASSWORD:-}" ]; then
        log_warn "INFISICAL_ADMIN_EMAIL or INFISICAL_ADMIN_PASSWORD not set — skipping vault bootstrap"
        return 0
    fi

    INIT_STATUS=$(curl -sf http://localhost:8080/api/v1/admin/config 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('config',{}).get('initialized','false'))" 2>/dev/null || echo "false")

    if [ "$INIT_STATUS" != "true" ]; then
        log_info "Infisical not initialized — running admin signup..."

        SIGNUP_RESP=$(curl -sf -w "\n%{http_code}" -X POST "http://localhost:8080/api/v1/admin/signup" \
            -H "Content-Type: application/json" \
            -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\",\"firstName\":\"Janitor\",\"lastName\":\"Admin\"}" 2>/dev/null)
        SIGNUP_STATUS=$(echo "$SIGNUP_RESP" | tail -1)
        SIGNUP_BODY=$(echo "$SIGNUP_RESP" | sed '$d')

        if [ "$SIGNUP_STATUS" = "200" ] || [ "$SIGNUP_STATUS" = "201" ]; then
            log_ok "Infisical admin account created"
        elif echo "$SIGNUP_BODY" | grep -qi "already.*set up"; then
            log_info "Infisical admin already exists"
        else
            log_warn "Infisical admin signup failed (HTTP $SIGNUP_STATUS)"
            echo "$SIGNUP_BODY" | head -3
            return 0
        fi

        log_info "Waiting for Infisical to be ready (up to 60s)..."
        READY=false
        for i in $(seq 1 30); do
            sleep 2
            LOGIN_TEST=$(curl -sf --max-time 5 -X POST "http://localhost:8080/api/v3/auth/login" \
                -H "Content-Type: application/json" \
                -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)
            if echo "$LOGIN_TEST" | grep -q '"accessToken"'; then
                READY=true
                break
            fi
            log_info "Waiting for Infisical login readiness (attempt $i/30)..."
        done

        if [ "$READY" != "true" ]; then
            log_warn "Infisical login not ready after signup — skipping vault bootstrap"
            return 0
        fi
        log_ok "Infisical ready for vault bootstrap"
    fi

    LOGIN_BODY=$(curl -sf -X POST "http://localhost:8080/api/v3/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"${INFISICAL_ADMIN_EMAIL}\",\"password\":\"${INFISICAL_ADMIN_PASSWORD}\"}" 2>/dev/null)
    ACCESS_TOKEN=$(echo "$LOGIN_BODY" | grep -o '"accessToken"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '[^"]*"$' | tr -d '"')
    if [ -z "$ACCESS_TOKEN" ]; then
        log_warn "Infisical login failed — skipping vault bootstrap"
        return 0
    fi

    ORG_ID=$(curl -sf -H "Authorization: Bearer ${ACCESS_TOKEN}" "http://localhost:8080/api/v1/organization" 2>/dev/null | jq -r '.organizations[0].id // empty' 2>/dev/null)
    if [ -z "$ORG_ID" ]; then
        log_warn "No Infisical organization found — skipping vault bootstrap"
        return 0
    fi

    SELECT_BODY=$(curl -sf -X POST "http://localhost:8080/api/v3/auth/select-organization" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -d "{\"organizationId\":\"${ORG_ID}\"}" 2>/dev/null)
    ORG_TOKEN=$(echo "$SELECT_BODY" | jq -r '.token // empty' 2>/dev/null)
    if [ -z "$ORG_TOKEN" ]; then
        log_warn "Infisical org-scoped token failed — skipping vault bootstrap"
        return 0
    fi

    PROJECT_EXISTS=$(curl -sf -H "Authorization: Bearer ${ORG_TOKEN}" "http://localhost:8080/api/v1/projects" 2>/dev/null | jq -r '.projects[] | select(.name == "janitor-secrets") | .id // empty' 2>/dev/null)
    if [ -n "$PROJECT_EXISTS" ]; then
        log_ok "Vault already initialized — skipping bootstrap"
        return 0
    fi

    log_info "Running vault-bootstrap.sh..."
    bash "$JANITOR_SOURCE_DIR/scripts/vault-bootstrap.sh"
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}═══ Janitor Stack Setup ═══${NC}"

    check_docker
    generate_infisical_keys
    do_infisical
    generate_honcho_env
    ensure_compose_file || { log_fail "ensure_compose_file failed"; exit 1; }
    launch_stack
    install_playwright
    install_systemd_unit
    # install_agentmemory  # Deshabilitado: AgentMemory es CLI interactivo, no daemon
    bootstrap_vault

    echo
    log_ok "Janitor stack setup complete!"
    log_info "Manage with: docker compose --env-file ~/.janitor/.env -f ${JANITOR_HOME}/docker/docker-compose.yml [start|stop|logs]"
    log_info "Or use the systemd service: systemctl --user [start|stop] janitor-stack"
}

main "$@"