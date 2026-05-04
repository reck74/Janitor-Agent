#!/bin/bash
# =============================================================================
# janitor-onboarding: local-services.sh
# Spins up Honcho and Firecrawl containers via docker compose.
# Called by the janitor-onboarding SKILL or directly by the user.
#
# Usage:
#   bash skills/janitor-onboarding/scripts/local-services.sh start
#   bash skills/janitor-onboarding/scripts/local-services.sh stop
#   bash skills/janitor-onboarding/scripts/local-services.sh status
#   bash skills/janitor-onboarding/scripts/local-services.sh logs [service]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
COMPOSE_PROJECT="janitor"

# Aesthetic
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

# ── Guards ────────────────────────────────────────────────────────────────────
check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log_fail "Docker not found. Install Docker first: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log_fail "Docker daemon not running. Start it with: sudo systemctl start docker"
        exit 1
    fi
}

check_compose_file() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_fail "docker-compose.yml not found at $COMPOSE_FILE"
        exit 1
    fi
}

# ── Health check helpers ───────────────────────────────────────────────────────
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
    log_fail "$name failed to become healthy within ${timeout}s"
    log_warn "Check logs with: $0 logs $name"
    return 1
}

# ── Actions ────────────────────────────────────────────────────────────────────
do_start() {
    check_docker
    check_compose_file

    log_info "Starting Janitor local services (Honcho + Firecrawl)..."

    # Pull latest images first
    log_info "Pulling latest images..."
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" pull || {
        log_warn "Image pull failed — proceeding anyway (image may already exist)"
    }

    # Start containers
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d || {
        log_fail "Failed to start containers"
        exit 1
    }

    # Wait for health
    local honcho_port="${HONCHO_PORT:-1973}"
    local firecrawl_port="${FIRECRAWL_PORT:-1974}"

    wait_for_health "http://localhost:${honcho_port}/health" "Honcho" 60 || true
    wait_for_health "http://localhost:${firecrawl_port}/health" "Firecrawl" 60 || true

    echo ""
    log_ok "Local services started"
    echo "  Honcho:    http://localhost:${honcho_port}"
    echo "  Firecrawl: http://localhost:${firecrawl_port}"
    echo ""
    echo "  To view logs: $0 logs"
    echo "  To stop:      $0 stop"
}

do_stop() {
    check_docker
    log_info "Stopping Janitor local services..."
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" down || {
        log_warn "Some containers may not have stopped cleanly"
    }
    log_ok "Local services stopped (volumes preserved)"
}

do_status() {
    check_docker
    echo ""
    echo -e "${BOLD}Janitor Local Services Status${NC}"
    echo ""
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps || {
        log_fail "Could not retrieve status"
    }
    echo ""

    # Show health for each service
    for port in 1973 1974; do
        local name
        [ "$port" = "1973" ] && name="Honcho" || name="Firecrawl"
        if curl -sf "http://localhost:${port}/health" >/dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} ${name} (localhost:${port}) — healthy"
        else
            echo -e "  ${RED}●${NC} ${name} (localhost:${port}) — not responding"
        fi
    done
    echo ""
}

do_logs() {
    check_docker
    local service="${1:-}"
    if [ -n "$service" ]; then
        docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" logs -f "$service" || {
            log_fail "No logs available for service: $service"
        }
    else
        docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" logs -f
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
ACTION="${1:-}"
SERVICE="${2:-}"

case "$ACTION" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs "$SERVICE"
        ;;
    restart)
        do_stop
        sleep 2
        do_start
        ;;
    *)
        echo "Usage: $0 {start|stop|status|logs [service]|restart}"
        echo ""
        echo "Commands:"
        echo "  start              Start Honcho and Firecrawl containers"
        echo "  stop               Stop containers (preserve volumes)"
        echo "  status             Show running containers and health"
        echo "  logs [service]     Tail logs (optionally for a specific service)"
        echo "  restart            Stop then start again"
        exit 1
        ;;
esac