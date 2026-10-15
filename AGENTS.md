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

# Hermes Agent - Development Guide

For AI coding assistants and developers working on hermes-agent. This root file is a hub: what
applies everywhere, then a routing table. Each area's `AGENTS.md` loads automatically when you work
in that directory; read it before editing there. `python scripts/check` caps this file at 12k chars
and every root-to-area chain at 30k, so it loads whole on 128k+ models: long form goes in the guide.

**Never give up on the right solution.**

## What Hermes Is

Hermes is a personal AI agent that runs the same agent core across a CLI, a messaging
gateway (Telegram, Discord, Slack, ~20 platforms), a TUI, and an Electron desktop app. It
learns across sessions (memory + skills), delegates to subagents, runs scheduled jobs, and
drives a real terminal and browser. It is extended primarily through **plugins and skills**,
not by growing the core.

Two invariants shape almost every design decision and are the lens for reviewing any change:

- **Per-conversation prompt caching is sacred.** Mutating past context, swapping toolsets,
  reloading memories or rebuilding the system prompt mid-conversation breaks the cached prefix and
  multiplies the user's cost; the ONE exception is context compression. Slash commands that change
  system-prompt state defer to the next session, with an opt-in `--now` (`/skills install --now`).
- **The core is a narrow waist; capability lives at the edges.** Every model tool is sent on
  every API call, so the bar for a new *core* tool is high. New capability should arrive as a
  CLI command + skill, a service-gated tool, or a plugin — not as core surface.

## Contribution rubric

The project's intent layer, for contributors and for the triage sweeper (which may only close on
`implemented_on_main`, `cannot_reproduce` or `incoherent`; taste-based closes are a maintainer's
call, and when in doubt a PR stays open). Long form with examples:
`website/docs/developer-guide/contributing.md` § Contribution rubric.

**Wanted:** real bug fixes (repro on `main`, the exact line, the whole class incl. sibling paths);
reach at the edges (adapters, providers, models, UI features) wired into the existing setup UX;
god-file → module refactors; extending before duplicating (3+ PRs in one category → an ABC +
orchestrator); behaviour-contract tests; E2E with real imports against a temp `HERMES_HOME` for
resolution, config, security and I/O changes; salvage by cherry-pick so authorship survives.

**Rejected even when well-built:** hooks with no concrete consumer; new `HERMES_*` env vars for
non-secret config (`.env` is secrets only, behaviour goes in `config.yaml`); a new core tool when
terminal + file or a skill already does the job; `offset`/`limit` pagination on instructional tools;
"fixes" that destroy the feature they secure; outbound telemetry without an opt-in gate;
change-detector tests; plugins that touch core files; third-party products in the core tree (ship a
standalone plugin repo).

**Before you call it a bug,** verify the claim AND the intent (`git log -p -S "<symbol>"`): the
isolation is often the design (profiles are islands on purpose), an absence can be load-bearing,
and a fix that cannot point to the line where the bug manifests has an unverified premise.

**Security:** `SECURITY.md` is the scope authority. A §3.1 finding goes private (GitHub Security
Advisories or security@nousresearch.com), never into a public issue, PR, commit or comment; §3.2
hardening is ordinary public work. Name the §2 boundary crossed, with a repro on `main`.

**Footprint ladder** (take the highest rung that solves it): extend existing code → CLI command +
skill → service-gated tool (`check_fn` answers reachability/opt-in, never per-session surface:
`tools/AGENTS.md`) → plugin → MCP server in the catalog → new core tool (fundamental, broadly useful,
unreachable otherwise).

## Development Environment

`source ./activate` (fish: `activate.fish`, PowerShell: `activate.ps1`) provisions and activates the
PM environment; pick an isolated `HERMES_HOME`/`HERMES_RUNTIME_DIR` first
(`website/docs/reference/package-management.md#developer-workflow`). Tests need the separate test
environment in `CONTRIBUTING.md`. **`python scripts/check`** runs every blocking lint check CI
runs, with CI's pinned tools; `--install-hook pre-push` runs it on every push (re-run after
pulling to refresh the hook). `# noqa` does not waive a ratchet finding:
`# health: allow <RULE> -- <why>` does.

## Project Structure

Counts shift constantly; the filesystem is canonical. Load-bearing entry points:

```
hermes-agent/
├── run_agent.py          # AIAgent facade; the turn loop lives in agent/turn_*.py
├── model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # TOOLSETS dict, _HERMES_CORE_TOOLS
├── cli.py                # HermesCLI (REPL, slash dispatch) + hermes_cli/cli_*_mixin.py
├── hermes_state.py       # SessionDB facade; hermes_state_*.py siblings
├── hermes_constants.py   # get_hermes_home(), display_hermes_home() — profile-aware paths
├── agent/                # turn loop phases, providers, memory, compression, prompt builder
├── hermes_cli/           # CLI subcommands, setup, config, plugins loader, updater, web_routers/
├── tools/                # Tool implementations (tools/registry.py) + environments/ backends
├── gateway/              # run.py facade + run_*.py phases + session*.py + platforms/
├── plugins/              # memory/, context_engine/, model-providers/, kanban/, image_gen/, ...
├── skills/               # Built-in skills (by category)   optional-skills/: shipped, not active
├── ui-tui/, tui_gateway/ # Ink terminal UI + its Python JSON-RPC backend (also serves Desktop)
├── apps/desktop/         # Electron desktop app (+ apps/shared)   web/: dashboard SPA
├── cron/                 # jobs.py + scheduler.py (+ scheduler_*.py)
├── pm/, hermes_platform/ # dependency/environment manager; machine facts + executable lookup
├── scripts/              # check, run_tests.sh, code_health/, ci/
├── website/              # Docusaurus docs (developer-guide/ holds the long-form area docs)
└── tests/                # Pytest suite, mirrors the source tree
```

**User state:** `~/.hermes/config.yaml` (settings), `.env` (secrets only), `logs/` (`hermes logs`);
all profile-aware via `get_hermes_home()`.

### Facade + siblings layout

Every former god file is a **facade** (public entry points + the names other packages import) plus
**siblings** `<stem>_<topic>.py`, each owning one topic (`hermes_state.py`, `gateway/run.py`,
`tools/mcp_tool.py`, `hermes_cli/kanban.py`, `hermes_cli/web_server.py`, `cli.py` →
`hermes_cli/cli_*_mixin.py`, `run_agent.py` → `agent/turn_*.py`).

- **Find code by topic:** `grep -rn "def name" <dir>/<stem>_*.py`, not by reading the facade.
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

| Area | Read | Covers |
|---|---|---|
| `run_agent.py`, `agent/` | `agent/AGENTS.md` | turn phases, caching and message-flow invariants, compression, model/aux resolution |
| `cli.py`, `hermes_cli/` | `hermes_cli/AGENTS.md` | CLI mixins, slash registry, config system, skins, `hermes update`, profiles / multiplex |
| `gateway/` | `gateway/AGENTS.md` | adapters, message guards, streaming, notifications, token locks, § Profile scope |
| `gateway/platforms/` new adapter | `gateway/platforms/ADDING_A_PLATFORM.md` | step-by-step adapter guide |
| `tools/`, `toolsets.py`, `model_tools.py` | `tools/AGENTS.md` | adding tools, registry, toolsets, delegation, session-scoped surface tools |
| `plugins/`, `hermes_cli/plugins*.py` | `plugins/AGENTS.md` | plugin kinds, native compat contract, in-tree policy |
| `plugin-catalog/` | `plugin-catalog/README.md` | catalog admission rules (mirrored in the developer guide; keep identical) |
| `tui_gateway/`, `ui-tui/` | `tui_gateway/AGENTS.md` | process model, JSON-RPC transport, slash flow |
| `web/`, `hermes_cli/web_routers/` | `web/AGENTS.md` | dashboard embeds the real TUI |
| `apps/desktop/` | `apps/desktop/AGENTS.md`, `apps/desktop/src/AGENTS.md` | `serve` backend, slash palette, Bot Mode |
| `skills/`, `optional-skills/`, `agent/curator*.py` | `skills/AGENTS.md` | frontmatter, authoring standards, curator |
| `cron/`, kanban | `cron/AGENTS.md` | scheduler invariants, job fields, kanban dispatcher |
| `tests/` | `tests/AGENTS.md` | runner, placement, OS markers, `wine2e`, banned test shapes |
| `pm/`, `pyproject.toml` | `pm/AGENTS.md` | pinning policy, PM-owned environments, plugin quarantine |
| `hermes_platform/` | `hermes_platform/AGENTS.md` | host facts, resolvers |

Long-form background: `website/docs/developer-guide/`. Workflow rules (PR/issue/review/salvage
process) live in the `hermes-agent-dev` skill, not here.
