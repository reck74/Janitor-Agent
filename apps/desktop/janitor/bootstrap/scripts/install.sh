#!/usr/bin/env bash
# Progress protocol adapter backed exclusively by the Janitor installer.
set -euo pipefail
stage=""; commit=""; branch="main"; install_root=""; janitor_home=""; manifest=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest) manifest=1; shift ;;
        --stage) stage="$2"; shift 2 ;;
        --commit) commit="$2"; shift 2 ;;
        --branch) branch="$2"; shift 2 ;;
        --dir) install_root="$2"; shift 2 ;;
        --hermes-home) janitor_home="$2"; shift 2 ;;
        --non-interactive|--json) shift ;;
        *) echo "Unknown bootstrap argument: $1" >&2; exit 2 ;;
    esac
done
if [[ "$manifest" -eq 1 ]]; then
    printf '%s\n' '{"protocol_version":1,"stages":[{"name":"runtime","title":"Install Janitor runtime","category":"runtime","needs_user_input":false},{"name":"profile","title":"Configure MiniMax and Honcho","category":"configuration","needs_user_input":false}]}'
    exit 0
fi
[[ -n "$install_root" && -n "$janitor_home" ]] || { echo "Missing runtime/home paths" >&2; exit 2; }
[[ "$stage" == runtime || "$stage" == profile ]] || { echo "Unknown Janitor stage: $stage" >&2; exit 2; }
temp_script=""
finish() {
    local code="$?"
    [[ -z "$temp_script" ]] || rm -f "$temp_script"
    if [[ "$code" -eq 0 ]]; then
        printf '{"stage":"%s","ok":true}\n' "$stage"
    elif [[ "$stage" == profile ]]; then
        printf '{"stage":"profile","ok":false,"error":"Janitor needs MiniMax and local or cloud Honcho configuration. Open ~/.janitor/.env (or JANITOR_HOME/.env), set the required credentials, and retry setup. See the Desktop setup log for details."}\n'
    else
        printf '{"stage":"runtime","ok":false,"error":"Janitor runtime installation failed. Check Docker access, network connectivity and the Desktop setup log, then retry."}\n'
    fi
    return "$code"
}
trap finish EXIT
if [[ "$stage" == profile ]]; then
    JANITOR_HOME="$janitor_home" HERMES_HOME="$janitor_home" bash "$install_root/scripts/bootstrap.sh" \
        --stage profile --honcho-mode "${JANITOR_HONCHO_MODE:-local}" --non-interactive --dir "$install_root" --hermes-home "$janitor_home" --json >&2
    exit 0
fi
ref="${commit:-$branch}"
[[ "$ref" =~ ^[a-zA-Z0-9._-]+$ && "$ref" != -* ]] || { echo "Invalid bootstrap ref" >&2; exit 2; }
temp_script="$(mktemp "${TMPDIR:-/tmp}/janitor-bootstrap.XXXXXXXX.sh")"
curl --fail --location --silent --show-error --connect-timeout 15 --max-time 120 \
    "https://raw.githubusercontent.com/reck74/Janitor-Agent/${ref}/scripts/bootstrap.sh" -o "$temp_script"
args=(--stage runtime --non-interactive --dir "$install_root" --hermes-home "$janitor_home" --json)
[[ -z "$commit" ]] || args+=(--commit "$commit")
JANITOR_HOME="$janitor_home" HERMES_HOME="$janitor_home" bash "$temp_script" "${args[@]}" >&2
