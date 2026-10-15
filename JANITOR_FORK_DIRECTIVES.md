# Directivas detalladas del fork Janitor

`AGENTS.md` conserva todos los contratos operativos en forma resumida. Este documento conserva su contexto e incidentes históricos. El procedimiento de sincronización vigente está en `MERGE_GUIDE.md`: resolver por subsistema sin estrategias globales `-X theirs`/`-X ours`.

# JANITOR FORK DIRECTIVES (SUPREME RULES)

1. **ZERO-RENAMING POLICY**: Nunca hagas buscar-y-reemplazar de la palabra 'hermes' en el core. El motor subyacente se mantiene intacto para garantizar que `git pull upstream main` funcione sin conflictos destructivos.
2. **CLI WRAPPER**: Las extensiones de Janitor heredarán de `HermesCLI` en archivos separados (ej. `janitor_cli.py`). No se modifica `cli.py` original.
3. **SKILLS AISLADOS**: Toda habilidad nueva debe ir exclusivamente bajo `skills/janitor-*/`. Los skills del core Hermes nunca se tocan.
4. **TUI ISOLATION**: Los cambios visuales del TUI deben ser condicionados o inyectados vía el sistema de skins (`skin_engine.py`) sin destruir la compatibilidad del protocolo JSON-RPC. No se hace hardcode en los componentes base del TUI.
5. **NAMING CONVENTION (BRANDING)**: Todo contenedor Docker, red, volumen, servicio de sistema o aplicación de terceros que Janitor instale o configure en el futuro DEBE llevar obligatoriamente el prefijo `janitor-` (ej. `janitor-redis`, `janitor-network`). Sin excepciones.
6. **merge-auditor**: Cada merge debe ser auditado contra estas directivas. Si un PR introduce 'hermes' renombrado en archivos core, se rechaza automáticamente.
7. **tui-compilation**: Los cambios en el TUI requieren pasar `npm run build` Y `npm test` (vitest) ANTES de hacer commit. El pipeline CI de Janitor ejecuta esta habilidad como gate obligatorio.
8. **ESSENTIAL DEPENDENCIES**: Docker y Honcho son dependencias fundamentales del stack Janitor, no opcionales. El `bootstrap.sh` verifica la presencia de Docker y asiste en su instalacion (`get-docker.sh`) si falta. El `janitor-install.sh` despliega Honcho (modo Docker local) o solicita credenciales de Honcho cloud. `MINIMAX_API_KEY` es obligatoria porque es el proveedor de IA principal de Janitor (usada como `LLM_ANTHROPIC_API_KEY` por Honcho). Las capacidades restantes (Firecrawl, Browser) son skills opcionales bajo `skills/janitor-*/` que se instalan explicitamente post-primer-arranque.
9. **OPTIONAL SKILLS ARE EXPLICIT**: Tras la instalacion base (que incluye Docker + Honcho), el usuario puede ejecutar `janitor` inmediatamente. Las skills opcionales (Firecrawl, Browser) se instalan explicitamente post-arranque via `bash skills/janitor-*/scripts/deploy.sh`. Janitor no incluye Infisical ni AgentMemory en su stack — la gestion de secretos y memoria de codigo se maneja por otros mecanismos.
10. **MIGRATION SUPPORT**: Cada reestructuracion importante debe incluir un script de migracion (`scripts/migrate-*.sh`) para usuarios existentes, con backup automatico de configuracion.
11. **TEST PRUNING (TWO-TIER CI)**: El gate de PR (`tests.yml :: test`) corre únicamente el manifiesto canónico `.github/janitor-tests.txt`, mediante `scripts/run_janitor_tests.py` y el runner upstream `scripts/run_tests.sh`. `janitor-ci.yml :: python-tests`, el gate nativo de PR en `tests-os.yml :: os-tests` y el gate manual de compatibilidad ejecutan exactamente ese mismo manifiesto, en el mismo orden. Todo nuevo `tests/**/test_*janitor*.py` DEBE añadirse al manifiesto en el mismo cambio; los tests MCP del fork con nombres heredados también se incluyen. `tests/test_janitor_ci_contracts.py` verifica cobertura e interfaces workflow_call. No replicar listas de archivos en seis lugares. La suite completa upstream se ejecuta en `upstream-sync-verify` por dispatch manual, release o push a main cuyo mensaje incluya `chore(sync):`, `fix(sync):` o merge `upstream-sync-*`. **NO** se borran tests upstream ni se cambia el gate PR para ejecutar toda la suite. Los fallos de sync se investigan individualmente; no debilitar las invariantes para obtener verde.
12. **TEST ASSERTION BRANDING**: Toda aserción de test que compare contra el string del banner CLI (e.g. output de `--version`, el titulo del welcome banner) DEBE assertar sobre `THE JANITOR` / `THE JANITOR v`, NO sobre `Hermes Agent` / `Hermes Agent v`. Los commits de branding del fork re-aplican el string del banner Janitor en `hermes_cli/main.py` y `hermes_cli/banner.py`, pero los tests upstream siguen hardcodeando el string upstream. Cuando un nuevo test upstream introduzca el literal `Hermes Agent`, actualizar la aserción a `THE JANITOR` en el mismo commit y añadir un comentario inline que apunte a esta directiva. Ver `MERGE_GUIDE.md` para el checklist post-`git pull`.
13. **JANITOR UPDATE FLOW**: Both `janitor update` entry points — the early intercept in `janitor_cli.py` (`if sys.argv[1] == "update"`) and the monkey-patched `cmd_update` (also `janitor_cli.py:_janitor_cmd_update`) — delegate to a single shared core in `janitor_update_core.py:run_janitor_update(args)`. Any change to the update flow (pre-check, fetch, pull, fallback, post-pull validation, dependency install, stash handling, error recovery) lives in `janitor_update_core.py`. The entry-point shells in `janitor_cli.py` and `janitor_update_bootstrap.py` may ONLY print their branding banner and call the core. Rationale: the previous two-path design led to silent divergence — machine 2 of issue #N had a `git pull --ff-only` failure with no recovery path because the bootstrap path lacked the official's `git reset --hard origin/main` fallback. Helpers from `hermes_cli.main` are imported lazily inside the core so the early intercept still works on a partially-broken venv.
14. **MONKEY-PATCH SIGNATURE INVARIANTS**: `janitor_cli.py` monkey-patches several upstream functions at import time (currently: `prompt_builder.load_soul_md`, `argparse.ArgumentParser.__init__`, `hermes_cli.main.cmd_update`). Each wrapper's signature MUST stay compatible with the upstream function it replaces — it must accept every parameter the original accepts. When upstream adds a parameter to a patched function, the `chore(sync)` merge (`-X theirs`) adopts the new callee signature AND the new caller, but never touches `janitor_cli.py` (fork-only file, invisible to `-X theirs`), so the wrapper silently keeps the old signature and crashes at runtime with `TypeError: ... takes 0 positional arguments but 1 was given`. CI does not catch this because upstream tests mock the patched functions and the test environment never imports `janitor_cli`. **Enforcement**: `tests/test_janitor_monkeypatch_signatures.py` runs in the PR gate (directive #11) and verifies each wrapper accepts the upstream original's parameters. When a sync breaks this test, update the wrapper signature in `janitor_cli.py` to match — do NOT weaken the test. See `MERGE_GUIDE.md` §4.1 for the post-sync audit step.
15. **POST-SYNC DUPLICATE METHOD AUDIT**: When both the Janitor fork and upstream add a method with the same name to the same class in a core file (e.g. `gateway/run.py`), a `chore(sync)` merge with `-X theirs` resolves textual conflicts in upstream's favor but leaves both non-conflicting additions in place. Python's "last definition wins" rule then silently shadows the first definition with the second, which can change a method from `async` to `sync` (or vice versa) while callers still use the original calling convention — producing `TypeError: object NoneType can't be used in 'await' expression` at runtime. This is NOT caught by directive #14 (which only covers `janitor_cli.py` monkey-patches) nor by the PR gate's upstream tests (which mock the affected methods). **Real-world impact**: the v2026.7.7.2 sync (merge `83d4f8d62`) left duplicate `_refresh_agent_cache_message_count` definitions in `gateway/run.py` — the sync version shadowed the async one, and every Telegram message crashed AFTER generating the correct response, replacing it with "Sorry, I encountered an unexpected error". **Enforcement**: `tests/test_janitor_no_duplicate_methods.py` runs in the PR gate (directive #11) and scans the core facades `gateway/run.py`, `gateway/session.py`, `run_agent.py`, `cli.py` plus their extracted modules under `agent/`, `gateway/`, `hermes_cli/`, `tui_gateway/`, `tools/`, `providers/`, `plugins/platforms/` and all root Python modules for duplicate method definitions within the same class (excluding `@property`/`@.setter` pairs which are intentional) AND for duplicate module-level function definitions — the same v2026.7.7.2 merge left six duplicated top-level functions in `cli.py` and one (`_load_gateway_runtime_config`) in `gateway/run.py`; class-method scanning alone could not see them. It also locks the post-fix invariant for `_refresh_agent_cache_message_count`: exactly one definition, MUST be `async` (callers `await` it). When a sync breaks this test, identify which definition is correct (usually the Janitor fork's version with the more complete logic) and delete the other — do NOT weaken the test. See `MERGE_GUIDE.md` §4.1 for the post-sync audit step.

---

## Janitor Skills Architecture (Post-v5 Restructure)

### Philosophy

Janitor follows a **minimal installer + optional skills** model. The first-run installer
creates a functional agent with identity, configuration, skin, and required Honcho memory (local or cloud).
Everything else is delivered as opt-in skills that users install post-first-run.

### Installer Contract

`scripts/janitor-install.sh` deploys **only**:
- `~/.janitor/.env` — environment variables
- `~/.janitor/config.yaml` — agent configuration
- `~/.janitor/SOUL.md` — agent persona
- `~/.janitor/skins/sentry-janitor.yaml` — visual theme
- Required: Honcho local (via `scripts/setup-honcho.sh`) or cloud credentials

**Does NOT deploy by default**: Firecrawl, Browser, or full-stack systemd.

### Skill Hierarchy

All Janitor-specific capabilities live under `skills/janitor-*/`:

| Skill | Purpose | Former Location |
|-------|---------|-----------------|
| `janitor-honcho` | Local Honcho memory | `scripts/setup-stack.sh` (Honcho block) |
| `janitor-firecrawl` | Web scraping | `scripts/setup-stack.sh` (Firecrawl block) |
| `janitor-browser` | Playwright browser automation | `scripts/bootstrap.sh` |
| `janitor-onboarding` | Orientation guide | Formerly deployed 5 services |
| `janitor-core` | Cache cleaning and environment hygiene | Fork-native |
| `janitor-config-audit` | Config/SOUL.md drift audit | Fork-native |
| `janitor-code-review-agent` | Code review agent | Fork-native |
| `janitor-repo-research-agent` | GitHub repository research agent | Fork-native |
| `janitor-desktop-launcher` | Launch the compiled Janitor Desktop AppImage | Fork-native |
| `janitor-opendesign` | Open Design native agent registration | Fork-native |

Each skill contains:
- `SKILL.md` — metadata, description, install instructions
- `scripts/` — deployment/install scripts
- Compose files (if applicable) — scoped to that service only

### Adding a New Janitor Skill

1. Create directory: `skills/janitor-<name>/`
2. Write `SKILL.md` with valid frontmatter (name, description, version, platforms, metadata)
3. Add scripts under `skills/janitor-<name>/scripts/`
4. Reference the skill from `skills/janitor-onboarding/SKILL.md` so users can discover it
5. Do NOT modify core Hermes files or built-in skills

### User Workflow

```bash
# Fresh install — minimal
curl -fsSL .../bootstrap.sh | bash
janitor

# Post-install: add capabilities as needed
bash skills/janitor-firecrawl/scripts/deploy.sh
```

### Migration from Legacy Full-Stack

Users with old installs should run:
```bash
bash scripts/migrate-janitor-minimal.sh
```

This backs up config, detects Infisical shell RC snippets, offers secret export,
and cleans up configuration without deleting Docker volumes.

---

