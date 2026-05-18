#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# JANITOR bootstrap.sh — Zero-Friction One-Liner Installer
# ============================================================

# Config — el usuario puede cambiar estas variables
JANITOR_REPO_URL="${JANITOR_REPO_URL:-https://github.com/reck74/Janitor-Agent.git}"
JANITOR_SOURCE_DIR="${HOME}/.janitor/janitor-core"
JANITOR_VENV_DIR="${JANITOR_SOURCE_DIR}/venv"
JANITOR_INSTALL_SCRIPT="${JANITOR_SOURCE_DIR}/scripts/janitor-install.sh"

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

    DOCKER_OUT=$(docker info 2>&1)
    if [ $? -ne 0 ]; then
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
# Sanitización de Node.js (Mitigación Cross-OS WSL2)
# ============================================================
NPM_PATH=$(command -v npm 2>/dev/null || echo "missing")
if [[ "$NPM_PATH" == "missing" ]] || [[ "$NPM_PATH" == *".exe" ]] || [[ "$NPM_PATH" == *"/mnt/c/"* ]]; then
    echo "⚠️ NPM nativo no encontrado o versión de Windows detectada."
    echo "📦 Instalando Node.js nativo (v20) aislado vía NVM (cero sudo)..."
    export NVM_DIR="$HOME/.nvm"
    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash > /dev/null 2>&1
    fi
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm install 20 > /dev/null 2>&1
    nvm use 20 > /dev/null 2>&1
    export PATH="$NVM_DIR/versions/node/$(nvm current)/bin:$PATH"
    echo "✓ Node.js nativo instalado y activado."
else
    echo "✓ NPM nativo detectado: $NPM_PATH"
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
# 3b. Ecosistema Docker (Opcional)
# ============================================================
SETUP_STACK="${JANITOR_SOURCE_DIR}/scripts/setup-stack.sh"
if [ -f "$SETUP_STACK" ]; then
    echo "🔥 Ecosistema Docker detectado. ¿Deseas levantar el stack local (Honcho, Firecrawl)?"
    echo "   Esto requiere Docker instalado y corriendo."
    read -r -p "   Levantar stack ahora? (Y/n): " launch_stack
    if [[ "$launch_stack" != "n" && "$launch_stack" != "N" ]]; then
        bash "$SETUP_STACK" || echo "⚠️ El stack no se pudo levantar — continuando con la instalación base"
    else
        echo "   Stack Docker omitido. Puedes levantarlo luego con: bash $SETUP_STACK"
    fi
else
    echo "⚠️ setup-stack.sh no encontrado — omitiendo ecosistema Docker"
fi

# ============================================================
# 4. Compilación Python
# ============================================================
echo "Configurando entorno Python..."
cd "${JANITOR_SOURCE_DIR}"
uv venv venv --python 3.11
# shellcheck disable=SC1091
source venv/bin/activate
uv pip install -e ".[all]"

# ============================================================
# 4b. Playwright Browser
# ============================================================
echo "Instalando navegador Playwright (chromium)..."
set +e
uv run playwright install --with-deps chromium 2>/dev/null
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