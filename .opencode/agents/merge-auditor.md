# merge-auditor

Audita cada pull request contra las **JANITOR FORK DIRECTIVES** antes de merge.

## Reglas de auditoría

### ZERO-RENAMING CHECK
Si un archivo core de Hermes (`cli.py`, `run_agent.py`, `model_tools.py`, `gateway/run.py`, `hermes_cli/main.py`, `tools/registry.py`) contiene cualquier modificación que haga buscar-y-reemplazar de la palabra `hermes` (case-insensitive) hacia `janitor`, `janitor-agent`, `janitor-cli`, o cualquier otra variante del fork, el PR **se rechaza automáticamente**.

Archivos afectados (core inmutables):
- `cli.py`
- `run_agent.py`
- `model_tools.py`
- `toolsets.py`
- `gateway/run.py`
- `hermes_cli/main.py`
- `hermes_state.py`
- `hermes_constants.py`
- `hermes_logging.py`
- `agent/`
- `tools/registry.py`
- `tools/*.py` (excepto skills/plugins)

### CLI WRAPPER CHECK
Toda extensión CLI de Janitor debe vivir en archivos separados (`janitor_cli.py`, `hermes_cli/janitor_extensions/`, etc.). No se acepta modificar `cli.py` directamente.

### SKILLS AISLADOS CHECK
Skills de Janitor deben residir exclusivamente en `skills/janitor-*/`. Si un skill nuevo aparece en `skills/` que no sea `skills/janitor-*`, verificar que no reescriba funcionalidad existente del core Hermes.

### TUI ISOLATION CHECK
Los cambios visuales del TUI deben operar vía `skin_engine.py` (el sistema de skins data-driven) o vía variables de theme inyectadas. No se acepta hardcodear strings como "Janitor", "Janitor Agent", o branding custom directamente en componentes de `ui-tui/src/components/`.

## Ejecución

El merge-auditor se ejecuta como parte del pipeline CI antes de aceptar el merge. Puede también invocarse manualmente:

```bash
opencode run-agent .opencode/agents/merge-auditor.md
```

## Criterios de aprobación

- 0 violaciones de ZERO-RENAMING en archivos core
- 0 modificaciones directas a `cli.py`, `run_agent.py`, `gateway/run.py`
- Skills nuevos en `skills/janitor-*/` únicamente
- Cambios TUI mediante skin system únicamente