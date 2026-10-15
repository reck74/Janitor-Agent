#!/usr/bin/env bash
# Source this helper to export N8N_COOKIE_JAR. PM owns the interpreter and dependencies.
janitor_n8n_auth() {
    local helper_source helper_root launcher cookie
    helper_source="$(readlink -f "${BASH_SOURCE[0]}")"
    helper_root="$(cd "$(dirname "$helper_source")/../../.." && pwd)"
    launcher="$helper_root/scripts/janitor"
    [[ -x "$launcher" ]] || launcher="$(command -v janitor || true)"
    [[ -n "$launcher" && -x "$launcher" ]] || { echo 'Install/repair Janitor before authenticating n8n.' >&2; return 1; }
    cookie="$(JANITOR_HOME="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}" "$launcher" --run-module janitor_ext.service_auth)" || return $?
    export N8N_COOKIE_JAR="$cookie"
    printf '%s\n' "$cookie"
}
janitor_n8n_auth || { return 1 2>/dev/null || exit 1; }
