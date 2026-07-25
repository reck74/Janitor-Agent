#!/bin/bash
# =============================================================================
# janitor-onboarding: local-services.sh
# Manages Honcho and Firecrawl containers via their individual skill compose files.
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
SKILLS_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

HONCHO_COMPOSE="${SKILLS_DIR}/janitor-honcho/scripts/honcho-compose.yml"
FIRECRAWL_COMPOSE="${SKILLS_DIR}/janitor-firecrawl/scripts/firecrawl-compose.yml"

# Aesthetic
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

available_compose_files() {
    local files=()
    [ -f "$HONCHO_COMPOSE" ] && files+=("$HONCHO_COMPOSE")
    [ -f "$FIRECRAWL_COMPOSE" ] && files+=("$FIRECRAWL_COMPOSE")
    echo "${files[@]}"
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
    return 1
}

# ── Actions ────────────────────────────────────────────────────────────────────
do_start() {
    check_docker

    log_info "Starting Janitor local services..."

    if [ -f "$HONCHO_COMPOSE" ]; then
        log_info "Starting Honcho..."
        docker compose -f "$HONCHO_COMPOSE" -p janitor up -d || {
            log_warn "Honcho start failed — may already be running or needs setup"
        }
        wait_for_health "http://localhost:1973/health" "Honcho" 60 || true
    else
        log_warn "Honcho compose not found at $HONCHO_COMPOSE"
        log_warn "Run: bash skills/janitor-honcho/scripts/setup-honcho.sh"
    fi

    if [ -f "$FIRECRAWL_COMPOSE" ]; then
        log_info "Starting Firecrawl..."
        docker compose -f "$FIRECRAWL_COMPOSE" -p janitor up -d || {
            log_warn "Firecrawl start failed — may already be running or needs setup"
        }
        wait_for_health "http://localhost:1974/v0/health/liveness" "Firecrawl" 60 || true
    else
        log_warn "Firecrawl compose not found at $FIRECRAWL_COMPOSE"
        log_warn "Run: bash skills/janitor-firecrawl/scripts/deploy.sh"
    fi

    echo ""
    log_ok "Local services start complete"
    echo ""
    echo "  To view logs: $0 logs"
    echo "  To stop:      $0 stop"
}

do_stop() {
    check_docker
    log_info "Stopping Janitor local services..."

    for compose in $HONCHO_COMPOSE $FIRECRAWL_COMPOSE; do
        if [ -f "$compose" ]; then
            docker compose -f "$compose" -p janitor down 2>/dev/null || true
        fi
    done

    log_ok "Local services stopped (volumes preserved)"
}

do_status() {
    check_docker
    echo ""
    echo -e "${BOLD}Janitor Local Services Status${NC}"
    echo ""

    for port_name in "1973:Honcho:/health" "1974:Firecrawl:/v0/health/liveness"; do
        local port="${port_name%%:*}"
        local rest="${port_name#*:}"
        local name="${rest%%:*}"
        local endpoint="${rest##*:}"
        if curl -sf "http://localhost:${port}${endpoint}" >/dev/null 2>&1; then
            echo -e "  ${GREEN}●${NC} ${name} (localhost:${port}) — healthy"
        else
            echo -e "  ${RED}●${NC} ${name} (localhost:${port}) — not responding"
        fi
    done
    echo ""
    docker ps --filter "name=janitor-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
    echo ""
}

do_logs() {
    check_docker
    local service="${1:-}"
    docker logs -f "janitor-${service}" 2>/dev/null || {
        log_warn "No container named 'janitor-${service}' — showing all Janitor logs"
        for c in $(docker ps --filter "name=janitor-" --format "{{.Names}}" 2>/dev/null); do
            echo -e "\n${CYAN}=== $c ===${NC}"
            docker logs --tail 20 "$c" 2>/dev/null || true
        done
    }
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
