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
check_dep npm

# Verificar o instalar uv
if ! command -v uv &>/dev/null; then
    echo "Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "${HOME}/.local/bin/env" 2>/dev/null || true
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