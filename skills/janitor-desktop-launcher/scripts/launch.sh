#!/usr/bin/env bash
# Launch a verified local Janitor Desktop artifact. Diagnostics never change files.
set -euo pipefail
unpacked=0; headless=0; background=0; diagnostic=""; app_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --unpacked) unpacked=1 ;;
        --headless) headless=1 ;;
        --background) background=1 ;;
        --version) diagnostic=version ;;
        --print-path) diagnostic=path ;;
        --) shift; app_args=("$@"); break ;;
        -h|--help)
            printf '%s\n' 'Janitor Desktop launcher' \
                'Usage: launch.sh [--unpacked] [--headless] [--background] [--version|--print-path] [-- APP_ARGS]' \
                'Set JANITOR_DESKTOP_DIR to select a build; JANITOR_HOME selects the profile root.'
            exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done
script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
janitor_home="${HERMES_HOME:-${JANITOR_HOME:-$HOME/.janitor}}"
case "$(uname -m)" in
    x86_64|amd64) architecture=x86_64 ;;
    aarch64|arm64) architecture=arm64 ;;
    *) printf 'Unsupported Janitor Desktop architecture\n' >&2; exit 1 ;;
esac
candidates=("${janitor_home}/janitor-core/apps/desktop" "${janitor_home}/apps/desktop" "${script_root}/apps/desktop" "$(pwd)/apps/desktop")
if [[ -n "${JANITOR_DESKTOP_DIR:-}" ]]; then candidates=("$JANITOR_DESKTOP_DIR"); fi
valid_metadata() {
    python3 - "$1" "$2" <<'PYCODE'
import json, pathlib, re, sys
try:
    artifact, filename = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    metadata = json.loads(filename.read_text())
    version = metadata['janitorVersion']
    assert re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version)
    assert isinstance(metadata['upstreamVersion'], str) and metadata['upstreamVersion']
    if artifact.suffix == '.AppImage':
        assert artifact.name.startswith('janitor-desktop-' + version + '-linux-')
        assert metadata['artifact'] == artifact.name
except (OSError, ValueError, KeyError, AssertionError):
    raise SystemExit(1)
PYCODE
}
binary=""; selected=""; metadata=""
for candidate in "${candidates[@]}"; do
    if [[ "$unpacked" -eq 1 ]]; then
        directory=linux-unpacked
        [[ "$architecture" != arm64 ]] || directory=linux-arm64-unpacked
        file="${candidate}/release/${directory}/janitor-desktop"
        [[ -f "$file" && -x "$file" ]] || continue
        candidate_metadata="${candidate}/release/janitor-release.json"
        valid_metadata "$file" "$candidate_metadata" || continue
    else
        shopt -s nullglob
        files=("${candidate}/release/"janitor-desktop-*-linux-"${architecture}".AppImage)
        shopt -u nullglob
        [[ ${#files[@]} -gt 0 ]] || continue
        file=""
        while IFS= read -r artifact; do
            [[ -f "$artifact" && -x "$artifact" ]] || continue
            valid_metadata "$artifact" "${artifact}.json" || continue
            file="$artifact"; candidate_metadata="${artifact}.json"; break
        done < <(printf '%s\n' "${files[@]}" | LC_ALL=C sort -Vr)
        [[ -n "$file" ]] || continue
    fi
    binary="$file"; selected="$candidate"; metadata="$candidate_metadata"; break
done
if [[ -z "$binary" ]]; then
    printf '%s\n' 'No Janitor Desktop artifact found. Build with:' \
        "  node ${script_root}/apps/desktop/janitor/build.mjs" >&2
    exit 1
fi
if [[ "$diagnostic" == path ]]; then printf '%s\n' "$binary"; exit 0; fi
if [[ "$diagnostic" == version ]]; then
    if [[ ! -f "$metadata" ]]; then
        printf '%s\n' 'Build metadata is missing; rebuild the Janitor artifact.' >&2; exit 1
    fi
    python3 - "$metadata" <<'PYCODE'
import json,sys
with open(sys.argv[1],encoding='utf8') as file: metadata=json.load(file)
print('Janitor Agent v'+metadata['janitorVersion']+' (Hermes v'+metadata['upstreamVersion']+')')
PYCODE
    exit 0
fi
[[ -x "$binary" ]] || { printf 'Artifact is not executable: %s\n' "$binary" >&2; exit 1; }
export JANITOR_HOME="$janitor_home" HERMES_HOME="$janitor_home"
command=("$binary" "${app_args[@]}")
if [[ "$headless" -eq 1 ]]; then
    command -v xvfb-run >/dev/null || { printf '%s\n' '--headless requires xvfb-run' >&2; exit 1; }
    command=(xvfb-run -a "${command[@]}")
fi
if [[ "$background" -eq 1 ]]; then
    nohup "${command[@]}" >/dev/null 2>&1 &
    pid=$!
    disown || true
    printf 'Started Janitor Desktop (PID %s)\n' "$pid"
else
    exec "${command[@]}"
fi
