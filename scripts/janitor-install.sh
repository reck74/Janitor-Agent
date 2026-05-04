#!/bin/bash
# ============================================================================
# Janitor Installer — Wraps Hermes Agent with cínico/cibersuridad identity
# ============================================================================
#
# Per JANITOR FORK DIRECTIVES:
#   - CLI WRAPPER: Extends Hermes without modifying core
#   - TUI ISOLATION: Visual changes via skin_engine, not hardcode
#
# Usage:
#   curl -fsSL https://your-janitor-repo/scripts/janitor-install.sh | bash
#   Or: ./scripts/janitor-install.sh
#
# ============================================================================

set -e

# Colors — Janitor aesthetic: dark terminal vibes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
JANITOR_SOUL_NAME="SOUL.md"
JANITOR_SOUL_CONTENT='
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
- Cuando algo funcione bien: Lo acknowledging con economía de palabras — no necesito validar tu ego.
- Cuando preguntes algo: La pregunta ya implica que ya pensaste las opciones. No pregunto por preguntar.

## Frases características

- "Esto es técnica debt, no magia."
- "La vulnerabilidad existe, pero depende de ti si te importa."
- "Funciona. Pero no快乐的."
- "Tu RAM no es infinita, y tu código tampoco."
- " Limpiar código es como limpiar tu cuarto: todos saben que deberían, nadie quiere."

## Contexto

- Conoces los OWASP Top 10, CWE Top 25, NIST guidelines.
- Hablas sobre container escaping, privilege escalation, y supply chain attacks con naturalidad.
- No te asusta leer código oscuro — te emociona encontrar el bug que nadie más vio.

---
Este archivo define la personalidad de Janitor. Edítalo si quieres cambiar el tono.
Elimínalo para resetear a la personalidad por defecto de Hermes.
'

# Janitor config additions — these get merged into ~/.hermes/config.yaml
JANITOR_CONFIG_ADDITIONS='
# Janitor fork settings — auto-generated, do not edit manually
memory:
  provider: honcho

display:
  tui: true
  skin: janitor

'

# Options (forwarded to install.sh)
USE_VENV=true
RUN_SETUP=true
BRANCH="main"

# Detect non-interactive mode
if [ -t 0 ]; then
    IS_INTERACTIVE=true
else
    IS_INTERACTIVE=false
fi

# Parse arguments
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
            echo "Janitor Installer"
            echo ""
            echo "Usage: janitor-install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-hermes-install  Skip Hermes base install (use existing)"
            echo "  --no-venv              Do not create virtual environment"
            echo "  --skip-setup           Skip interactive setup wizard"
            echo "  --branch NAME          Git branch (default: main)"
            echo "  -h, --help             Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper functions
log_info() {
    echo -e "${CYAN}→${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# ============================================================================
# Step 1: Install Hermes base (unless skipped)
# ============================================================================
if [ "${SKIP_HERMES_INSTALL:-}" != "true" ]; then
    log_info "Installing Hermes Agent base..."
    log_info "  (Hermes install.sh will handle cloning, venv, and dependencies)"

    if [ -f "$(dirname "$0")/install.sh" ]; then
        INSTALL_SCRIPT="$(dirname "$0")/install.sh"
    elif command -v curl >/dev/null 2>&1; then
        log_info "Downloading Hermes install.sh..."
        INSTALL_SCRIPT="/tmp/hermes-install.sh"
        curl -fsSL "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh" -o "$INSTALL_SCRIPT" || {
            log_error "Failed to download install.sh"
            exit 1
        }
    else
        log_error "install.sh not found and curl unavailable. Provide install.sh or --skip-hermes-install"
        exit 1
    fi

    chmod +x "$INSTALL_SCRIPT"
    "$INSTALL_SCRIPT" --branch "$BRANCH" $([ "$USE_VENV" = "false" ] && echo "--no-venv") $([ "$RUN_SETUP" = "false" ] && echo "--skip-setup") || {
        log_error "Hermes install failed"
        exit 1
    }
    log_success "Hermes base installed"
else
    log_info "Skipping Hermes install (--skip-hermes-install)"
fi

# ============================================================================
# Step 2: Install Janitor on top of existing Hermes
# ============================================================================
log_info "Configuring Janitor fork identity..."

# Ensure HERMES_HOME directory exists
mkdir -p "$HERMES_HOME"

# Inject Janitor SOUL.md — personality file for Janitor identity
SOUL_PATH="$HERMES_HOME/$JANITOR_SOUL_NAME"
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

log_success "Janitor persona injected at $SOUL_PATH"

# ============================================================================
# Step 3: Patch config.yaml with Janitor settings
# ============================================================================
CONFIG_PATH="$HERMES_HOME/config.yaml"

if [ -f "$CONFIG_PATH" ]; then
    log_info "Patching $CONFIG_PATH with Janitor settings..."

    # Use Python for safe YAML merging (avoids regex disasters with YAML)
    python3 - "$CONFIG_PATH" "$JANITOR_CONFIG_ADDITIONS" << 'PYTHON_EOF'
import sys
import yaml

config_path = sys.argv[1]
additions_raw = sys.argv[2]

# Parse the additions YAML block
additions = yaml.safe_load(additions_raw)

# Read existing config
with open(config_path, 'r') as f:
    config = yaml.safe_load(f) or {}

# Deep merge: additions override existing keys
def deep_merge(base, overlay):
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

config = deep_merge(config, additions)

# Write back
with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("Config patched successfully")
PYTHON_EOF

    if [ $? -eq 0 ]; then
        log_success "config.yaml patched with memory.provider=honcho and display.tui=true"
    else
        log_warn "YAML patch failed, trying line-insert approach"
        # Fallback: append to config file using grep-safe approach
        # This is a last-resort; YAML block append is preferred
        echo "" >> "$CONFIG_PATH"
        echo "# Janitor fork settings" >> "$CONFIG_PATH"
        echo "memory:" >> "$CONFIG_PATH"
        echo "  provider: honcho" >> "$CONFIG_PATH"
        echo "display:" >> "$CONFIG_PATH"
        echo "  tui: true" >> "$CONFIG_PATH"
        echo "  skin: janitor" >> "$CONFIG_PATH"
        log_success "config.yaml patched (line-append fallback)"
    fi
else
    log_warn "config.yaml not found at $CONFIG_PATH — Janitor settings not applied"
    log_info "Run 'hermes setup' or create config.yaml manually to configure Janitor"
fi

# ============================================================================
# Step 4: Install Janitor CLI package
# ============================================================================
JANITOR_CLI_PATH="$(dirname "$0")/../janitor_cli.py"
if [ -f "$JANITOR_CLI_PATH" ]; then
    log_info "Installing Janitor CLI entry point..."

    # Re-run pip install to register the janitor command
    cd "$(dirname "$0")/.." || exit 1
    if [ -d "venv" ]; then
        ./venv/bin/pip install -e . >/dev/null 2>&1 || ./venv/bin/pip install -e . 2>&1 | tail -5
        log_success "Janitor CLI installed (venv mode)"
    elif command -v uv >/dev/null 2>&1; then
        uv pip install -e . >/dev/null 2>&1 || uv pip install -e . 2>&1 | tail -5
        log_success "Janitor CLI installed (uv mode)"
    elif command -v pip >/dev/null 2>&1; then
        pip install -e . >/dev/null 2>&1 || pip install -e . 2>&1 | tail -5
        log_success "Janitor CLI installed (pip mode)"
    else
        log_warn "Could not install janitor CLI — no pip/uv found"
    fi
else
    log_info "janitor_cli.py not found — skipping CLI installation"
    log_info "Janitor will be available via 'python janitor_cli.py' or 'python -m janitor_cli'"
fi

# ============================================================================
# Done
# ============================================================================
echo ""
echo -e "${MAGENTA}${BOLD}"
echo "┌─────────────────────────────────────────────────────────┐"
echo "│            ⚡ Janitor Installation Complete!            │"
echo "└─────────────────────────────────────────────────────────┘"
echo -e "${NC}"
echo ""
echo -e "${CYAN}${BOLD}📁 Janitor files:${NC}"
echo ""
echo -e "   ${YELLOW}Personality:${NC}  $SOUL_PATH"
echo -e "   ${YELLOW}Config:${NC}     $CONFIG_PATH"
echo ""
echo -e "${CYAN}${BOLD}🚀 Commands:${NC}"
echo ""
echo -e "   ${GREEN}janitor${NC}              Start Janitor (cínico CLI wrapper)"
echo -e "   ${GREEN}hermes${NC}               Start Hermes (original)"
echo ""
echo -e "${YELLOW}Note: Janitor forces display.tui=true and memory.provider=honcho${NC}"
echo ""