#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# JANITOR bootstrap.sh — Zero-Friction One-Liner Installer
# ============================================================

# Config — el usuario puede cambiar estas variables
JANITOR_REPO_URL="${JANITOR_REPO_URL:-https://github.com/reck74/Janitor-Agent.git}"
JANITOR_SOURCE_DIR="${HOME}/.janitor-source"
JANITOR_VENV_DIR="${JANITOR_SOURCE_DIR}/venv"
JANITOR_INSTALL_SCRIPT="${JANITOR_SOURCE_DIR}/scripts/janitor-install.sh"

# ============================================================
# 1. Banner silencioso
# ============================================================
echo "Descargando e instalando el motor de Janitor..."

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
if [ -d "${JANITOR_SOURCE_DIR}/.git" ]; then
    echo "Janitor ya instalado. Ejecutando git pull..."
    cd "${JANITOR_SOURCE_DIR}"
    git pull origin main
else
    echo "Clonando Janitor..."
    git clone --depth 1 "${JANITOR_REPO_URL}" "${JANITOR_SOURCE_DIR}"
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
# 5. Compilación React/TUI
# ============================================================
echo "Compilando interfaz TUI..."
cd "${JANITOR_SOURCE_DIR}/ui-tui"
npm install
npm run build

# ============================================================
# 6. Enlace global
# ============================================================
echo "Creando enlace global..."
mkdir -p "${HOME}/.local/bin"
ln -sf "${JANITOR_VENV_DIR}/bin/janitor" "${HOME}/.local/bin/janitor"

# ============================================================
# 7. Handoff al instalador interactivo
# ============================================================
echo "Lanzando instalador interactivo..."
cd "${JANITOR_SOURCE_DIR}"
bash "${JANITOR_INSTALL_SCRIPT}"