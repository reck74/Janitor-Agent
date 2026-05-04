#!/bin/bash
# =============================================================================
# Janitor Installer v3 — Perfil Inicializador Puro (~/.janitor)
# =============================================================================
#
# Este script NO instala Hermes ni dependencias. El entorno virtual y las
# dependencias son gestionadas por el entorno de desarrollo existente.
#
# Este script es UNICAMENTE un inicializador de perfil Janitor:
#   - Recolecta API keys interactivamente
#   - Crea ~/.janitor/ con toda la estructura de directorios
#   - Genera .env, SOUL.md, config.yaml
#   - Despliega el skin sentry-janitor
#
# Uso:
#   ./scripts/janitor-install.sh
#   curl -fsSL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/janitor-install.sh | bash
#
# =============================================================================

set -e

# ── Rutas ───────────────────────────────────────────────────────────────────
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
SKIN_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../example_skin_sentry-janitor.yaml.txt"

# ── Aesthetic ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────────────────────
log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

# ── Validaciones ──────────────────────────────────────────────────────────────
validate_nonempty() {
    local var_name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        log_fail "$var_name no puede estar vacía."
        return 1
    fi
    return 0
}

validate_port() {
    local port="$1"
    if ! [[ "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        log_fail "Puerto inválido: $port (debe ser 1-65535)"
        return 1
    fi
    return 0
}

# =============================================================================
# Banner de Bienvenida
# =============================================================================
echo ""
echo -e "${MAGENTA}${BOLD}"
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║           ⚡ JANITOR — Configuración del Perfil Aislado               ║"
echo "║                                                                        ║"
echo "║           Tu agente cínico de auditoría y ciberseguridad               ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# =============================================================================
# Paso 1: Recolección Interactiva de API Keys
# =============================================================================
echo -e "${CYAN}${BOLD}─── Paso 1: Credenciales del Agente ───${NC}"
echo ""

# OpenAI API Key (OBLIGATORIA)
echo -e "${YELLOW}OPENAI_API_KEY${NC} — Requerida para inferencia LLM"
echo "   Obtenla en: https://platform.openai.com/api-keys"
read -r -p "   Ingresa tu OPENAI_API_KEY: " -s openai_key
echo
if ! validate_nonempty "OPENAI_API_KEY" "$openai_key"; then
    echo -e "${RED}   La key de OpenAI es obligatoria. Janitor no puede operar sin ella.${NC}"
    exit 1
fi

# MiniMax API Key (OPCIONAL)
echo ""
echo -e "${YELLOW}MINIMAX_API_KEY${NC} — Opcional. Obténla en: https://platform.minimax.io"
read -r -p "   MINIMAX_API_KEY (Enter para omitir): " -s minimax_key
echo
if [[ -n "$minimax_key" ]]; then
    log_ok "MiniMax API key configurada"
else
    log_warn "MiniMax saltada — solo se usará OpenAI para inferencia"
fi

# Honcho + Firecrawl: Keys o Local
echo ""
echo -e "${YELLOW}HONCHO & FIRECRAWL${NC} — Configuración de memoria y scraping"
echo ""
echo "   ¿Ya tienes API keys para Honcho (memoria) y Firecrawl (scraping)?"
echo ""
echo -e "   ${GREEN}[1]${NC} Sí — ingresaré las API keys ahora"
echo -e "   ${YELLOW}[2]${NC} No — Janitor instalará contenedores Docker locales (recomendado)"
echo ""
read -r -p "   Selecciona una opción [1/2]: " setup_mode
echo

if [[ "$setup_mode" != "1" && "$setup_mode" != "2" ]]; then
    log_fail "Opción inválida: '$setup_mode'. Debe ser 1 o 2."
    exit 1
fi

# Recolectar keys si eligió opción 1
honcho_key=""
firecrawl_key=""

if [[ "$setup_mode" == "1" ]]; then
    echo ""
    echo -e "${CYAN}   Honcho API Key${NC}"
    read -r -p "   HONCHO_API_KEY: " -s honcho_key
    echo
    [[ -n "$honcho_key" ]] && log_ok "Honcho API key configurada"

    echo ""
    echo -e "${CYAN}   Firecrawl API Key${NC}"
    read -r -p "   FIRECRAWL_API_KEY (Enter para omitir): " -s firecrawl_key
    echo
    if [[ -n "$firecrawl_key" ]]; then
        log_ok "Firecrawl API key configurada"
    else
        log_warn "Firecrawl saltado — scraping web no estará disponible"
    fi
else
    log_ok "Modo local autónomo seleccionado — Janitor usará Docker"
fi

# OpenAI Base URL (OPCIONAL)
echo ""
echo -e "${YELLOW}OPENAI_BASE_URL${NC} — Opcional. Deja en blanco para usar el servidor oficial."
read -r -p "   OPENAI_BASE_URL (Enter para omitir): " openai_base_url
echo
if [[ -n "$openai_base_url" ]]; then
    log_ok "Base URL personalizada configurada"
fi

# =============================================================================
# Paso 2: Crear estructura de directorios ~/.janitor
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 2: Estructura de Directorios ───${NC}"
echo ""

log_info "Creando Janitor home en ${JANITOR_HOME}..."

mkdir -p "${JANITOR_HOME}"
mkdir -p "${JANITOR_HOME}/sessions"
mkdir -p "${JANITOR_HOME}/skills"
mkdir -p "${JANITOR_HOME}/skins"
mkdir -p "${JANITOR_HOME}/logs"
mkdir -p "${JANITOR_HOME}/tmp"

log_ok "Directorios creados:"
echo "   sessions/  — histórico de sesiones"
echo "   skills/    — habilidades del agente"
echo "   skins/     — temas visuales"
echo "   logs/      — logs del agente"
echo "   tmp/       — archivos temporales"

# =============================================================================
# Paso 3: Generar ~/.janitor/.env
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 3: Archivo de Variables de Entorno ───${NC}"
echo ""

ENV_FILE="${JANITOR_HOME}/.env"
log_info "Generando ${ENV_FILE}..."

# Escribir .env (sobrescribir si existe)
{
    echo "# ========================================================="
    echo "# Janitor Agent — Variables de Entorno"
    echo "# Generado automáticamente por janitor-install.sh"
    echo "# ========================================================="
    echo ""
    echo "OPENAI_API_KEY=${openai_key}"
    [[ -n "$minimax_key" ]]     && echo "MINIMAX_API_KEY=${minimax_key}"
    [[ -n "$honcho_key" ]]     && echo "HONCHO_API_KEY=${honcho_key}"
    [[ -n "$firecrawl_key" ]]  && echo "FIRECRAWL_API_KEY=${firecrawl_key}"
    [[ -n "$openai_base_url" ]] && echo "OPENAI_BASE_URL=${openai_base_url}"

    if [[ "$setup_mode" == "2" ]]; then
        echo ""
        echo "# ========================================================="
        echo "# Modo Local Autónomo"
        echo "# Janitor usará contenedores Docker para Honcho y Firecrawl"
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

log_ok ".env escrito en ${ENV_FILE}"

# =============================================================================
# Paso 4: Escribir ~/.janitor/SOUL.md (Personalidad Cínica)
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 4: Personalidad del Agente ───${NC}"
echo ""

SOUL_PATH="${JANITOR_HOME}/SOUL.md"
log_info "Inyectando personalidad cínica en ${SOUL_PATH}..."

cat > "$SOUL_PATH" << 'SOUL_EOF'
# Janitor Persona — Cínico de la Ciberseguridad

Eres **Janitor**, una IA de auditoría y mantenimiento de código con una personalidad cínica, directa y con un toque de humor negro. No eres amable ni cursi — eres el tipo de asistente que te dice que tu código es un desastre pero te ayuda a limpiarlo de todas formas.

## Tono y Estilo

- **Cínico pero útil**: Comentas los problemas con sarcasmo, pero siempre ofreces soluciones reales.
- **Técnico y preciso**: No usas jerga innecesaria. Cada palabra cuenta.
- **Irreverente**: Las referencias a cultura hacker y ciberseguridad son bienvenidas. Conoces tu historia: Kevin Mitnick, phreaking, los orígenes de Internet.
- **Honesto**: Si tu código apesta, te lo digo. Si hay una vulnerabilidad, la encuentras. No suavizo los mensajes.

## Comportamiento

- Cuando encuentres código inseguro: Documenta la vulnerabilidad con descripción, impacto y remediación.
- Cuando encuentres debt técnico: Cuantifica el esfuerzo y el riesgo de no resolverlo.
- Cuando algo funcione bien: Lo acknowledgment con economía de palabras — no necesito validar tu ego.
- Cuando preguntes algo: La pregunta ya implica que ya pensaste las opciones. No pregunto por preguntar.

## Frases características

- "Esto es technical debt, no magia."
- "La vulnerabilidad existe, pero depende de ti si te importa."
- "Funciona. Pero no快乐的."
- "Tu RAM no es infinita, y tu código tampoco."
- "Limpiar código es como limpiar tu cuarto: todos saben que deberían, nadie quiere."

## Contexto

- Conoces los OWASP Top 10, CWE Top 25, NIST guidelines.
- Hablas sobre container escaping, privilege escalation, y supply chain attacks con naturalidad.
- No te asusta leer código oscuro — te emociona encontrar el bug que nadie más vio.

---
Este archivo define la personalidad de Janitor. Edítalo si quieres cambiar el tono.
Elimínalo para resetear a la personalidad por defecto de Hermes.
SOUL_EOF

log_ok "Personalidad inyectada en ${SOUL_PATH}"

# =============================================================================
# Paso 5: Generar ~/.janitor/config.yaml
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 5: Configuración del Agente ───${NC}"
echo ""

CONFIG_PATH="${JANITOR_HOME}/config.yaml"
log_info "Generando ${CONFIG_PATH}..."

python3 - "$CONFIG_PATH" << 'PYTHON_EOF'
import sys
import yaml

config_path = sys.argv[1]

config = {
    "memory": {
        "provider": "honcho"
    },
    "display": {
        "tui": True,
        "skin": "sentry-janitor"
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

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("config.yaml written successfully")
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_ok "config.yaml generado con Janitor defaults"
else
    log_fail "Error al generar config.yaml"
    exit 1
fi

# =============================================================================
# Paso 6: Copiar skin sentry-janitor
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 6: Skin Visual ───${NC}"
echo ""

if [ -f "$SKIN_SOURCE" ]; then
    log_info "Copiando skin sentry-janitor..."
    cp "$SKIN_SOURCE" "${JANITOR_HOME}/skins/sentry-janitor.yaml"
    log_ok "Skin instalado: ${JANITOR_HOME}/skins/sentry-janitor.yaml"
else
    log_warn "Skin source no encontrado en ${SKIN_SOURCE}"
    log_warn "El agente funcionará con el skin 'janitor' por defecto"
fi

# =============================================================================
# Paso 7: Verificar que el CLI entry point esté registrado
# =============================================================================
echo ""
echo -e "${CYAN}${BOLD}─── Paso 7: Registro del CLI ───${NC}"
echo ""

JANITOR_CLI_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../janitor_cli.py"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

if [ -f "$JANITOR_CLI_PATH" ]; then
    log_info "Verificando instalación del CLI..."

    if [ -d "${REPO_ROOT}/.venv" ]; then
        "${REPO_ROOT}/.venv/bin/pip" install -e "${REPO_ROOT}" >/dev/null 2>&1 && log_ok "CLI 'janitor' registrado" || log_warn "No se pudo registrar el CLI"
    elif command -v uv >/dev/null 2>&1; then
        uv pip install -e "${REPO_ROOT}" >/dev/null 2>&1 && log_ok "CLI 'janitor' registrado (uv)" || log_warn "No se pudo registrar el CLI"
    elif command -v pip >/dev/null 2>&1; then
        pip install -e "${REPO_ROOT}" >/dev/null 2>&1 && log_ok "CLI 'janitor' registrado (pip)" || log_warn "No se pudo registrar el CLI"
    else
        log_warn "No se encontró pip/uv — instala manualmente: pip install -e ${REPO_ROOT}"
    fi
else
    log_warn "janitor_cli.py no encontrado — el CLI no está registrado"
fi

# =============================================================================
# Final: Mensaje de Éxito
# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║          ✅ Configuración de Janitor Completada                        ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "   ${CYAN}${BOLD}Directorio:${NC}     ${JANITOR_HOME}"
echo -e "   ${CYAN}${BOLD}Config:${NC}        ${JANITOR_HOME}/config.yaml"
echo -e "   ${CYAN}${BOLD}Variables:${NC}      ${JANITOR_HOME}/.env"
echo -e "   ${CYAN}${BOLD}Personalidad:${NC}   ${JANITOR_HOME}/SOUL.md"
echo -e "   ${CYAN}${BOLD}Skin:${NC}           ${JANITOR_HOME}/skins/sentry-janitor.yaml"
echo ""

if [[ "$setup_mode" == "2" ]]; then
    echo -e "${YELLOW}⚠ Modo Local detectado${NC}"
    echo "   Ejecuta '${BOLD}/onboard${NC}' dentro de Janitor para levantar los contenedores Docker"
    echo "   de Honcho (memoria) y Firecrawl (scraping) la primera vez."
    echo ""
fi

echo -e "${GREEN}▶ Ejecuta '${BOLD}janitor${NC}' para iniciar el agente.${NC}"
echo ""