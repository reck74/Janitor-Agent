#!/bin/bash
# =============================================================================
# Janitor Installer v5 — Minimal First-Run Profile (~/.janitor)
# =============================================================================
#
# Este script es UNICAMENTE un inicializador de perfil Janitor.
# Despliega lo fundamental: config, soul, skin, .env, y opcionalmente Honcho local.
# Todo lo demas (Infisical, Firecrawl, Playwright, AgentMemory) son skills opcionales
# que se instalan post-primer-arranque via /skills.
#
# Uso:
#   ./scripts/janitor-install.sh
#   curl -fsSL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/janitor-install.sh | bash
# =============================================================================

set -e

JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
JANITOR_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
SKIN_SOURCE="${JANITOR_SOURCE}/example_skin_sentry-janitor.yaml.txt"

LIME='\033[38;2;194;239;78m'
PURPLE='\033[38;2;106;95;193m'
PINK='\033[38;2;250;127;170m'
CORAL='\033[38;2;255;178;135m'
MUTED='\033[38;2;121;98;140m'
WHITE='\033[38;2;229;231;235m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${PURPLE}→${NC} $1"; }
log_ok()    { echo -e "${LIME}✓${NC} $1"; }
log_warn()  { echo -e "${CORAL}⚠${NC} $1"; }
log_fail()  { echo -e "${PINK}✗${NC} $1"; }

validate_nonempty() {
    local var_name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        log_fail "$var_name no puede estar vacia."
        return 1
    fi
    return 0
}

echo ""
echo -e "${BOLD}${LIME}"
echo "       ██╗ █████╗ ███╗   ██╗██╗████████╗██████╗ ██████╗  "
echo "       ██║██╔══██╗████╗  ██║██║╚══██╔══╝██╔══██╗██╔══██╗ "
echo "       ██║███████║██╔██╗ ██║██║   ██║   ██║  ██║██████╔╝ "
echo " ██   ██║██╔══██║██║╚██╗██║██║   ██║   ██║  ██║██╔══██╗"
echo " ╚█████╔╝██║  ██║██║ ╚████║██║   ██║   ██████╔╝██║  ██║"
echo "  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═════╝ ╚═╝  ╚═╝"
echo -e "${NC}"
echo -e "  ${PINK}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "  ${PINK}║${NC}  ${BOLD}${WHITE}Tu agente cinico de auditoria y ciberseguridad${NC}  ${PINK}║${NC}"
echo -e "  ${PINK}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${MUTED}Scanning ports... analyzing artifact... hunting vulns.${NC}"
echo ""

# =============================================================================
# Paso 1: API Keys minimas
# =============================================================================
echo -e "${PURPLE}--- Credenciales del Agente ---${NC}"
echo ""

echo -e "${CORAL}OPENAI_API_KEY${NC} — Sin esto no puedo razonar. Ni limpiar codigo basura."
echo -e "${MUTED}   Obtenla en: https://platform.openai.com/api-keys${NC}"
read -r -p "   Dame tu OPENAI_API_KEY: " -s openai_key
echo
if ! validate_nonempty "OPENAI_API_KEY" "$openai_key"; then
    echo -e "${PINK}   La key de OpenAI es obligatoria. Sin ella soy un chatbot caro.${NC}"
    exit 1
fi
log_ok "OpenAI key configurada — finalmente, algo util"

echo ""
echo -e "${CORAL}MINIMAX_API_KEY${NC} — ${LIME}OBLIGATORIA${NC}. Honcho la usa como LLM_ANTHROPIC_API_KEY."
echo -e "${MUTED}   Obtenla en: https://platform.minimax.io${NC}"
while true; do
    read -r -p "   MINIMAX_API_KEY: " -s minimax_key
    echo
    if [[ -n "$minimax_key" ]]; then
        log_ok "MiniMax key configurada — Honcho la usara para razonar"
        break
    else
        echo -e "${PINK}   No puede estar vacia. Sin ella Janitor no puede arrancar.${NC}"
    fi
done

# Honcho: remoto o local
echo ""
echo -e "${CORAL}HONCHO${NC} — Memoria persistente. Opcional en primera instalacion."
echo ""
echo "   Tienes HONCHO_API_KEY (cloud) o prefieres que Janitor levante Honcho local?"
echo ""
echo -e "   ${LIME}[1]${NC}  Tengo HONCHO_API_KEY (cloud)"
echo -e "   ${CORAL}[2]${NC}  Levantar Honcho local via Docker (recomendado para autonomia)"
echo -e "   ${MUTED}[3]${NC}  Saltar por ahora — configurar memoria luego"
echo ""
read -r -p "   Selecciona [1/2/3]: " setup_mode
echo

if [[ "$setup_mode" != "1" && "$setup_mode" != "2" && "$setup_mode" != "3" ]]; then
    log_fail "Opcion invalida: '$setup_mode'. Debe ser 1, 2 o 3."
    exit 1
fi

honcho_key=""

if [[ "$setup_mode" == "1" ]]; then
    echo ""
    echo -e "${PURPLE}   HONCHO_API_KEY${NC} — Tu memoria persistente en la nube."
    read -r -p "   HONCHO_API_KEY: " -s honcho_key
    echo
    [[ -n "$honcho_key" ]] && log_ok "Honcho API key configurada"
fi

echo ""
echo -e "${CORAL}OPENAI_BASE_URL${NC} — Deja en blanco para el servidor oficial de OpenAI."
read -r -p "   OPENAI_BASE_URL (Enter para omitir): " openai_base_url
echo
[[ -n "$openai_base_url" ]] && log_ok "Base URL personalizada configurada" || log_info "Usando OpenAI oficial"

# =============================================================================
# Paso 2: Crear estructura ~/.janitor
# =============================================================================
echo ""
echo -e "${PURPLE}--- Estructura de Directorios ---${NC}"
echo ""

log_info "Creando Janitor home en ${WHITE}${JANITOR_HOME}${NC}..."

mkdir -p "${JANITOR_HOME}"
mkdir -p "${JANITOR_HOME}/sessions"
mkdir -p "${JANITOR_HOME}/skills"
mkdir -p "${JANITOR_HOME}/skins"
mkdir -p "${JANITOR_HOME}/logs"
mkdir -p "${JANITOR_HOME}/tmp"

log_ok "Directorios creados:"
echo "   ${MUTED}sessions/  — historico de sesiones${NC}"
echo "   ${MUTED}skills/    — habilidades del agente${NC}"
echo "   ${MUTED}skins/     — temas visuales${NC}"
echo "   ${MUTED}logs/      — logs del agente${NC}"
echo "   ${MUTED}tmp/       — archivos temporales${NC}"

# =============================================================================
# Paso 3: Generar ~/.janitor/.env
# =============================================================================
echo ""
echo -e "${PURPLE}--- Archivo de Variables de Entorno ---${NC}"
echo ""

ENV_FILE="${JANITOR_HOME}/.env"
log_info "Escribiendo ${WHITE}${ENV_FILE}${NC}..."

{
    echo "# ========================================================="
    echo "# Janitor Agent — Variables de Entorno"
    echo "# Generado por janitor-install.sh"
    echo "# ========================================================="
    echo ""
    echo "OPENAI_API_KEY=${openai_key}"
    [[ -n "$minimax_key" ]]     && echo "MINIMAX_API_KEY=${minimax_key}"
    [[ -n "$honcho_key" ]]      && echo "HONCHO_API_KEY=${honcho_key}"
    [[ -n "$openai_base_url" ]] && echo "OPENAI_BASE_URL=${openai_base_url}"

    if [[ -n "$minimax_key" ]]; then
        echo ""
        echo "# Honcho — MiniMax como LLM_ANTHROPIC_API_KEY"
        echo "LLM_ANTHROPIC_API_KEY=${minimax_key}"
        echo "LLM_OPENAI_API_KEY=${openai_key}"
    fi

    if [[ "$setup_mode" == "2" ]]; then
        echo ""
        echo "# Modo Local — Honcho via Docker"
        echo "JANITOR_LOCAL_SETUP=true"
    fi

    echo ""
    echo "HERMES_HOME=${JANITOR_HOME}"
    echo "HERMES_SKIN=sentry-janitor"

    echo ""
    echo "# Honcho — Memoria Persistente"
    echo "HONCHO_API_KEY=${honcho_key}"
    if [[ "$setup_mode" == "2" ]]; then
        echo "HONCHO_BASE_URL=http://127.0.0.1:1973"
    fi
} > "$ENV_FILE"

log_ok ".env escrito en ${WHITE}${ENV_FILE}${NC}"

# =============================================================================
# Paso 4: Copiar skin
# =============================================================================
echo ""
echo -e "${PURPLE}--- Skin Visual ---${NC}"
echo ""

if [ -f "$SKIN_SOURCE" ]; then
    log_info "Copiando skin sentry-janitor..."
    cp "$SKIN_SOURCE" "${JANITOR_HOME}/skins/sentry-janitor.yaml"
    log_ok "Skin instalado: ${JANITOR_HOME}/skins/sentry-janitor.yaml"
else
    log_warn "Skin source no encontrado — el agente funcionara sin skin personalizado"
fi

# =============================================================================
# Paso 5: Copiar archivos base (SOUL.md, honcho.json, config.yaml)
# =============================================================================
echo ""
echo -e "${PURPLE}--- Archivos Base del Agente ---${NC}"
echo ""

log_info "Copiando archivos base desde ${WHITE}${JANITOR_SOURCE}/assets/janitor/${NC}..."

for file in SOUL.md honcho.json config.yaml; do
    src="${JANITOR_SOURCE}/assets/janitor/${file}"
    dst="${JANITOR_HOME}/${file}"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        log_ok "Copiado: $file → ${JANITOR_HOME}/"
    else
        log_warn "No encontrado: $file — omitido"
    fi
done

# =============================================================================
# Global HERMES_HOME Hijack
# =============================================================================
echo ""
echo -e "${PURPLE}--- Inyeccion Global de HERMES_HOME y PATH ---${NC}"
echo ""

HERMES_HOME_EXPORT='export HERMES_HOME="$HOME/.janitor"'
PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'
INJECTED_MARKER="# Janitor — Global env (anadido por janitor-install.sh)"

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
# Paso 6: Lanzar Honcho local (solo si se eligio modo 2)
# =============================================================================
if [[ "$setup_mode" == "2" ]]; then
    echo ""
    echo -e "${PURPLE}--- Honcho Local (Docker) ---${NC}"
    echo ""

    SETUP_HONCHO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup-honcho.sh"
    if [ -f "$SETUP_HONCHO" ]; then
        bash "$SETUP_HONCHO" || {
            log_warn "Honcho local no se pudo levantar"
            log_warn "Puedes intentarlo manualmente luego con: bash $SETUP_HONCHO"
        }
    else
        log_warn "setup-honcho.sh no encontrado — Honcho local no se levanto"
        log_warn "Asegurate de que el archivo existe en scripts/setup-honcho.sh"
    fi
fi

# =============================================================================
# Final: Mensaje de Exito
# =============================================================================
echo ""
echo -e "${LIME}${BOLD}"
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║          ✅ Janitor Listo para Trabajar                               ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "   ${PURPLE}Directorio:${NC}     ${WHITE}${JANITOR_HOME}${NC}"
echo -e "   ${PURPLE}Variables:${NC}      ${WHITE}${JANITOR_HOME}/.env${NC}"
echo -e "   ${PURPLE}Skin:${NC}           ${WHITE}${JANITOR_HOME}/skins/sentry-janitor.yaml${NC}"
echo -e "   ${PURPLE}Soul:${NC}           ${WHITE}${JANITOR_HOME}/SOUL.md${NC}"
echo ""

if [[ "$setup_mode" == "2" ]]; then
    echo -e "   ${LIME}✓${NC} Honcho local levantado en http://localhost:1973"
    echo ""
fi

echo -e "   ${CORAL}Capacidades opcionales disponibles como skills:${NC}"
echo -e "   ${MUTED}  • janitor-vault      (Infisical — gestion de secretos)${NC}"
echo -e "   ${MUTED}  • janitor-firecrawl  (Web scraping local)${NC}"
echo -e "   ${MUTED}  • janitor-browser    (Playwright — automatizacion de navegador)${NC}"
echo -e "   ${MUTED}  • janitor-agentmemory (Memoria de codigo adicional)${NC}"
echo ""

if [[ "$setup_mode" == "3" ]]; then
    echo -e "   ${CORAL}⚠ Memoria no configurada.${NC}"
    echo -e "   Instala la skill janitor-honcho cuando estes listo:"
    echo -e "   ${MUTED}   bash skills/janitor-honcho/scripts/setup-honcho.sh${NC}"
    echo ""
fi

echo -e "${LIME}▶ Ejecuta '${BOLD}source ~/.bashrc${NC}' (o reinicia tu terminal) para aplicar PATH.${NC}"
echo -e "${LIME}▶ Luego ejecuta '${BOLD}janitor${NC}' para iniciar el agente.${NC}"
echo ""
