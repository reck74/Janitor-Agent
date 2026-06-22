#!/usr/bin/env bash
# janitor-desktop-launcher — launch the compiled Janitor Desktop AppImage.
# Resolves paths relative to this script so it works from any CWD.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DESKTOP_DIR="${REPO_ROOT}/apps/desktop"
RELEASE_DIR="${DESKTOP_DIR}/release"

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

# Prefer python3 (always available in modern Linux distros) over jq (often missing).
read_pkg_field() {
    local field="$1"
    python3 -c "import json,sys; print(json.load(open('${DESKTOP_DIR}/package.json')).get('${field}',''))" 2>/dev/null \
        || sed -n "s/.*\"${field}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "${DESKTOP_DIR}/package.json" | head -n1
}

USE_UNPACKED=0
HEADLESS=0
BACKGROUND=0
PRINT_VERSION_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --unpacked)   USE_UNPACKED=1 ;;
        --headless)   HEADLESS=1 ;;
        --background) BACKGROUND=1 ;;
        --version)    PRINT_VERSION_ONLY=1 ;;
        -h|--help)
            cat <<'USAGE'
janitor-desktop-launcher — launch the compiled Janitor Desktop AppImage.

Usage:
  launch.sh [--unpacked] [--headless] [--background] [--version]

Flags:
  --unpacked    Run the unpacked binary at release/linux-unpacked/janitor
  --headless    Wrap launch in xvfb-run (requires xvfb)
  --background  Fork and detach so the shell does not block
  --version     Print detected app version and exit
  -h, --help    Show this help and exit
USAGE
            exit 0
            ;;
        *)
            log_fail "Unknown flag: $1 (try --help)"
            exit 2
            ;;
    esac
    shift
done

APP_NAME="$(read_pkg_field name)"
APP_VERSION="$(read_pkg_field version)"

if [[ "${PRINT_VERSION_ONLY}" -eq 1 ]]; then
    echo "${APP_NAME} v${APP_VERSION}"
    exit 0
fi

log_info "Janitor Desktop launcher — ${APP_NAME} v${APP_VERSION}"

if [[ ! -d "${RELEASE_DIR}" ]]; then
    die "Release directory missing: ${RELEASE_DIR}. Run 'cd apps/desktop && npm run dist:linux' first."
fi

if [[ "${USE_UNPACKED}" -eq 1 ]]; then
    UNPACKED_BIN="${RELEASE_DIR}/linux-unpacked/janitor"
    if [[ ! -x "${UNPACKED_BIN}" ]]; then
        die "Unpacked binary missing or not executable: ${UNPACKED_BIN}"
    fi
    BINARY="${UNPACKED_BIN}"
    log_info "Mode: unpacked"
else
    # electron-builder names the artifact <name>-<version>-linux-x86_64.AppImage
    # at runtime — glob instead of hardcoding so version bumps don't break the script.
    APPIMAGE_PATH="$(find "${RELEASE_DIR}" -maxdepth 1 -type f -name '*-linux-x86_64.AppImage' | head -n1 || true)"
    if [[ -z "${APPIMAGE_PATH}" ]]; then
        die "No AppImage found under ${RELEASE_DIR}. Build one with 'cd apps/desktop && npm run dist:linux'."
    fi
    if [[ ! -x "${APPIMAGE_PATH}" ]]; then
        log_warn "AppImage not executable, fixing: ${APPIMAGE_PATH}"
        chmod +x "${APPIMAGE_PATH}"
    fi
    BINARY="${APPIMAGE_PATH}"
    log_info "Mode: AppImage"
fi

log_ok "Binary: ${BINARY}"

LAUNCH_CMD=("${BINARY}")

if [[ "${HEADLESS}" -eq 1 ]]; then
    if ! command -v xvfb-run >/dev/null 2>&1; then
        die "--headless requires xvfb-run (apt-get install xvfb)"
    fi
    log_info "Wrapping in xvfb-run (virtual display)"
    LAUNCH_CMD=(xvfb-run -a "${LAUNCH_CMD[@]}")
fi

if [[ "${BACKGROUND}" -eq 1 ]]; then
    log_info "Launching detached (--background). Use 'pkill janitor' to stop."
    nohup "${LAUNCH_CMD[@]}" >/dev/null 2>&1 &
    disown || true
    sleep 1
    if pgrep -af 'J4nitor-Agent|janitor' >/dev/null 2>&1; then
        log_ok "Process started (PID $!)"
    else
        log_warn "Process may have exited immediately — check HERMES_HOME/logs/desktop.log"
    fi
    exit 0
fi

log_info "Launching (Ctrl+C to stop)..."
exec "${LAUNCH_CMD[@]}"