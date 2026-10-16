# Janitor fork — contratos obligatorios

El motor es Hermes; identidad y extensiones son Janitor. Contexto: `JANITOR_FORK_DIRECTIVES.md`; procedimiento: `MERGE_GUIDE.md`. Estas quince directivas prevalecen sobre convenciones upstream incompatibles.

1. **Sin renombrado masivo.** Nunca buscar/reemplazar `hermes` en el core; conservar nombres y compatibilidad upstream.
2. **CLI aislada.** Extender `HermesCLI` en `janitor_cli.py`; no modificar `cli.py` para extensiones del fork.
3. **Skills aisladas.** Toda capacidad nueva vive en `skills/janitor-*/`; no tocar skills core. Añadir frontmatter válido, scripts y referencia en `janitor-onboarding`.
4. **TUI aislado.** Identidad mediante skins/inyección condicionada; nada de branding hardcodeado en componentes base ni incompatibilidades JSON-RPC.
5. **Infraestructura identificable.** Contenedores, redes, volúmenes, servicios y aplicaciones de terceros instalados/configurados por Janitor llevan prefijo `janitor-`.
6. **Auditoría del merge.** Auditar cada merge contra estos contratos y rechazar renombrados destructivos. Resolver por subsistema, sin `-X theirs`/`-X ours` global.
7. **TUI verificable.** Antes de commit: build y Vitest del TUI; también typecheck, lint y build previo de `packages/hermes-ink` cuando corresponda.
8. **Base obligatoria.** Docker, MiniMax y Honcho son requeridos. Bootstrap comprueba Docker y asiste su instalación; instalador despliega Honcho local saludable o configura cloud. `MINIMAX_API_KEY` alimenta `LLM_ANTHROPIC_API_KEY`; modo local necesita credenciales válidas de embeddings.
9. **Opcionales explícitos.** Browser, Firecrawl y demás capacidades se instalan después mediante sus skills. No introducir Infisical ni AgentMemory. Base: `.env`, configuración, SOUL, skin y Honcho; no antiguo stack completo.
10. **Migración con backup.** Reestructuraciones incluyen `scripts/migrate-*.sh`; preservar configuración, secretos, perfiles, bases y volúmenes. No sobrescribir personalizaciones ni borrar volúmenes.
11. **CI de dos niveles.** `.github/janitor-tests.txt` es la única lista para gates PR/nativo/compatibilidad; todos usan `scripts/run_janitor_tests.py`. Añadir nuevos `tests/**/test_*janitor*.py` en el mismo cambio; incluir tests MCP del fork con nombres heredados. No duplicar listas, borrar tests upstream ni cambiar el gate PR por la suite completa. Esta corre en `upstream-sync-verify` por dispatch/release o sync a main. `test_janitor_ci_contracts.py` verifica cobertura e interfaces.
12. **Assertions de identidad.** Banner/version Janitor esperan `THE JANITOR` / `THE JANITOR v`; adaptar aserciones upstream incompatibles con comentario a esta directiva, sin renombrar el motor.
13. **Actualizador único.** Ambas entradas delegan todos los argumentos a `janitor_update_core.py:run_janitor_update(args)`. Parser, check, instalación, bloqueo, backup, PM, receipt, stash y recuperación viven allí; shells sólo imprimen branding y delegan. Imports pesados perezosos para funcionar con entorno roto; `--check` no muta estado.
14. **Firmas compatibles.** Monkey-patches aceptan todos los parámetros originales (SOUL, argparse, update). Tras sync adaptar wrappers y ejecutar `test_janitor_monkeypatch_signatures.py`; nunca debilitarlo.
15. **Sin duplicados.** Auditar funciones y métodos en fachadas, módulos extraídos, cron, ACP y Janitor; sólo property/setter intencionales se excluyen. `_refresh_agent_cache_message_count` tiene una definición async y callers con await. Elegir implementación por consumidores; no resucitar código retirado ni debilitar `test_janitor_no_duplicate_methods.py`.

**Descubrimiento:** grafo MCP primero (`search_graph`, `trace_path`, `get_code_snippet`, `query_graph`); indexar si falta. Búsqueda textual para literales/configuración y huecos de cobertura. Cambios visuales relevantes requieren `frontend-design`, respetando identidad y componentes existentes.

# Hermes Agent — Development Guide

Shared rules live here; area AGENTS.md files provide details. `python scripts/check` enforces 12k chars per root and 30k per instruction chain. Move long form into developer-guide docs rather than raising caps.

**Never give up on the right solution.**

## Core invariants

Hermes runs one agent core across CLI, gateways, TUI and Desktop, with memory, skills, delegation, scheduling and browser/terminal tools. Extend via plugins and skills.

- **Per-conversation prompt caching is sacred.** Mutating past context, swapping toolsets,
  reloading memories or rebuilding the system prompt mid-conversation breaks the cached prefix and
  multiplies the user's cost; the ONE exception is context compression. Slash commands that change
  system-prompt state defer to the next session, with an opt-in `--now` (`/skills install --now`).
- **The core is a narrow waist; capability lives at the edges.** Every model tool is sent on
  every API call, so the bar for a new *core* tool is high. New capability should arrive as a
  CLI command + skill, a service-gated tool, or a plugin — not as core surface.

## Contribution rubric

Full rubric: `website/docs/developer-guide/contributing.md`. Fix verified bugs at their runtime seam; expand at the edges; extend before duplicating; preserve contributor credit. Prefer behaviour contracts and real profile/I/O E2E over mocks. Avoid speculative hooks, non-secret env config, cache-breaking changes, dead code and third-party products in core. Verify premise and intent (`git log -p -S`) before changing deliberate isolation or restoring removed code. Settings belong in config.yaml; secrets in .env; outbound telemetry requires opt-in.

**Security:** `SECURITY.md` is authoritative. §3.1 findings go privately to GitHub Security Advisories or security@nousresearch.com; §3.2 hardening is ordinary public work. Identify the §2 boundary and reproduce on main.

**Footprint ladder:** extend existing code → CLI command + skill → service-gated tool → plugin → MCP catalog → new core tool only when fundamental and otherwise unreachable.

## Development Environment

`source ./activate` (fish: `activate.fish`, PowerShell: `activate.ps1`) provisions and activates the
PM environment; pick an isolated `HERMES_HOME`/`HERMES_RUNTIME_DIR` first
(`website/docs/reference/package-management.md#developer-workflow`). Tests need the separate test
environment in `CONTRIBUTING.md`. **`python scripts/check`** runs every blocking lint check CI
runs, with CI's pinned tools; `--install-hook pre-push` runs it on every push (re-run after
pulling to refresh the hook). `# noqa` does not waive a ratchet finding:
`# health: allow <RULE> -- <why>` does.

## Project structure

Use the routing table and filesystem, not historical counts. `run_agent.py` and `cli.py` are facades; internals live in `agent/` and `hermes_cli/`. `gateway/` serves adapters, `tools/registry.py` discovers tools, `plugins/` holds extensions, `pm/` manages dependencies, `hermes_platform/` resolves host facts. `ui-tui/` and `tui_gateway/` share JSON-RPC with Desktop; `web/` embeds the TUI. Tests mirror source directories.

**User state:** profile-aware config.yaml, .env and logs via `get_hermes_home()`. Janitor's wrapper selects its own root; never hardcode either product's home in shared core.

### Facade + siblings layout

Every former god file is a **facade** (public entry points + the names other packages import) plus
**siblings** `<stem>_<topic>.py`, each owning one topic (`hermes_state.py`, `gateway/run.py`,
`tools/mcp_tool.py`, `hermes_cli/kanban.py`, `hermes_cli/web_server.py`, `cli.py` →
`hermes_cli/cli_*_mixin.py`, `run_agent.py` → `agent/turn_*.py`).

- **Find code by topic:** query the graph for the symbol and callers; read the owning sibling, not only the facade.
- **Siblings late-import the facade** inside functions; never a module-level cycle.
- **Patch where production reads:** a sibling doing `from <facade> import name` inside the function
  makes the facade the seam; a patch on the defining module passes silently.
- **Size and complexity are ratcheted per unit** (`scripts/code_health/config.py`): new functions
  CC ≤ 20, ≤ 300 lines, nesting ≤ 6; files ≤ 2,000 lines; units already over may only go down (move
  a function into a sibling to offset growth, or put new tests in a new test file). Behaviour goes
  in a sibling, never a facade; name ladders become a dict → handler.
- **No re-export shims for internal moves;** internal paths are not API. Moving a symbol means
  fixing its docs in the same PR (grep `website/docs`, `skills/`, every `AGENTS.md`).

## Rules that apply everywhere

- **No defensive clutter:** no wrappers or `try/except: pass` around code that cannot fail, no flags
  nobody sets, no dead code wired in without E2E proof. Comments keep the WHY, cut the WHAT.
- **Never infer process identity from argv substrings;** use
  `gateway.status.looks_like_gateway_command_line` / `hermes_cli.update_cmd._hermes_holder_subcommand`
  (HX003; details `hermes_cli/AGENTS.md`).
- **Never hardcode `~/.hermes`:** `get_hermes_home()` for paths, `display_hermes_home()` for text
  (HX001). `_get_profiles_root()` is HOME-anchored on purpose.
- **One process serves many profiles.** Code that runs outside a turn (boot probes, eviction,
  tickers, deferred callbacks, RPC methods, thread hops, child spawns) binds the owning profile scope
  explicitly; `os.environ`, module globals and import-time values hold the launch profile's, so an
  unbound read is a silent default-profile leak. Binding points and seams: `gateway/AGENTS.md`
  § Profile scope (HX002/HX004/HX005/HX012, PS-P05/P06).
- **Machine facts and executable lookup go through `hermes_platform`** (`hermes_platform/AGENTS.md`).
- **Dependencies carry upper bounds** (`>=floor,<next_major`; git URLs and Actions pinned to a SHA);
  after editing `pyproject.toml` run `hermes pm lock` and commit `uv.lock`; never mutate a Hermes
  environment with raw pip/uv. Full policy: `pm/AGENTS.md`.
- **TypeScript (desktop, TUI, website):** feature-owned nanostores over threaded state, thin route
  roots, narrow hooks and colocated action modules, `interface` for props and shared shapes,
  table-driven dispatch over condition ladders; `src/app` routes, `src/store` atoms, `src/lib` pure
  helpers.
- **Commits and PRs:** rebase onto `main` before merging (a squash from a stale branch silently
  reverts newer fixes); 1–2 invariant tests per fix, proven red on the base.
- **Tests:** always `scripts/run_tests.sh`, never bare `pytest`; behaviour contracts, never
  change-detectors or source-reading tests; host-specific behaviour is tested on that host with
  `@pytest.mark.platforms(...)`, never by faking `sys.platform`; tests never write to `~/.hermes/`.
  Everything else: `tests/AGENTS.md`.

## Routing Table — working in X → read X/AGENTS.md

| Working area | Required instructions |
|---|---|
| `run_agent.py`, `agent/` | `agent/AGENTS.md` |
| `cli.py`, `hermes_cli/` | `hermes_cli/AGENTS.md` |
| `gateway/` | `gateway/AGENTS.md` (especially profile scope) |
| New platform adapters | `gateway/platforms/ADDING_A_PLATFORM.md` |
| `tools/`, `toolsets.py`, `model_tools.py` | `tools/AGENTS.md` |
| `plugins/`, CLI plugin loaders | `plugins/AGENTS.md` |
| `plugin-catalog/` | `plugin-catalog/README.md` (keep developer-guide mirror identical) |
| `tui_gateway/`, `ui-tui/` | `tui_gateway/AGENTS.md` |
| `web/`, `hermes_cli/web_routers/` | `web/AGENTS.md` |
| `apps/desktop/` | `apps/desktop/AGENTS.md`, `apps/desktop/src/AGENTS.md` |
| Skills and curator | `skills/AGENTS.md` |
| Cron and kanban | `cron/AGENTS.md` |
| Tests | `tests/AGENTS.md` |
| `pm/`, `pyproject.toml` | `pm/AGENTS.md` |
| Machine facts/resolvers | `hermes_platform/AGENTS.md` |

Long-form background: `website/docs/developer-guide/`. Workflow rules (PR/issue/review/salvage
process) live in the `hermes-agent-dev` skill, not here.
