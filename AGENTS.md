# JANITOR FORK DIRECTIVES (SUPREME RULES)

1. **ZERO-RENAMING POLICY**: Nunca hagas buscar-y-reemplazar de la palabra 'hermes' en el core. El motor subyacente se mantiene intacto para garantizar que el merge de cada release upstream funcione sin conflictos destructivos.
2. **CLI WRAPPER**: Las extensiones de Janitor heredan de `HermesCLI` en el paquete `janitor/` (lanzador: `janitor/cli.py`). No se modifica `cli.py` original. Los módulos raíz `janitor_cli.py`, `janitor_update_core.py`, `janitor_update_bootstrap.py`, `janitor_version.py` y `janitor_ext/` son alias de compatibilidad para instalaciones pre-1.0 (su console script apunta a `janitor_cli:main`); no se les añade lógica.
3. **SKILLS AISLADOS**: Toda skill Janitor vive en `janitor/skills/<grupo>/janitor-*/`, con grupos `core`, `services` (con Docker), `agents` e `integrations`. Se cargan in place vía `skills.external_dirs` (`${JANITOR_SKILLS_ROOT}`, exportado por el lanzador) y nunca se copian a `~/.janitor/skills`. Los árboles `skills/` y `optional-skills/` son de upstream y no se tocan. Las skills de `services/` declaran un `service.yaml` (contenedores `janitor-*`, script de deploy) que consume `janitor services list|status|deploy|start|stop|uninstall`.
4. **TUI ISOLATION**: Los cambios visuales del TUI se inyectan vía el sistema de skins (`skin_engine.py`, skin `assets/janitor/sentry-janitor.yaml`) sin destruir la compatibilidad del protocolo JSON-RPC. No se hace hardcode en los componentes base del TUI; el único hook es el touchpoint `tui-branding-hook` (`branding.tagline` / `branding.vendor`). El desktop se personaliza en el overlay de build `apps/desktop-janitor/`, nunca reemplazando assets en `apps/desktop/`.
5. **NAMING CONVENTION (BRANDING)**: Todo contenedor Docker, red, volumen, servicio de sistema o aplicación de terceros que Janitor instale o configure en el futuro DEBE llevar obligatoriamente el prefijo `janitor-` (ej. `janitor-redis`, `janitor-network`). Sin excepciones.
6. **merge-auditor**: Cada merge debe ser auditado contra estas directivas. Si un PR introduce 'hermes' renombrado en archivos core, se rechaza automáticamente. El gate mecánico es `scripts/janitor-sync-verify.sh` (ver `MERGE_GUIDE.md`).
7. **tui-compilation**: Los cambios en el TUI requieren pasar `npm run build` Y `npm test` (vitest) ANTES de hacer commit. El pipeline CI de Janitor ejecuta esta habilidad como gate obligatorio.
8. **ESSENTIAL DEPENDENCIES**: Docker y Honcho son dependencias fundamentales del stack Janitor, no opcionales. El `bootstrap.sh` verifica la presencia de Docker y asiste en su instalacion (`get-docker.sh`) si falta. El `janitor-install.sh` despliega Honcho (modo Docker local) o solicita credenciales de Honcho cloud. `MINIMAX_API_KEY` es obligatoria porque es el proveedor de IA principal de Janitor (usada como `LLM_ANTHROPIC_API_KEY` por Honcho). Las capacidades restantes (Firecrawl, n8n, LightRAG, NocoDB, WAHA, Browser) son skills opcionales bajo `janitor/skills/` que se instalan explicitamente post-primer-arranque.
9. **OPTIONAL SKILLS ARE EXPLICIT**: Tras la instalacion base (que incluye Docker + Honcho), el usuario puede ejecutar `janitor` inmediatamente. Los servicios opcionales se despliegan explicitamente post-arranque con `janitor services deploy <nombre>`. Janitor no incluye Infisical ni AgentMemory en su stack — la gestion de secretos y memoria de codigo se maneja por otros mecanismos.
10. **MIGRATION SUPPORT**: Cada reestructuracion de `~/.janitor` incluye una migración en `janitor/migrations/` (sube `LAYOUT_VERSION` en `janitor/home.py`) y su script `scripts/migrate-*.sh` con `--dry-run`. El lanzador `janitor` la ejecuta automáticamente en el primer arranque (marcador `~/.janitor/.layout_version`), con backup previo en `~/.janitor/.backup/` (incluida una copia consistente de `state.db` vía la API de backup de SQLite). Una migración nunca toca contenedores ni volúmenes Docker, `.env`, líneas del RC de shell ni unidades systemd, y conserva todo archivo que el usuario haya editado. El instalador, re-ejecutado sobre un home existente, conserva `config.yaml`, `SOUL.md`, `honcho.json` y el skin, y respalda `.env` antes de reescribirlo.
11. **TEST PRUNING (TWO-TIER CI)**: Todo test Janitor vive en `tests/janitor/` — no hay listas que mantener sincronizadas. El gate de PR (`tests.yml :: test`) corre `scripts/janitor-sync-verify.sh --skip-tui --skip-desktop`: el overlay check (directiva #16) más `scripts/run_tests.sh tests/janitor/`. `janitor-ci.yml` corre el mismo directorio en `python-tests` (ubuntu) y en `os-compat` (macOS vía `scripts/run_tests.sh`, Windows vía `"$HERMES_PYTHON" -m pytest`; los tests `@pytest.mark.platforms("linux")` se saltan fuera de Linux). Los jobs de test instalan con la acción upstream `./.github/actions/setup-pm` (Python fijado en `pm/lock.json`, entorno de test aislado exportado como `HERMES_PYTHON`); solo `installer-e2e` usa el `.venv` clásico de `bootstrap.sh`, además de los gates del TUI (`react-tests`) y del overlay desktop (`desktop-overlay`). El suite completo de upstream (~50k tests, salvo `tests/ci/`, que asserta sobre los workflows podados, y los pocos tests deseleccionados en el propio job que chocan con el fork por diseño, como los de descubrimiento de plugins que ven el entry point `janitor`) se ejecuta en el job `upstream-sync-verify`, y su suite e2e (`tests/e2e/`) en el job `e2e`; ambos corren en `workflow_dispatch` (manual) o automaticamente en push a `main` cuyo commit message matche `chore(sync):`, `fix(sync):`, o merge de un branch `upstream-sync-*`. **Razon**: upstream ya valida su propio test suite antes de que cualquier commit llegue al fork. **NO** se borran los archivos de test upstream del arbol — permanecen disponibles para que `upstream-sync-verify` los corra. **NO** se deshabilita el `test` job para que ejecute la suite completa, eso revierte esta directiva.
12. **TEST ASSERTION BRANDING**: Toda aserción de test que compare contra el string del banner CLI (e.g. output de `--version`, el titulo del welcome banner) DEBE assertar sobre `THE JANITOR` / `THE JANITOR v`, NO sobre `Hermes Agent` / `Hermes Agent v`. El touchpoint `banner` re-aplica el string del banner Janitor en `hermes_cli/banner.py` (`format_banner_version_label`), `hermes_cli/_startup_fast.py` (fallback) y `hermes_cli/cli_render.py` (rama rápida de `_build_compact_banner`, que upstream sacó de `cli.py` en v2026.9.24), pero los tests upstream siguen hardcodeando el string upstream. Cuando un nuevo test upstream introduzca el literal `Hermes Agent`, actualizar la aserción a `THE JANITOR` en el mismo commit, añadir un comentario inline que apunte a esta directiva y declarar el archivo en el touchpoint `banner` de `janitor/overlay.yaml`.
13. **JANITOR UPDATE FLOW**: Both `janitor update` entry points — the early intercept in `janitor/cli.py` (`if sys.argv[1] == "update"`, via `janitor/update_bootstrap.py`) and the monkey-patched `cmd_update` (`janitor/cli.py:_janitor_cmd_update`) — delegate to a single shared core in `janitor/update_core.py:run_janitor_update(args)`. Any change to the update flow (pre-check, fetch, pull, fallback, post-pull validation, dependency install, stash handling, error recovery) lives in `janitor/update_core.py`. The entry-point shells may ONLY print their branding banner and call the core. Rationale: the previous two-path design led to silent divergence — one path had a `git pull --ff-only` failure with no recovery because it lacked the `git reset --hard origin/main` fallback. Helpers from `hermes_cli.main` are imported lazily inside the core so the early intercept still works on a partially-broken venv. Everything after the pull (dependency install, Node deps + TUI/web build via `hermes_cli.source_build`, config check/migration) runs in a fresh interpreter of the pulled code through `python -m janitor.update_child <step>`, never by re-importing modules in the running process; a checkout stamped `updateMechanism: "self"` (upstream's PM takeover) syncs its PM generation instead of `pip install -e`. The core claims upstream's shared update marker (`hermes_cli/update_lock.py`, also used by `hermes update`, the dashboard and the desktop/Tauri updaters) and refuses with exit code 2 while another live update holds it; `--check` stays lock-free, and an unimportable lock module degrades to an unlocked update. The `~/.janitor` layout migration is NOT part of the update flow: the code that pulls a release is the previous release's, so the new launcher migrates on first start (directive #10).
14. **MONKEY-PATCH SIGNATURE INVARIANTS**: `janitor/cli.py` monkey-patches upstream callables at import / launch time (currently: `argparse.ArgumentParser.__init__`, `hermes_cli.main.cmd_update`, and `hermes_cli.tips.get_random_tip`). Each wrapper's signature MUST stay compatible with the upstream function it replaces — it must accept every parameter the original accepts. When upstream adds a parameter to a patched function, the sync merge adopts the new callee signature AND the new caller, but never touches `janitor/` (fork-only), so the wrapper silently keeps the old signature and crashes at runtime with `TypeError: ... takes 0 positional arguments but 1 was given`. Upstream tests mock the patched functions and never import the launcher, so only our test catches it. **Enforcement**: `tests/janitor/test_janitor_monkeypatch_signatures.py`. When a sync breaks this test, update the wrapper signature in `janitor/cli.py` to match — do NOT weaken the test. Prefer a plugin hook or skin key over a new monkey-patch.
15. **POST-SYNC DUPLICATE DEFINITION AUDIT**: When both the Janitor fork and upstream add a method or function with the same name to the same scope, a sync merge can leave both non-conflicting additions in place. Python's "last definition wins" rule then silently shadows the first, which can change a method from `async` to `sync` while callers still `await` it — producing `TypeError: object NoneType can't be used in 'await' expression` at runtime. **Real-world impact**: the v2026.7.7.2 sync (merge `83d4f8d62`) left duplicate `_refresh_agent_cache_message_count` definitions in `gateway/run.py` and every Telegram message crashed AFTER generating the correct response; the v2026.8.13 audit found more in `cron/`, `tools/`, `agent/`, `hermes_cli/` and `tui_gateway/`. Since v2026.9.24 upstream splits `GatewayRunner` into mixins, so the method now lives in `gateway/run_agent_cache.py` (callers in `gateway/run_turn.py`) and the Janitor cache-refresh touchpoint is retired — the gateway holds an `AsyncSessionDB`, so upstream's direct `await` is correct. **Enforcement**: `tests/janitor/test_janitor_no_duplicate_methods.py` scans the top-level core modules and every core package (`agent/`, `tools/`, `cron/`, `hermes_cli/`, `gateway/`, `tui_gateway/`, `plugins/`) for duplicate class methods (excluding `@property`/`@.setter` pairs) and duplicate module-level functions, and locks `_refresh_agent_cache_message_count` as a single `async` definition across the whole `gateway/` package, resolved as a coroutine on `GatewayRunner` and always awaited by its callers. Upstream's intentional PLUGIN-COMPAT chained module `__getattr__` pairs are listed in `_UPSTREAM_KNOWN_DUPLICATES`. When a sync breaks this test, keep the correct definition (usually the one with the more complete logic) and delete the other — do NOT weaken the test.
16. **OVERLAY INVENTORY**: `janitor/overlay.yaml` declares every divergence from upstream: `fork_paths` (zonas exclusivas del fork: `janitor/`, `assets/janitor/`, `apps/desktop-janitor/`, `tests/janitor/`, `docs/janitor/`, scripts y workflows Janitor) and `touchpoints` (each in-place edit of an upstream file, with `why`, `verify` and `merge: ours|reapply`). `python -m janitor.overlay check` fails on any undeclared difference against `upstream.base`, so merge residue cannot survive silently. Editing an upstream file requires declaring it as a touchpoint in the same PR, with a behavioral check in `tests/janitor/test_janitor_overlay_contract.py` when `verify: test:<id>`. Generic hooks worth upstreaming are marked `upstream_candidate: true` (see `docs/janitor/upstream-candidates.md`).

---

## Janitor Architecture (1.0 — thin fork + Janitor layer)

### Philosophy

Janitor is a thin fork: the Hermes core stays as close to upstream as the
touchpoints in `janitor/overlay.yaml` allow, and everything Janitor-specific
lives in fork-only directories. The first-run installer creates a functional
agent with identity, configuration, skin, and optional Honcho memory.
Everything else is delivered as opt-in skills and services.

### Layout

| Path | Role |
|------|------|
| `janitor/cli.py` | `janitor` launcher: `HERMES_HOME=~/.janitor`, skin, layout migration, update intercept |
| `janitor/update_core.py`, `janitor/update_bootstrap.py`, `janitor/update_child.py` | Update flow (directive #13); `update_child` runs the post-pull steps in a fresh interpreter |
| `janitor/migrations/` | `~/.janitor` layout migrations (directive #10) |
| `janitor/plugin/` | Hermes plugin (`plugins.enabled: [janitor]`): Telegram `/start` + avatar, language prompt section, `janitor services` and `janitor agents` CLI commands |
| `janitor/services.py`, `janitor/agents.py` | Service lifecycle (`service.yaml`) and specialized-agent catalog |
| `janitor/skills/` | All Janitor skills (directive #3) |
| `janitor/overlay.py`, `janitor/overlay.yaml` | Overlay inventory and check (directive #16) |
| `assets/janitor/` | Seed `config.yaml`, `SOUL.md`, `honcho.json`, `sentry-janitor.yaml` skin, Telegram assets |
| `apps/desktop-janitor/` | Desktop build overlay (`scripts/build.mjs`, `electron-builder.janitor.json`) |
| `tests/janitor/` | The Janitor test suite (directive #11) |

### Installer Contract

`scripts/janitor-install.sh` deploys **only**:
- `~/.janitor/.env` — environment variables (backed up to `~/.janitor/.backup/install-*/` before a rewrite)
- `~/.janitor/config.yaml` — agent configuration (kept if it already exists)
- `~/.janitor/SOUL.md` — agent persona (kept if it already exists)
- `~/.janitor/skins/sentry-janitor.yaml` — visual theme (kept if it already exists)
- Optional: local Honcho (via `scripts/setup-honcho.sh`)

**Does NOT deploy by default**: Firecrawl, Browser, or any other service.

### Skill Hierarchy

| Group | Skills |
|-------|--------|
| `core/` | `janitor-core` (cache/environment hygiene), `janitor-config-audit` (config/SOUL.md drift), `janitor-onboarding` (orientation guide) |
| `services/` | `janitor-honcho`, `janitor-firecrawl`, `janitor-n8n`, `janitor-lightrag`, `janitor-nocodb`, `janitor-waha` — each with `service.yaml` + `scripts/deploy.sh` |
| `agents/` | `janitor-code-review-agent`, `janitor-repo-research-agent` — each with `agent.yaml` |
| `integrations/` | `janitor-browser`, `janitor-desktop-launcher`, `janitor-opendesign`, `janitor-skill-integration` |

Each skill contains `SKILL.md`, optional `scripts/`, and compose files scoped to
that service only. SKILL.md prose references its own files as
`${HERMES_SKILL_DIR}/...` so it works from any install tree.

### Adding a New Janitor Skill

1. Create `janitor/skills/<group>/janitor-<name>/` with a `SKILL.md` (name, description ≤ 60 chars, version, platforms, metadata).
2. Add scripts under `scripts/`. A Docker service also gets a `service.yaml` (`name`, `description`, `deploy`, `compose`, `url`, `containers` — all `janitor-*`).
3. Reference the skill from `janitor/skills/core/janitor-onboarding/SKILL.md` so users can discover it.
4. Add its tests under `tests/janitor/`.
5. Do NOT modify core Hermes files or built-in skills.

### User Workflow

```bash
# Fresh install — minimal
curl -fsSL .../bootstrap.sh | bash
janitor

# Post-install: add capabilities as needed
janitor services list
janitor services deploy firecrawl
```

### Upgrading Existing Installs

`janitor update` pulls the new release; the next `janitor` start migrates
`~/.janitor` to the current layout (backup first). Manual / preview:

```bash
bash scripts/migrate-janitor-v1.sh --dry-run
```

Users of the pre-v5 full stack run `bash scripts/migrate-janitor-minimal.sh`
first (Infisical RC snippets, secret export; Docker volumes are never deleted).

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
