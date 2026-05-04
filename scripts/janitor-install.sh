#!/bin/bash
# ============================================================================
# Janitor Installer v2 — Onboarding Aislado y Auto-Setup
# ============================================================================
#
# Per JANITOR FORK DIRECTIVES:
#   - CLI WRAPPER: Extends Hermes without modifying core
#   - TUI ISOLATION: Visual changes via skin_engine, not hardcode
#
# This installer:
#   1. Installs Hermes base (or uses existing installation)
#   2. Sets up Janitor at ~/.janitor (isolated from ~/.hermes)
#   3. Copies the sentry-janitor skin to ~/.janitor/skins/
#   4. Interactively collects API keys (OpenAI, MiniMax, Honcho/Firecrawl)
#   5. Writes ~/.janitor/.env with all credentials
#   6. Installs the janitor CLI entry point
#
# Usage:
#   curl -fsSL https://your-janitor-repo/scripts/janitor-install.sh | bash
#   Or: ./scripts/janitor-install.sh
#
# ============================================================================

set -e

# ── Aesthetic: Janitor dark terminal ──────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# ── Paths ───────────────────────────────────────────────────────────────────
JANITOR_HOME="${JANITOR_HOME:-$HOME/.janitor}"
HERMES_INSTALL_SCRIPT="$(dirname "$0")/install.sh"
JANITOR_SKINS_SOURCE="$(dirname "$0")/../example_skin_sentry-janitor.yaml.txt"

# ── Options ─────────────────────────────────────────────────────────────────
USE_VENV=true
RUN_SETUP=true
BRANCH="main"
SKIP_HERMES_INSTALL=false

# ── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-venv)
            USE_VENV=false
            shift
            ;;
        --skip-setup)
            RUN_SETUP=false
            shift
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --skip-hermes-install)
            SKIP_HERMES_INSTALL=true
            shift
            ;;
        -h|--help)
            echo "Janitor Installer v2 — Onboarding Aislado"
            echo ""
            echo "Usage: janitor-install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-hermes-install  Skip Hermes base install (use existing)"
            echo "  --no-venv             Do not create virtual environment"
            echo "  --skip-setup          Skip interactive setup wizard"
            echo "  --branch NAME         Git branch (default: main)"
            echo "  -h, --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
log_info()  { echo -e "${CYAN}→${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

ask_secret() {
    local prompt="$1"
    local var_name="$2"
    local value
    printf "%s" "$prompt"
    read -r value
    if [ -n "$value" ]; then
        echo "${var_name}=${value}"
    fi
}

ask_choice() {
    local prompt="$1"
    local var_name="$2"
    local value
    printf "%s" "$prompt"
    read -r value
    echo "${var_name}=${value}"
}

# ── Step 0: Detect non-interactive ──────────────────────────────────────────
if [ ! -t 0 ]; then
    log_warn "Non-interactive TTY detected. Using default credential collection."
    IS_INTERACTIVE=false
else
    IS_INTERACTIVE=true
fi

# ============================================================================
# Step 1: Install Hermes base (unless skipped)
# ============================================================================
if [ "${SKIP_HERMES_INSTALL}" != "true" ]; then
    log_info "Installing Hermes Agent base..."
    log_info "  (Hermes install.sh handles cloning, venv, and dependencies)"

    if [ -f "$HERMES_INSTALL_SCRIPT" ]; then
        chmod +x "$HERMES_INSTALL_SCRIPT"
        "$HERMES_INSTALL_SCRIPT" --branch "$BRANCH" $([ "$USE_VENV" = "false" ] && echo "--no-venv") $([ "$RUN_SETUP" = "false" ] && echo "--skip-setup") || {
            log_fail "Hermes install failed"
            exit 1
        }
    else
        log_warn "install.sh not found — skipping Hermes base install"
        log_info "Provide --skip-hermes-install if Hermes is already installed"
    fi
    log_ok "Hermes base installed"
else
    log_info "Skipping Hermes install (--skip-hermes-install)"
fi

# ============================================================================
# Step 2: Create ~/.janitor/ directory structure
# ============================================================================
log_info "Creating Janitor home at ${JANITOR_HOME}..."
mkdir -p "${JANITOR_HOME}"
mkdir -p "${JANITOR_HOME}/sessions"
mkdir -p "${JANITOR_HOME}/skills"
mkdir -p "${JANITOR_HOME}/skins"
mkdir -p "${JANITOR_HOME}/logs"
log_ok "Janitor home directory created"

# ============================================================================
# Step 3: Copy sentry-janitor skin
# ============================================================================
if [ -f "$JANITOR_SKINS_SOURCE" ]; then
    log_info "Installing sentry-janitor skin..."
    cp "$JANITOR_SKINS_SOURCE" "${JANITOR_HOME}/skins/sentry-janitor.yaml"
    log_ok "sentry-janitor skin installed at ${JANITOR_HOME}/skins/sentry-janitor.yaml"
else
    log_warn "Skin source not found at ${JANITOR_SKINS_SOURCE} — skipping skin install"
    log_info "The Janitor CLI will copy the skin from the repo at runtime if missing"
fi

# ============================================================================
# Step 4: Inject Janitor persona (SOUL.md)
# ============================================================================
SOUL_PATH="${JANITOR_HOME}/SOUL.md"
log_info "Injecting Janitor persona at $SOUL_PATH..."
cat > "$SOUL_PATH" << 'JANITOR_SOUL_EOF'
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
JANITOR_SOUL_EOF
log_ok "Janitor persona injected"

# ============================================================================
# Step 5: Generate ~/.janitor/config.yaml with Janitor defaults
# ============================================================================
CONFIG_PATH="${JANITOR_HOME}/config.yaml"
JANITOR_CONFIG_ADDITIONS='
memory:
  provider: honcho

display:
  tui: true
  skin: sentry-janitor

skills:
  config:
    janitor.cache_clean_days: 7
    janitor.dry_run: false
'

log_info "Generating Janitor config at $CONFIG_PATH..."
if [ -f "$CONFIG_PATH" ]; then
    log_info "Merging Janitor settings into existing config..."
    python3 - "$CONFIG_PATH" "$JANITOR_CONFIG_ADDITIONS" << 'PYTHON_EOF'
import sys, yaml

config_path = sys.argv[1]
additions_raw = sys.argv[2]
additions = yaml.safe_load(additions_raw)

with open(config_path, 'r') as f:
    config = yaml.safe_load(f) or {}

def deep_merge(base, overlay):
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

config = deep_merge(config, additions)

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
print("Config merged successfully")
PYTHON_EOF
    log_ok "config.yaml updated with Janitor settings"
else
    log_info "No existing config — creating fresh Janitor config..."
    python3 - "$JANITOR_CONFIG_ADDITIONS" << 'PYTHON_EOF'
import sys, yaml

additions_raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
additions = yaml.safe_load(additions_raw)

with open(sys.argv[2], 'w') as f if len(sys.argv) > 2 else open('/dev/stdout', 'w') as f:
    yaml.dump(additions, f, default_flow_style=False, sort_keys=False)
PYTHON_EOF
    log_ok "config.yaml created with Janitor defaults"
fi

# ============================================================================
# Step 6: Interactive API Key Collection
# ============================================================================
ENV_FILE="${JANITOR_HOME}/.env"
log_info "Collecting API keys interactively..."

# Initialize .env (clear previous if exists)
> "$ENV_FILE"

if [ "$IS_INTERACTIVE" = "true" ]; then
    echo ""
    echo -e "${MAGENTA}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}${BOLD}║           ⚡ JANITOR — Credential Setup                      ║${NC}"
    echo -e "${MAGENTA}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # OpenAI API Key
    echo -e "${CYAN}${BOLD}[1/4] OpenAI API Key${NC}"
    echo "  Required for LLM inference. Get yours at https://platform.openai.com/api-keys"
    read -r -p "  OPENAI_API_KEY: " -s openai_key
    echo
    if [ -n "$openai_key" ]; then
        echo "OPENAI_API_KEY=${openai_key}" >> "$ENV_FILE"
    fi

    # MiniMax API Key
    echo -e "${CYAN}${BOLD}[2/4] MiniMax API Key${NC}"
    echo "  Optional. Get yours at https://platform.minimax.io"
    read -r -p "  MINIMAX_API_KEY (optional, Enter to skip): " -s minimax_key
    echo
    if [ -n "$minimax_key" ]; then
        echo "MINIMAX_API_KEY=${minimax_key}" >> "$ENV_FILE"
    fi

    # Honcho / Firecrawl setup mode
    echo -e "${CYAN}${BOLD}[3/4] Memory & Scraping Setup${NC}"
    echo "  Janitor uses Honcho (memory) and Firecrawl (web scraping)."
    echo "  Choose how to configure them:"
    echo ""
    echo "    ${GREEN}[1]${NC} I have API keys — enter them now"
    echo "    ${YELLOW}[2]${NC} Run locally via Docker (no keys needed)"
    echo ""
    read -r -p "  Select option [1/2]: " setup_mode
    echo

    if [ "$setup_mode" = "1" ]; then
        # Honcho API Key
        read -r -p "  HONCHO_API_KEY: " -s honcho_key
        echo
        [ -n "$honcho_key" ] && echo "HONCHO_API_KEY=${honcho_key}" >> "$ENV_FILE"

        # Firecrawl API Key
        read -r -p "  FIRECRAWL_API_KEY (optional, Enter to skip): " -s firecrawl_key
        echo
        [ -n "$firecrawl_key" ] && echo "FIRECRAWL_API_KEY=${firecrawl_key}" >> "$ENV_FILE"

        log_ok "API keys saved to $ENV_FILE"
    else
        echo "JANITOR_LOCAL_SETUP=true" >> "$ENV_FILE"
        log_ok "Local setup mode enabled — Janitor will use Docker containers"
        log_info "Run '/onboard' after installation to start local services"
    fi

    # Agent Base URL (optional)
    echo -e "${CYAN}${BOLD}[4/4] Custom Model Base URL (optional)${NC}"
    read -r -p "  OPENAI_BASE_URL (Enter to skip, default: https://api.openai.com/v1): " base_url
    echo
    [ -n "$base_url" ] && echo "OPENAI_BASE_URL=${base_url}" >> "$ENV_FILE"

else
    log_warn "Non-interactive mode — creating .env with JANITOR_LOCAL_SETUP=true"
    echo "# Janitor .env — generated in non-interactive mode" >> "$ENV_FILE"
    echo "# Set API keys manually or run 'janitor --setup' interactively" >> "$ENV_FILE"
    echo "JANITOR_LOCAL_SETUP=true" >> "$ENV_FILE"
fi

log_ok ".env written to $ENV_FILE"

# ============================================================================
# Step 7: Install janitor CLI entry point
# ============================================================================
JANITOR_CLI_PATH="$(dirname "$0")/../janitor_cli.py"
REPO_ROOT="$(dirname "$0")/.."

if [ -f "$JANITOR_CLI_PATH" ]; then
    log_info "Installing janitor CLI entry point..."

    cd "$REPO_ROOT" || exit 1

    if [ -d ".venv" ]; then
        .venv/bin/pip install -e . >/dev/null 2>&1 && log_ok "Janitor CLI installed (.venv)" || log_warn "pip install failed"
    elif command -v uv >/dev/null 2>&1; then
        uv pip install -e . >/dev/null 2>&1 && log_ok "Janitor CLI installed (uv)" || log_warn "uv install failed"
    elif command -v pip >/dev/null 2>&1; then
        pip install -e . >/dev/null 2>&1 && log_ok "Janitor CLI installed (pip)" || log_warn "pip install failed"
    else
        log_warn "No pip/uv found — janitor command may not be on PATH"
    fi
else
    log_warn "janitor_cli.py not found at $JANITOR_CLI_PATH"
fi

# ============================================================================
# Done
# ============================================================================
echo ""
echo -e "${MAGENTA}${BOLD}"
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│              ⚡ Janitor v2 — Onboarding Aislado Complete!         │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo -e "${NC}"
echo ""
echo -e "${CYAN}${BOLD}📁 Janitor Files:${NC}"
echo "   ${YELLOW}Home:${NC}       $JANITOR_HOME"
echo "   ${YELLOW}Config:${NC}     $CONFIG_PATH"
echo "   ${YELLOW}.env:${NC}       $ENV_FILE"
echo "   ${YELLOW}Personality:${NC} $SOUL_PATH"
echo "   ${YELLOW}Skin:${NC}       $JANITOR_HOME/skins/sentry-janitor.yaml"
echo ""
echo -e "${CYAN}${BOLD}🚀 Commands:${NC}"
echo ""
echo -e "   ${GREEN}janitor${NC}           Start Janitor (isolated at ~/.janitor/)"
echo -e "   ${GREEN}hermes${NC}            Start Hermes (original, at ~/.hermes/)"
echo ""
if grep -q "JANITOR_LOCAL_SETUP=true" "$ENV_FILE" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Local mode enabled. Run '/onboard' inside Janitor to start Docker services.${NC}"
else
    echo -e "${GREEN}✓ API keys configured. Janitor ready to run.${NC}"
fi
echo ""