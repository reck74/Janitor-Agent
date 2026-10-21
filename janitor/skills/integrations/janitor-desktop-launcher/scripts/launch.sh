#!/usr/bin/env bash
# janitor-desktop-launcher — launch Janitor Desktop against ~/.janitor.
#
# Resolution order for the AppImage:
#   1. A local build under <install tree>/apps/desktop/release/ (built with
#      `node apps/desktop-janitor/scripts/build.mjs --linux AppImage`).
#   2. A previously downloaded release under $HERMES_HOME/desktop/.
#   3. The latest GitHub release of the fork (downloaded on demand).
# The app always runs with HERMES_HOME pointing at the Janitor home, so it
# talks to the same config, sessions and skills as the `janitor` CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
DEFAULT_REPO="reck74/Janitor-Agent"

if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi
log_info()  { echo -e "${CYAN}→${NC} $*"; }
log_ok()    { echo -e "${GREEN}✓${NC} $*"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
log_fail()  { echo -e "${RED}✗${NC} $*" >&2; }
die() { log_fail "$*"; exit 1; }

HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.janitor}"
DOWNLOAD_DIR="${HERMES_HOME_DIR}/desktop"
REPO="${DEFAULT_REPO}"

USE_UNPACKED=0
HEADLESS=0
BACKGROUND=0
PRINT_PATH_ONLY=0
FORCE_DOWNLOAD=0

usage() {
    cat <<USAGE
janitor-desktop-launcher — launch Janitor Desktop.

Usage:
  launch.sh [--download] [--repo owner/name] [--unpacked] [--headless]
            [--background] [--print-path]

Flags:
  --download      Fetch the latest release AppImage even if one exists locally
  --repo R        GitHub repository to download from (default: ${DEFAULT_REPO})
  --unpacked      Run the unpacked local build (release/linux-unpacked/Janitor)
  --headless      Wrap launch in xvfb-run (requires xvfb)
  --background    Fork and detach so the shell does not block
  --print-path    Print the resolved binary path and exit
  -h, --help      Show this help and exit

HERMES_HOME defaults to ~/.janitor; downloads go to \$HERMES_HOME/desktop/.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --download)   FORCE_DOWNLOAD=1 ;;
        --repo)       shift; REPO="${1:?--repo needs owner/name}" ;;
        --unpacked)   USE_UNPACKED=1 ;;
        --headless)   HEADLESS=1 ;;
        --background) BACKGROUND=1 ;;
        --print-path) PRINT_PATH_ONLY=1 ;;
        -h|--help)    usage; exit 0 ;;
        *)            log_fail "Unknown flag: $1 (try --help)"; exit 2 ;;
    esac
    shift
done

RELEASE_DIRS=(
    "${HERMES_HOME_DIR}/janitor-core/apps/desktop/release"
    "${SCRIPT_REPO_ROOT}/apps/desktop/release"
)

newest() {
    # Newest file matching a glob across directories (mtime order).
    local pattern="$1"; shift
    local dir
    for dir in "$@"; do
        [[ -d "${dir}" ]] || continue
        find "${dir}" -maxdepth 1 -type f -name "${pattern}" -printf '%T@ %p\n' 2>/dev/null
    done | sort -rn | head -n1 | cut -d' ' -f2-
}

download_latest() {
    command -v curl >/dev/null 2>&1 || die "curl is required to download Janitor Desktop"
    local api="https://api.github.com/repos/${REPO}/releases/latest"
    log_info "Looking up the latest release of ${REPO}..."
    local url
    url="$(curl -fsSL "${api}" | python3 -c '
import json, sys
assets = json.load(sys.stdin).get("assets", [])
urls = [a["browser_download_url"] for a in assets
        if a["name"].startswith("Janitor-") and a["name"].endswith("-linux-x86_64.AppImage")]
print(urls[0] if urls else "")
')" || die "Could not query ${api}"
    [[ -n "${url}" ]] || die "The latest ${REPO} release has no Janitor Linux AppImage"
    mkdir -p "${DOWNLOAD_DIR}"
    local dest="${DOWNLOAD_DIR}/$(basename "${url}")"
    log_info "Downloading $(basename "${url}")..."
    curl -fL --progress-bar -o "${dest}.part" "${url}" || die "Download failed"
    mv "${dest}.part" "${dest}"
    chmod +x "${dest}"
    printf '%s\n' "${dest}"
}

if [[ "${USE_UNPACKED}" -eq 1 ]]; then
    BINARY=""
    for dir in "${RELEASE_DIRS[@]}"; do
        if [[ -x "${dir}/linux-unpacked/Janitor" ]]; then
            BINARY="${dir}/linux-unpacked/Janitor"
            break
        fi
    done
    [[ -n "${BINARY}" ]] || die "No unpacked build found (build with: node apps/desktop-janitor/scripts/build.mjs --linux dir)"
else
    BINARY=""
    if [[ "${FORCE_DOWNLOAD}" -eq 0 ]]; then
        BINARY="$(newest 'Janitor-*-linux-x86_64.AppImage' "${RELEASE_DIRS[@]}" "${DOWNLOAD_DIR}")"
    fi
    if [[ -z "${BINARY}" ]]; then
        BINARY="$(download_latest)"
    fi
    chmod +x "${BINARY}" 2>/dev/null || true
fi

if [[ "${PRINT_PATH_ONLY}" -eq 1 ]]; then
    printf '%s\n' "${BINARY}"
    exit 0
fi

log_ok "Binary: ${BINARY}"
log_info "HERMES_HOME: ${HERMES_HOME_DIR}"

# The desktop backend starts Hermes directly, skipping the `janitor` launcher
# that normally upgrades a pre-1.0 home, so run that migration here first.
if [[ "${HERMES_HOME_DIR}" == "${JANITOR_HOME:-$HOME/.janitor}" && ! -f "${HERMES_HOME_DIR}/.layout_version" ]]; then
    for migrate in "${HERMES_HOME_DIR}/janitor-core/scripts/migrate-janitor-v1.sh" \
                   "${SCRIPT_REPO_ROOT}/scripts/migrate-janitor-v1.sh"; do
        if [[ -f "${migrate}" ]]; then
            JANITOR_HOME="${HERMES_HOME_DIR}" bash "${migrate}" || log_warn "Layout migration failed — run: bash ${migrate}"
            break
        fi
    done
fi

export HERMES_HOME="${HERMES_HOME_DIR}"
export HERMES_DESKTOP_APP_NAME="${HERMES_DESKTOP_APP_NAME:-Janitor}"

LAUNCH_CMD=("${BINARY}")

if [[ "${HEADLESS}" -eq 1 ]]; then
    command -v xvfb-run >/dev/null 2>&1 || die "--headless requires xvfb-run (apt-get install xvfb)"
    LAUNCH_CMD=(xvfb-run -a "${LAUNCH_CMD[@]}")
fi

if [[ "${BACKGROUND}" -eq 1 ]]; then
    nohup "${LAUNCH_CMD[@]}" >/dev/null 2>&1 &
    pid=$!
    disown || true
    sleep 1
    if kill -0 "${pid}" 2>/dev/null; then
        log_ok "Janitor Desktop started (PID ${pid})"
    else
        log_warn "Process exited immediately — check ${HERMES_HOME_DIR}/logs/desktop.log"
    fi
    exit 0
fi

exec "${LAUNCH_CMD[@]}"
