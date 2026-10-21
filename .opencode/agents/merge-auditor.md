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
Toda extensión CLI de Janitor debe vivir en el paquete `janitor/` (lanzador `janitor/cli.py`, plugin `janitor/plugin/`). No se acepta modificar `cli.py` directamente; toda edición en un archivo upstream debe estar declarada como touchpoint en `janitor/overlay.yaml` (`python -m janitor.overlay check`).

### SKILLS AISLADOS CHECK
Skills de Janitor deben residir exclusivamente en `janitor/skills/<grupo>/janitor-*/` (grupos `core`, `services`, `agents`, `integrations`). Los árboles `skills/` y `optional-skills/` son de upstream: un skill Janitor ahí es una violación.

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
- Skills nuevos en `janitor/skills/<grupo>/janitor-*/` únicamente
- `scripts/janitor-sync-verify.sh` en verde
- Cambios TUI mediante skin system únicamente