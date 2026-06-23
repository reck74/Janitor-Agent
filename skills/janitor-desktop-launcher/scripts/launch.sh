#!/usr/bin/env bash
# janitor-desktop-launcher — launch the compiled Janitor Desktop AppImage.
# Searches multiple install locations in priority order so the same script
# works for end users (HERMES_HOME=~/.janitor/janitor-core), developers
# running from a checkout, and CI/sandbox scenarios.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

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

# Candidates for the apps/desktop directory, in priority order.
# 1. HERMES_HOME/janitor-core/apps/desktop — default end-user install layout
#    (hermes_constants.get_hermes_home() returns ~/.janitor, janitor-install.sh
#    mirrors the repo to ~/.janitor/janitor-core/).
# 2. HERMES_HOME/apps/desktop — if a non-janitor-core layout is used.
# 3. Path relative to this script — developer running from a checkout.
# 4. ./apps/desktop from CWD — for `bash skills/.../launch.sh` from repo root.
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.janitor}"
CANDIDATES=(
    "${HERMES_HOME_DIR}/janitor-core/apps/desktop"
    "${HERMES_HOME_DIR}/apps/desktop"
    "${SCRIPT_REPO_ROOT}/apps/desktop"
    "$(pwd)/apps/desktop"
)

resolve_desktop_dir() {
    local candidate
    for candidate in "${CANDIDATES[@]}"; do
        if [[ -f "${candidate}/package.json" && -d "${candidate}/release" ]]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    return 1
}

DESKTOP_DIR="$(resolve_desktop_dir || true)"
if [[ -z "${DESKTOP_DIR}" ]]; then
    log_fail "Could not find the Janitor Desktop source tree."
    log_fail "Searched:"
    printf '  - %s\n' "${CANDIDATES[@]}" >&2
    die "Set HERMES_HOME=/path/to/.janitor or run from the repo checkout."
fi

RELEASE_DIR="${DESKTOP_DIR}/release"

# Prefer python3 (always available in modern Linux distros) over jq (often missing).
read_pkg_field() {
    local field="$1"
    python3 -c "import json; print(json.load(open('${DESKTOP_DIR}/package.json')).get('${field}',''))" 2>/dev/null \
        || sed -n "s/.*\"${field}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "${DESKTOP_DIR}/package.json" | head -n1
}

USE_UNPACKED=0
HEADLESS=0
BACKGROUND=0
PRINT_VERSION_ONLY=0
PRINT_PATH_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --unpacked)   USE_UNPACKED=1 ;;
        --headless)   HEADLESS=1 ;;
        --background) BACKGROUND=1 ;;
        --version)    PRINT_VERSION_ONLY=1 ;;
        --print-path) PRINT_PATH_ONLY=1 ;;
        -h|--help)
            cat <<'USAGE'
janitor-desktop-launcher — launch the compiled Janitor Desktop AppImage.

Usage:
  launch.sh [--unpacked] [--headless] [--background] [--version] [--print-path]

Flags:
  --unpacked    Run the unpacked binary at release/linux-unpacked/janitor
  --headless    Wrap launch in xvfb-run (requires xvfb)
  --background  Fork and detach so the shell does not block
  --version     Print detected app version and exit
  --print-path  Print the resolved AppImage path and exit
  -h, --help    Show this help and exit

Path resolution (priority order):
  1. $HERMES_HOME/janitor-core/apps/desktop   (default end-user install)
  2. $HERMES_HOME/apps/desktop                (alternative layout)
  3. Path relative to this script             (developer checkout)
  4. ./apps/desktop from current working dir  (CI / sandbox)
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
log_info "Source: ${DESKTOP_DIR}"

if [[ ! -d "${RELEASE_DIR}" ]]; then
    die "Release directory missing: ${RELEASE_DIR}. Run 'cd ${DESKTOP_DIR} && npm run dist:linux' first."
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
        die "No AppImage found under ${RELEASE_DIR}. Build one with 'cd ${DESKTOP_DIR} && npm run dist:linux'."
    fi
    if [[ ! -x "${APPIMAGE_PATH}" ]]; then
        log_warn "AppImage not executable, fixing: ${APPIMAGE_PATH}"
        chmod +x "${APPIMAGE_PATH}"
    fi
    BINARY="${APPIMAGE_PATH}"
    log_info "Mode: AppImage"
fi

log_ok "Binary: ${BINARY}"

if [[ "${PRINT_PATH_ONLY}" -eq 1 ]]; then
    printf '%s\n' "${BINARY}"
    exit 0
fi

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