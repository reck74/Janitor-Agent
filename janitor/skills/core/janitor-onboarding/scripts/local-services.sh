#!/usr/bin/env bash
# Janitor local services — compatibility wrapper around `janitor services`.
#
# Kept so pre-1.0 docs and muscle memory keep working. It acts on the
# janitor-* containers by name, never recreates compose projects and never
# deletes volumes.
#
# Usage:
#   bash janitor/skills/core/janitor-onboarding/scripts/local-services.sh start|stop|status|restart
#   bash janitor/skills/core/janitor-onboarding/scripts/local-services.sh logs [service]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
SERVICES=(honcho firecrawl)

janitor_services() {
    if command -v janitor >/dev/null 2>&1; then
        janitor services "$@"
    else
        (cd "$REPO_ROOT" && python3 -m janitor.services "$@")
    fi
}

ACTION="${1:-}"
SERVICE="${2:-}"

case "$ACTION" in
    start|stop)
        for svc in "${SERVICES[@]}"; do
            janitor_services "$ACTION" "$svc" || true
        done
        ;;
    restart)
        for svc in "${SERVICES[@]}"; do
            janitor_services stop "$svc" || true
            janitor_services start "$svc" || true
        done
        ;;
    status)
        janitor_services status
        ;;
    logs)
        if [ -n "$SERVICE" ]; then
            docker logs -f "janitor-${SERVICE}"
        else
            for c in $(docker ps --filter "name=janitor-" --format "{{.Names}}"); do
                echo "=== $c ==="
                docker logs --tail 20 "$c" 2>/dev/null || true
            done
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|logs [service]}"
        echo "Prefer: janitor services {list|status|deploy|start|stop|uninstall}"
        exit 1
        ;;
esac
