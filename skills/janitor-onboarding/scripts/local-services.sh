#!/usr/bin/env bash
# Compatibility helper: operate only on an explicitly selected installed stack.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
home="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
action="${1:-status}"
service="${2:-honcho}"
case "$action" in
    --help|-h) echo 'Usage: local-services.sh {status|start|stop|restart|logs} [honcho|firecrawl]'; exit 0 ;;
    status)
        docker info >/dev/null
        docker ps --filter 'name=janitor-' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
        exit 0 ;;
    start|stop|restart|logs) ;;
    *) echo "Unknown action: $action" >&2; exit 2 ;;
esac
case "$service" in honcho|firecrawl) ;; *) echo 'Choose honcho or firecrawl explicitly.' >&2; exit 2 ;; esac
export JANITOR_HOME="$home" HERMES_HOME="$home"
if [[ "$action" == start ]]; then
    # Firecrawl is never activated by a bare legacy `start` invocation.
    exec bash "$root/skills/janitor-$service/scripts/deploy.sh"
fi
compose="$home/docker/$service-compose.yml"
environment="$home/docker/$service.env"
[[ "$service" != honcho ]] || environment="$home/honcho.env"
[[ -f "$compose" && -f "$environment" ]] || { echo "Configure janitor-$service first; no services changed." >&2; exit 1; }
args=(compose --project-name "janitor-$service" --env-file "$environment" -f "$compose")
case "$action" in
    stop) exec docker "${args[@]}" stop ;;
    restart) exec docker "${args[@]}" up -d --force-recreate --wait --wait-timeout 180 ;;
    logs) exec docker "${args[@]}" logs --tail 100 ;;
esac
