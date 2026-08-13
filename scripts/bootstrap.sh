#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# JANITOR bootstrap.sh — Zero-Friction One-Liner Installer
# ============================================================

# Config — el usuario puede cambiar estas variables
JANITOR_REPO_URL="${JANITOR_REPO_URL:-https://github.com/reck74/Janitor-Agent.git}"
JANITOR_SOURCE_DIR="${HOME}/.janitor/janitor-core"
JANITOR_VENV_DIR="${JANITOR_SOURCE_DIR}/.venv"
JANITOR_INSTALL_SCRIPT="${JANITOR_SOURCE_DIR}/scripts/janitor-install.sh"

# Janitor aísla su estado bajo ~/.janitor (no ~/.hermes). Lo exportamos antes
# de invocar la librería compartida node-bootstrap.sh para que Node se
# instale en ~/.janitor/node, consistente con el resto del fork.
export HERMES_HOME="${HOME}/.janitor"

# ============================================================
# 1. Banner silencioso
# ============================================================
echo "Descargando e instalando el motor de Janitor..."

# ============================================================
# 1b. Kill-Switch: Docker Daemon Gate
# ============================================================
check_docker_hard() {
    local BLUE='\033[0;34m'
    local YELLOW='\033[1;33m'
    local RED='\033[0;31m'
    local GREEN='\033[0;32m'
    local NC='\033[0m'

    echo -e "→ Checking Docker Daemon..."

    # Pre-authenticate sudo with TTY access (curl | bash pipe lock workaround)
    echo -e "${YELLOW}Se requieren permisos de administrador para validar Docker...${NC}"
    sudo -v < /dev/tty || { echo -e "${RED}Autenticación fallida.${NC}"; exit 1; }

    if ! command -v docker >/dev/null 2>&1; then
        echo -e "Docker CLI not found. Attempting install..."
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh 2>/dev/null && sudo sh /tmp/get-docker.sh 2>/dev/null < /dev/tty
        if [ $? -ne 0 ]; then
            echo -e "FATAL: Docker installation failed. Please install Docker Desktop manually."
            exit 1
        fi
    fi

    set +e
    DOCKER_OUT=$(docker info 2>&1)
    DOCKER_STATUS=$?
    set -e
    if [ $DOCKER_STATUS -ne 0 ]; then
        if echo "$DOCKER_OUT" | grep -q "permission denied"; then
            echo -e "Permission denied on docker.sock. Auto-fixing group permissions..."
            sudo usermod -aG docker "$USER" < /dev/tty || sudo adduser "$USER" docker < /dev/tty
            echo -e "[ACCIÓN REQUERIDA] Tu usuario fue añadido al grupo 'docker'."
            echo -e "Debes reiniciar tu terminal (o ejecutar 'newgrp docker') y volver a correr este instalador."
            exit 1
        else
            echo -e "Docker daemon not running. Attempting to start service..."
            sudo systemctl start docker 2>/dev/null < /dev/tty || sudo service docker start 2>/dev/null < /dev/tty
            sleep 3
            if ! docker info >/dev/null 2>&1; then
                echo -e "FATAL: Docker daemon is dead. Start Docker Desktop manually and retry."
                exit 1
            fi
        fi
    fi
    echo -e "✓ Docker is active and accessible."
}

check_docker_hard

# ============================================================
# 2. Validación de dependencias
# ============================================================
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "Error: '$1' no encontrado. Instálalo primero."
        exit 1
    fi
}

check_dep git
check_dep python3

# Verificar o instalar uv
if ! command -v uv &>/dev/null; then
    echo "Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "${HOME}/.local/bin/env" 2>/dev/null || true
fi

# ============================================================
# 3. Clonación o pull
# ============================================================
mkdir -p "${HOME}/.janitor"
if [ -d "${JANITOR_SOURCE_DIR}/.git" ]; then
    echo "Janitor ya instalado. Ejecutando git pull..."
    cd "${JANITOR_SOURCE_DIR}"
    git pull origin main
else
    echo "Clonando Janitor..."
    git clone --depth 1 "${JANITOR_REPO_URL}" "${JANITOR_SOURCE_DIR}"
fi

# ============================================================
# 3b. Node.js — delegar al helper compartido de Hermes
# ============================================================
# El root package.json exige node >=22.22.0 y npm "<11.10.0 || >=11.17.0".
# Una versión previa de este bootstrap hardcodeaba `nvm install 20`, que
# NUNCA puede cumplir engines.node y mataba el `npm install` del TUI con
# EBADENGINE. Peor, el PATH exportado solo vivía dentro del sub-bash del
# curl, así que la shell de login del usuario veía `npm: command not found`
# apenas terminara el instalador.
#
# node-bootstrap.sh resuelve los tres problemas:
#   1. instala Node major 22 (HERMES_NODE_TARGET_MAJOR=22),
#   2. crea symlinks en /usr/local/bin (root) o ~/.local/bin (user),
#      que SÍ sobreviven al sub-bash porque están en PATH estándar,
#   3. respeta un Node existente en PATH si cumple la versión mínima,
#      y como fallback descarga un tarball pinneado de nodejs.org.
NODE_HELPER="${JANITOR_SOURCE_DIR}/scripts/lib/node-bootstrap.sh"
if [ ! -s "$NODE_HELPER" ]; then
    echo "FATAL: $NODE_HELPER no encontrado tras el clone."
    echo "       El repo está corrupto o el clone se cortó. Reintenta el install."
    exit 1
fi
# shellcheck source=scripts/lib/node-bootstrap.sh
source "$NODE_HELPER"
if ! ensure_node; then
    echo "FATAL: no se pudo provisionar Node >= 22.22.0."
    echo "       Instálalo manualmente (https://nodejs.org/) y reejecuta este script."
    exit 1
fi

# ============================================================
# 4. Compilación Python
# ============================================================
echo "Configurando entorno Python..."
cd "${JANITOR_SOURCE_DIR}"
uv venv .venv --python 3.11
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -e ".[all]"

# ============================================================
# 4b. Playwright Browser
# ============================================================
echo "Instalando navegador Playwright (chromium)..."
set +e
uv pip install playwright 2>/dev/null
uv run playwright install --with-deps chromium < /dev/tty
PW_RESULT=$?
set -e
if [ $PW_RESULT -ne 0 ]; then
    echo "⚠️  Playwright install failed — browser tools may not work."
    echo "   You can install manually later: uv run playwright install --with-deps chromium"
else
    echo "✓ Playwright chromium installed."
fi

# ============================================================
# 6. Compilación React/TUI
# ============================================================
echo "Compilando interfaz TUI..."
cd "${JANITOR_SOURCE_DIR}/ui-tui"
npm install
npm run build

# ============================================================
# 7. Enlace global
# ============================================================
echo "Creando enlace global..."
mkdir -p "${HOME}/.local/bin"
ln -sf "${JANITOR_VENV_DIR}/bin/janitor" "${HOME}/.local/bin/janitor"

# ============================================================
# 8. Handoff al instalador interactivo
# ============================================================
echo "Lanzando instalador interactivo..."
cd "${JANITOR_SOURCE_DIR}"
bash "${JANITOR_INSTALL_SCRIPT}" < /dev/tty