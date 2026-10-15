#!/usr/bin/env bash
# Janitor's public installer and Desktop stage protocol. Upstream owns PM acquisition.
set -euo pipefail
export JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
export HERMES_HOME="${HERMES_HOME:-$JANITOR_HOME}"
repo_url="${JANITOR_REPO_URL:-https://github.com/reck74/Janitor-Agent.git}"
install_dir="$JANITOR_HOME/janitor-core"
commit=""; branch="main"; stage=""; json=false; non_interactive=false; honcho_mode=""; explicit_dir=false; explicit_branch=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest)
            printf '%s\n' '{"protocol_version":1,"stages":[{"name":"prerequisites","title":"Docker y dependencias","category":"runtime","needs_user_input":false},{"name":"repository","title":"Descargar Janitor","category":"runtime","needs_user_input":false},{"name":"venv","title":"Python administrado","category":"runtime","needs_user_input":false},{"name":"python-deps","title":"Dependencias Janitor","category":"runtime","needs_user_input":false},{"name":"products","title":"Interfaz y comandos","category":"runtime","needs_user_input":false},{"name":"config","title":"MiniMax y Honcho","category":"configuration","needs_user_input":true},{"name":"complete","title":"Verificar instalación","category":"runtime","needs_user_input":false}]}'
            exit 0 ;;
        --dir|--hermes-home|--commit|--branch|--stage|--honcho-mode)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { echo "$1 needs a value" >&2; exit 2; }
            case "$1" in
                --dir) install_dir="$2"; explicit_dir=true ;;
                --hermes-home) export JANITOR_HOME="$2" HERMES_HOME="$2" ;;
                --commit) commit="$2" ;;
                --branch) branch="$2"; explicit_branch=true ;;
                --stage) stage="$2" ;;
                --honcho-mode) honcho_mode="$2" ;;
            esac
            shift 2 ;;
        --non-interactive|--skip-setup) non_interactive=true; shift ;;
        --json) json=true; shift ;;
        --verbose) shift ;;
        --help|-h) echo 'Usage: bootstrap.sh [--dir PATH] [--hermes-home PATH] [--commit SHA | --branch NAME] [--non-interactive] [--honcho-mode local|cloud] [--manifest | --stage NAME] [--json]'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ "$explicit_dir" == true ]] || install_dir="$JANITOR_HOME/janitor-core"
[[ -z "$commit" || "$commit" =~ ^[a-fA-F0-9]{40}$ ]] || { echo '--commit must be a full SHA' >&2; exit 2; }
case "$stage" in ''|prerequisites|repository|venv|python-deps|products|config|setup|gateway|complete|runtime|profile) ;; *) echo "Unknown stage: $stage" >&2; exit 2 ;; esac
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
temporary=""
cleanup() { [[ -z "$temporary" ]] || rm -rf -- "$temporary"; }
trap cleanup EXIT
if [[ -f "$script_dir/install.sh" && -f "$script_dir/../janitor_cli.py" ]]; then
    upstream_installer="$script_dir/install.sh"
else
    temporary="$(mktemp -d)"
    # The public bootstrap must resolve a Janitor stable release, never upstream/main.
    ref="${commit:-v1.0.0}"
    upstream_installer="$temporary/install.sh"
    curl --fail --location --silent --show-error "https://raw.githubusercontent.com/reck74/Janitor-Agent/$ref/scripts/install.sh" -o "$upstream_installer"
fi
if [[ -z "$commit" && "$explicit_branch" == false && "$stage" != @(products|config|setup|profile|complete|gateway) ]]; then
    commit="$(git ls-remote "$repo_url" 'refs/tags/v1.0.0^{}' refs/tags/v1.0.0 | awk 'END {print $1}')"
    [[ "$commit" =~ ^[a-fA-F0-9]{40}$ ]] || { echo 'Janitor stable v1.0.0 is unavailable; choose an explicit --commit for development.' >&2; exit 1; }
fi
upstream_args=(--dir "$install_dir" --hermes-home "$HERMES_HOME" --branch "$branch" --non-interactive --skip-browser --skip-computer-use)
[[ -z "$commit" ]] || upstream_args+=(--commit "$commit")
export HERMES_REPO_URL="$repo_url"
docker_gate() {
    if ! command -v docker >/dev/null 2>&1; then
        if [[ "$non_interactive" == true ]]; then
            echo 'Docker is required. Install Docker and retry.' >&2; return 1
        fi
        printf 'Docker is required. Install it using get.docker.com? [y/N] ' >/dev/tty
        read -r answer </dev/tty
        [[ "$answer" == y || "$answer" == Y ]] || return 1
        local download
        download="$(mktemp)"
        curl --fail --location --silent --show-error https://get.docker.com -o "$download"
        sudo sh "$download" </dev/tty
        rm -f "$download"
    fi
    docker info >/dev/null 2>&1 || { echo 'Docker is unavailable. Start it and grant this user access, then retry.' >&2; return 1; }
}
run_stage() {
    case "$1" in
        prerequisites) docker_gate; bash "$upstream_installer" "${upstream_args[@]}" --stage prerequisites ;;
        repository|venv|python-deps) bash "$upstream_installer" "${upstream_args[@]}" --stage "$1" ;;
        products)
            # PM publishes private launchers only; preserve any existing global Hermes command.
            selected_python="$(
                set -- "${upstream_args[@]}" --manifest
                source "$upstream_installer"
                bootstrap_python >&2
                printf '%s\n' "$boot_py"
            )"
            "$selected_python" - "$install_dir" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
from hermes_cli._launchers import ensure_install_launchers
if not ensure_install_launchers(root, root / '.hermes/bin'):
    raise SystemExit('PM launchers are unavailable')
PY
            "$install_dir/scripts/janitor" --run-module janitor_ext.install --publish-only
            "$install_dir/scripts/janitor" --run-module janitor_ext.products ;;
        config|setup|profile)
            local options=()
            [[ "$non_interactive" != true ]] || options+=(--non-interactive)
            [[ -z "$honcho_mode" ]] || options+=(--honcho-mode "$honcho_mode")
            bash "$install_dir/scripts/janitor-install.sh" "${options[@]}" ;;
        gateway) echo 'Gateway service installation is explicit: janitor gateway install' ;;
        complete)
            "$install_dir/scripts/janitor" --run-module janitor_ext.install --home "$HERMES_HOME" --verify-honcho
            "$install_dir/scripts/janitor" --version ;;
        runtime)
            for part in prerequisites repository venv python-deps products; do run_stage "$part"; done ;;
    esac
}
stage_result() {
    local result="$?"
    if [[ "$json" == true ]]; then
        printf '{"ok":%s,"stage":"%s","skipped":false,"reason":"%s"}\n' "$([[ $result == 0 ]] && echo true || echo false)" "$stage" "$([[ $result == 0 ]] || echo 'stage failed; see installer output')"
    fi
    cleanup
    return "$result"
}
if [[ -n "$stage" ]]; then
    trap stage_result EXIT
    run_stage "$stage"
else
    for stage in prerequisites repository venv python-deps products config complete; do run_stage "$stage"; done
fi
