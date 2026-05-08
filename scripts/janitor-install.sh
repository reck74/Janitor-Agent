#!/bin/bash
# =============================================================================
# Janitor Installer v4 — Perfil Inicializador Puro (~/.janitor)
# =============================================================================
#
# Este script NO instala Hermes ni dependencias. El entorno virtual y las
# dependencias son gestionadas por el entorno de desarrollo existente.
#
# Este script es UNICAMENTE un inicializador de perfil Janitor:
#   - Recolecta API keys interactivamente (con personalidad cínica)
#   - Crea ~/.janitor/ con toda la estructura de directorios
#   - Genera .env, SOUL.md, config.yaml
#   - Despliega el skin sentry-janitor
#
# Uso:
#   ./scripts/janitor-install.sh
#   curl -fsSL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/janitor-install.sh | bash
#
# =============================================================================

# =============================================================================
# PRE-CHECK: Hostile Takeover Warning
# =============================================================================
if [ -d "${HOME}/.hermes" ]; then
    echo ""
    echo -e "${A_PINK}${A_BOLD}╔══════════════════════════════════════════════════════════════╗${A_NC}"
    echo -e "${A_PINK}${A_BOLD}║${A_NC}  ${A_CORAL}${A_BOLD}ATENCIÓN: Hostile Takeover Detectado${A_NC}                      ${A_PINK}║${A_NC}"
    echo -e "${A_PINK}${A_BOLD}╚══════════════════════════════════════════════════════════════╝${A_NC}"
    echo ""
    echo -e "${A_CORAL}⚠  Janitor es una evolución agresiva de Hermes.${A_NC}"
    echo -e "${A_WHITE}   Se detectó una instalación previa en ${HOME}/.hermes${A_NC}"
    echo -e "${A_WHITE}   Al continuar, Janitor tomará el control global del entorno.${A_NC}"
    echo -e "${A_WHITE}   Tu Hermes original podría dejar de funcionar por defecto.${A_NC}"
    echo ""
    read -r -p "¿Deseas continuar? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Abortado por el usuario."
        exit 1
    fi
fi

set -e

# ── Rutas ───────────────────────────────────────────────────────────────────
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
SKIN_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../example_skin_sentry-janitor.yaml.txt"

# ── Aesthetic — Janitor Sentry palette ──────────────────────────────────────
# Sent by the Sentry Dark IDE + Cyberpunk Flamethrower palette
LIME='#c2ef4e'      # Lime Green: primary / ok
PURPLE='#6a5fc1'    # Sentry Purple: accent
PINK='#fa7faa'       # Pink: error / shell dollar
CORAL='#ffb287'      # Coral: warn
MUTED='#79628c'      # Muted purple: secondary text
WHITE='#e5e7eb'      # Light gray: text
BORDER='#362d59'     # Border purple

# ANSI escapes for each palette color
A_LIME="\033[38;2;194;239;78m"    # #c2ef4e
A_PURPLE="\033[38;2;106;95;193m"   # #6a5fc1
A_PINK="\033[38;2;250;127;170m"    # #fa7faa
A_CORAL="\033[38;2;255;178;135m"  # #ffb287
A_MUTED="\033[38;2;121;98;140m"   # #79628c
A_WHITE="\033[38;2;229;231;235m"   # #e5e7eb
A_BOLD="\033[1m"
A_NC="\033[0m"

# ── Helpers ──────────────────────────────────────────────────────────────────
log_info()  { echo -e "${A_PURPLE}→${A_NC} $1"; }
log_ok()    { echo -e "${A_LIME}✓${A_NC} $1"; }
log_warn()  { echo -e "${A_CORAL}⚠${A_NC} $1"; }
log_fail()  { echo -e "${A_PINK}✗${A_NC} $1"; }

validate_nonempty() {
    local var_name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        log_fail "$var_name no puede estar vacía."
        return 1
    fi
    return 0
}

# =============================================================================
# Banner de Bienvenida — ASCII Art con colores Janitor
# =============================================================================
echo ""
echo -e "${A_BOLD}${A_LIME}"
echo "       ██╗ █████╗ ███╗   ██╗██╗████████╗██████╗ ██████╗  "
echo "       ██║██╔══██╗████╗  ██║██║╚══██╔══╝██╔══██╗██╔══██╗ "
echo "       ██║███████║██╔██╗ ██║██║   ██║   ██║  ██║██████╔╝ "
echo " ██   ██║██╔══██║██║╚██╗██║██║   ██║   ██║  ██║██╔══██╗"
echo " ╚█████╔╝██║  ██║██║ ╚████║██║   ██║   ██████╔╝██║  ██║"
echo "  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═════╝ ╚═╝  ╚═╝"
echo -e "${A_NC}"
echo -e "  ${A_PINK}╔══════════════════════════════════════════════════════╗${A_NC}"
echo -e "  ${A_PINK}║${A_NC}  ${A_BOLD}${A_WHITE}Tu agente cínico de auditoría y ciberseguridad${A_NC}  ${A_PINK}║${A_NC}"
echo -e "  ${A_PINK}╚══════════════════════════════════════════════════════╝${A_NC}"
echo ""
echo -e "  ${A_MUTED}Scanning ports... analyzing artifact... hunting vulns.${A_NC}"
echo ""

# =============================================================================
# Paso 1: Recolección Interactiva de API Keys — Tono Cínico
# =============================================================================
echo -e "${A_PURPLE}─── Credenciales del Agente ───${A_NC}"
echo ""

# OpenAI API Key (OBLIGATORIA)
echo -e "${A_CORAL}OPENAI_API_KEY${A_NC} — Sin esto no puedo razonar. Ni limpiar código basura."
echo -e "${A_MUTED}   Obtenla en: https://platform.openai.com/api-keys${A_NC}"
read -r -p "   Dame tu OPENAI_API_KEY: " -s openai_key
echo
if ! validate_nonempty "OPENAI_API_KEY" "$openai_key"; then
    echo -e "${A_PINK}   La key de OpenAI es obligatoria. Sin ella soy un chatbot caro. Sáltate este paso y sufrirás.${A_NC}"
    exit 1
fi
log_ok "OpenAI key configurada — finalmente, algo útil"

# MiniMax API Key (OBLIGATORIA) — Se usa como LLM_ANTHROPIC_API_KEY para Honcho
echo ""
echo -e "${A_CORAL}MINIMAX_API_KEY${A_NC} — ${A_LIME}OBLIGATORIA${A_NC}. Honcho la usa como ${A_PINK}LLM_ANTHROPIC_API_KEY${A_NC}"
echo -e "${A_MUTED}   Obtenla en: https://platform.minimax.io${A_NC}"
while true; do
    read -r -p "   MINIMAX_API_KEY: " -s minimax_key
    echo
    if [[ -n "$minimax_key" ]]; then
        log_ok "MiniMax key configurada — Honcho la usará para razonar en modo local"
        break
    else
        echo -e "${A_PINK}   No puede estar vacía. Sin ella Janitor no puede arrancar.${A_NC}"
    fi
done

# Honcho + Firecrawl: Keys o Local
echo ""
echo -e "${A_CORAL}HONCHO & FIRECRAWL${A_NC} — Memoria persistente y scraping web"
echo ""
echo "   ¿Ya tienes API keys o prefieres que Janitor instale los contenedores locales?"
echo ""
echo -e "   ${A_LIME}[1]${A_NC}  Tengo las API keys — ingrésalas ahora"
echo -e "   ${A_CORAL}[2]${A_NC}  Instalación Local Autónoma — Janitor levanta Docker (recomendado)"
echo ""
read -r -p "   Selecciona [1/2]: " setup_mode
echo

if [[ "$setup_mode" != "1" && "$setup_mode" != "2" ]]; then
    log_fail "Opción inválida: '$setup_mode'. Debe ser 1 o 2."
    exit 1
fi

honcho_key=""
firecrawl_key=""

if [[ "$setup_mode" == "1" ]]; then
    echo ""
    echo -e "${A_PURPLE}   HONCHO_API_KEY${A_NC} — Tu memoria persistente necesita una key."
    read -r -p "   HONCHO_API_KEY: " -s honcho_key
    echo
    [[ -n "$honcho_key" ]] && log_ok "Honcho API key configurada"

    echo ""
    echo -e "${A_PURPLE}   FIRECRAWL_API_KEY${A_NC} — Scraping web. Saltable si no web-scrapeas."
    read -r -p "   FIRECRAWL_API_KEY (Enter para omitir): " -s firecrawl_key
    echo
    [[ -n "$firecrawl_key" ]] && log_ok "Firecrawl API key configurada" || log_warn "Firecrawl saltado — nada de scraping web"
else
    echo -e "${A_LIME}   Modo Local Autonomous Selected — Janitor levanta los contenedores Docker${A_NC}"
fi

# OpenAI Base URL (OPCIONAL)
echo ""
echo -e "${A_CORAL}OPENAI_BASE_URL${A_NC} — Deja en blanco para el servidor oficial de OpenAI."
read -r -p "   OPENAI_BASE_URL (Enter para omitir): " openai_base_url
echo
[[ -n "$openai_base_url" ]] && log_ok "Base URL personalizada configurada" || log_info "Usando OpenAI oficial"

# =============================================================================
# Paso 2: Crear estructura de directorios ~/.janitor
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Estructura de Directorios ───${A_NC}"
echo ""

log_info "Creando Janitor home en ${A_WHITE}${JANITOR_HOME}${A_NC}..."

mkdir -p "${JANITOR_HOME}"
mkdir -p "${JANITOR_HOME}/sessions"
mkdir -p "${JANITOR_HOME}/skills"
mkdir -p "${JANITOR_HOME}/skins"
mkdir -p "${JANITOR_HOME}/logs"
mkdir -p "${JANITOR_HOME}/tmp"

log_ok "Directorios creados:"
echo "   ${A_MUTED}sessions/  — histórico de sesiones${A_NC}"
echo "   ${A_MUTED}skills/    — habilidades del agente${A_NC}"
echo "   ${A_MUTED}skins/     — temas visuales${A_NC}"
echo "   ${A_MUTED}logs/      — logs del agente${A_NC}"
echo "   ${A_MUTED}tmp/       — archivos temporales${A_NC}"

# =============================================================================
# Paso 3: Generar ~/.janitor/.env
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Archivo de Variables de Entorno ───${A_NC}"
echo ""

ENV_FILE="${JANITOR_HOME}/.env"
log_info "Escribiendo ${A_WHITE}${ENV_FILE}${A_NC}..."

{
    echo "# ========================================================="
    echo "# Janitor Agent — Variables de Entorno"
    echo "# Generado por janitor-install.sh"
    echo "# ========================================================="
    echo ""
    echo "OPENAI_API_KEY=${openai_key}"
    [[ -n "$minimax_key" ]]     && echo "MINIMAX_API_KEY=${minimax_key}"
    [[ -n "$honcho_key" ]]      && echo "HONCHO_API_KEY=${honcho_key}"
    [[ -n "$firecrawl_key" ]]  && echo "FIRECRAWL_API_KEY=${firecrawl_key}"
    [[ -n "$openai_base_url" ]] && echo "OPENAI_BASE_URL=${openai_base_url}"

    # MiniMax → LLM_ANTHROPIC_API_KEY para Honcho (Hack de infraestructura)
    if [[ -n "$minimax_key" ]]; then
        echo ""
        echo "# ========================================================="
        echo "# Honcho — MiniMax como LLM_ANTHROPIC_API_KEY"
        echo "# Honcho usa Anthropic transport, pero con el modelo de MiniMax"
        echo "# ========================================================="
        echo "LLM_ANTHROPIC_API_KEY=${minimax_key}"
        echo "LLM_OPENAI_API_KEY=${openai_key}"
    fi

    if [[ "$setup_mode" == "2" ]]; then
        echo ""
        echo "# ========================================================="
        echo "# Modo Local Autónomo — Honcho y Firecrawl via Docker"
        echo "# ========================================================="
        echo "JANITOR_LOCAL_SETUP=true"
    fi

    echo ""
    echo "# ========================================================="
    echo "# Configuración de Janitor"
    echo "# ========================================================="
    echo "HERMES_HOME=${JANITOR_HOME}"
    echo "HERMES_SKIN=sentry-janitor"
} > "$ENV_FILE"

log_ok ".env escrito en ${A_WHITE}${ENV_FILE}${A_NC}"

# =============================================================================
# Paso 4: Copiar SOUL.md (Personalidad Cínica)
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Personalidad del Agente ───${A_NC}"
echo ""

SOUL_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/SOUL.md"
SOUL_PATH="${JANITOR_HOME}/SOUL.md"
log_info "Instalando personalidad cínica desde ${A_WHITE}${SOUL_SOURCE}${A_NC}..."

if [ -f "$SOUL_SOURCE" ]; then
    cp "$SOUL_SOURCE" "$SOUL_PATH"
    log_ok "Personalidad instalada — el cínico está listo para trabajar"
else
    log_warn "SOUL.md no encontrado en ${SOUL_SOURCE} — continuando sin personalidad"
fi

# =============================================================================
# Paso 5: Generar ~/.janitor/config.yaml
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Configuración del Agente ───${A_NC}"
echo ""

CONFIG_PATH="${JANITOR_HOME}/config.yaml"
log_info "Generando ${A_WHITE}${CONFIG_PATH}${A_NC}..."

python3 - "$CONFIG_PATH" "$setup_mode" << 'PYTHON_EOF'
import sys
import yaml

config_path = sys.argv[1]
setup_mode = sys.argv[2]

config = {
    "display": {
        "tui": True,
        "skin": "sentry-janitor"
    },
    "model": {
        "provider": "minimax",
        "default": "MiniMax-M2.7"
    },
    "skills": {
        "config": {
            "janitor.cache_clean_days": 7,
            "janitor.dry_run": False,
            "janitor.local_services_timeout": 60,
            "janitor.honcho_port": 1973,
            "janitor.firecrawl_port": 1974
        }
    }
}

# Solo habilitar Honcho como provider si el usuario eligió modo Keys y proporcionó API key
if setup_mode == "1":
    config["memory"] = {"provider": "honcho"}

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("config.yaml written successfully")
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_ok "config.yaml generado"
else
    log_fail "Error al generar config.yaml"
    exit 1
fi

# =============================================================================
# Paso 6: Copiar skin sentry-janitor
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Skin Visual ───${A_NC}"
echo ""

if [ -f "$SKIN_SOURCE" ]; then
    log_info "Copiando skin sentry-janitor..."
    cp "$SKIN_SOURCE" "${JANITOR_HOME}/skins/sentry-janitor.yaml"
    log_ok "Skin instalado: ${JANITOR_HOME}/skins/sentry-janitor.yaml"
else
    log_warn "Skin source no encontrado — el agente funcionará sin skin personalizado"
fi

# =============================================================================
# Global HERMES_HOME Hijack — ~/.bashrc / ~/.zshrc
# =============================================================================
echo ""
echo -e "${A_PURPLE}─── Inyección Global de HERMES_HOME y PATH ───${A_NC}"
echo ""

HERMES_HOME_EXPORT='export HERMES_HOME="$HOME/.janitor"'
PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'
INJECTED_MARKER="# Janitor — Global env (añadido por janitor-install.sh)"

for rc_file in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
    if [ -f "$rc_file" ]; then
        if ! grep -q 'HERMES_HOME.*\.janitor' "$rc_file" 2>/dev/null; then
            echo "" >> "$rc_file"
            echo "$INJECTED_MARKER" >> "$rc_file"
            echo "$HERMES_HOME_EXPORT" >> "$rc_file"
            echo "$PATH_EXPORT" >> "$rc_file"
            log_ok "HERMES_HOME + PATH inyectados en $rc_file"
        else
            log_info "HERMES_HOME ya presente en $rc_file — omitido"
        fi
    fi
done

# =============================================================================
# Final: Mensaje de Éxito
# =============================================================================
echo ""
echo -e "${A_LIME}${A_BOLD}"
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║          ✅ Configuración de Janitor Completada                       ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo -e "${A_NC}"
echo ""
echo -e "   ${A_PURPLE}Directorio:${NC}     ${A_WHITE}${JANITOR_HOME}${A_NC}"
echo -e "   ${A_PURPLE}Config:${NC}        ${A_WHITE}${JANITOR_HOME}/config.yaml${A_NC}"
echo -e "   ${A_PURPLE}Variables:${NC}      ${A_WHITE}${JANITOR_HOME}/.env${A_NC}"
echo -e "   ${A_PURPLE}Personalidad:${NC}   ${A_WHITE}${JANITOR_HOME}/SOUL.md${A_NC}"
echo -e "   ${A_PURPLE}Skin:${NC}           ${A_WHITE}${JANITOR_HOME}/skins/sentry-janitor.yaml${A_NC}"
echo ""

if [[ "$setup_mode" == "2" ]]; then
    echo -e "${A_CORAL}⚠ Modo Local detectado${A_NC}"
    echo "   Ejecuta '${A_BOLD}/onboard${A_NC}' dentro de Janitor para levantar los contenedores Docker"
    echo "   de Honcho y Firecrawl la primera vez."
    echo ""
fi

echo -e "${A_LIME}▶ Ejecuta '${A_BOLD}source ~/.bashrc${A_NC}' (o reinicia tu terminal) para aplicar los cambios en el PATH.${A_NC}"
echo ""
echo -e "${A_LIME}▶ Luego ejecuta '${A_BOLD}janitor${A_NC}' para iniciar el agente.${A_NC}"
echo ""