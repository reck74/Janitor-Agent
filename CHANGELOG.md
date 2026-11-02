# Janitor Fork Changelog

Notable changes specific to the Janitor fork of hermes-agent. Upstream
changes are documented in the upstream release notes.

## `0.22.5+janitor.1` (Hermes v0.22.5) — unreleased

Upstream sync from Hermes v2026.9.24 to v0.22.5. Upstream moved stable
releases from calver tags to `v0.x.y`, and replaced its in-process updater
with a package manager (pm) that owns the Python runtime, the dependencies
and Node. No `~/.janitor` layout change, so no new migration runs on first
start.

### Upgrade notes
- **The first `janitor update` from 0.21.x is finished by Hermes' new
  updater.** The 0.21.x update code is what pulls this release, and it hands
  the checkout over to pm ("Handing off to the new updater"). pm installs the
  locked Python 3.14, the dependencies and Node into `~/.janitor/tools` and
  `~/.janitor/installs`, rebuilds the TUI and web UI, and stamps the checkout
  (`install-stamp.json`, `updateMechanism: "self"`). After that, `janitor`
  runs on that runtime and `janitor update` keeps it in sync. Checked end to
  end from 0.21.5 with the real update in a sandbox home.
- That handoff also runs the end of `hermes update` once: it installs Hermes'
  default tools (`agent-browser` with Chromium, `cua-driver`) into
  `~/.janitor/tools`, and publishes `hermes`, `hermes-acp` and
  `hermes-agent` in `~/.local/bin`, pointing at the Janitor checkout. Those
  commands use `~/.hermes`, not `~/.janitor`. A command that belongs to
  another install is left alone. Janitor's own update and `bootstrap.sh` do
  neither.
- **Honcho left Hermes core.** It is now a catalog plugin, which the update
  installs for every home with `memory.provider: honcho` (the Janitor
  default). The catalog's current Honcho pin does not install (upstream
  [#146435](https://github.com/NousResearch/hermes-agent/issues/146435), fix
  in review in [#147311](https://github.com/NousResearch/hermes-agent/pull/147311)):
  the update reports "Memory provider 'honcho' … could not be installed
  automatically" and Honcho memory stays off until it installs. This
  release should not ship before upstream fixes that.

### Changed
- `janitor update` runs every step after the pull in a fresh interpreter of
  the pulled code (`python -m janitor.update_child`): dependency install,
  Node dependencies plus the TUI and web UI build (`hermes_cli.source_build`,
  as `hermes update` does), and the config check and migration. A pm-managed
  checkout syncs its pm environment; a classic `.venv` checkout still
  installs `-e .[all]`, with uv provided by pm or with pip.
- The `janitor` launcher imports `hermes_bootstrap` first, like every Hermes
  entry point, so a pm-managed checkout starts on its pm runtime.
- `scripts/bootstrap.sh` builds the TUI and web UI with
  `hermes_cli.source_build`; pm provides Node and npm in `~/.janitor/tools`.
- Upstream's `pyproject.toml` says `0.0.0` and reads the version from the
  install stamp or git tags. Janitor still declares `0.22.5+janitor.1`, and
  `hermes_cli/version_info.py` (touchpoint `version`) reports it for a
  checkout.
- The Janitor layer reads YAML through `hermes_yaml` (ruamel.yaml), since
  upstream dropped PyYAML.
- Tips: only `hermes_cli.tips.get_random_tip` is patched. Upstream removed
  `TIPS`; its tips are now i18n catalog keys.
- The desktop overlay merges Janitor's builder config on top of upstream's
  `electron-builder.config.cjs` and brands the `nous-girl` hero images.
- `scripts/migrate-janitor-v0.20.1.sh` calls `hermes_cli.config` directly.
- CI: the test jobs install through upstream's `setup-pm` action (locked
  Python, isolated test environment); `dev` is a dependency group; Janitor
  tests use `@pytest.mark.platforms(...)`.
- `janitor/overlay.yaml` tracks upstream v0.22.5. The weekly sync selects
  `v0.x.y` release tags.

### Fixed
- `janitor update` failed at "Restoring local changes" with `package-lock.json`
  would be overwritten. The update now discards npm lockfile and CRLF-only
  churn before stashing, like `hermes update`, and the frontends are built by
  `hermes_cli.source_build`, which never writes the lockfile.

### Removed
- The `web-typecheck` touchpoint: upstream already runs `tsc -b . --noEmit`.

## `0.21.5+janitor.1` (Hermes v2026.9.24)

Upstream sync from Hermes v2026.8.13 to v2026.9.24. No `~/.janitor` layout
change, so no new migration runs on first start.

### Changed
- **Touchpoints moved by upstream refactors:** the compact banner is now
  rebranded in `hermes_cli/cli_render.py` (upstream split `cli.py`), and the
  MCP `discover` endpoint uses upstream's profile/secret scoping
  (`_secret_scoped`) and redacts probe errors.
- **`janitor update`** honours the cross-process update lock shared with
  `hermes update`, the dashboard and the desktop updaters. It exits with code 2
  while another update is running; `janitor update --check` is unaffected.
- **Skill copy detection** in the v1 migration ignores `__pycache__` and other
  runtime caches, matching upstream's bundled-skill hash, so a copy whose only
  difference is bytecode is no longer reported as user-edited.
- `scripts/migrate-janitor-v0.20.1.sh` writes its `config.yaml` backup to
  `~/.janitor/backups/config/`, where upstream's backup sweep keeps them.
- `janitor/overlay.yaml` tracks upstream v2026.9.24.

### Fixed
- `janitor update` ignored its flags: the early intercept passed a hardcoded
  namespace, so `janitor update --check` ran a full update (including the
  switch to `main`). Flags are now parsed strictly (`--check`, `--gateway`,
  `--backup`, `--no-backup`, `--branch`), unknown ones are an error, and
  upstream's read-only `--plan` / `--list-venv-holders` are refused instead
  of running an update.
- `janitor update` looked `uv` up on `PATH` only. It now uses Hermes' managed
  `uv` in `~/.janitor/bin` (installing it if missing), like `hermes update`,
  and falls back to pip as before.
- The v1 migration read `config.yaml` with a raw YAML load. It now uses
  Hermes' fail-closed reader: an unreadable or malformed `config.yaml` stops
  the migration, which is retried on the next start, and the file is never
  rewritten. Before, a file whose top level was not a mapping was skipped
  and the home was marked as migrated anyway.
- CI: `janitor-ci.yml` no longer requests the `hindsight` extra that upstream
  removed, and the `e2e` and `upstream-sync-verify` jobs in `tests.yml`
  install what upstream's own jobs install. `upstream-sync-verify` skips
  `tests/ci/` and four upstream plugin-discovery tests that count the
  `janitor` entry-point plugin; upstream runs them in its own CI.

### Removed
- The `gateway-cache-refresh` touchpoint. The gateway holds an
  `AsyncSessionDB`, so upstream's direct `await` was already correct and the
  Janitor `asyncio.to_thread` wrapper broke the cached message count. A
  regression test with a real `SessionDB` covers the behavior.
- Upstream CI workflows the fork does not run. Only `tests.yml`,
  `janitor-ci.yml`, `upstream-sync.yml` and `janitor-desktop-release.yml`
  remain.

## 1.0.0 — `0.20.1+janitor.2` (Hermes v2026.8.13)

Janitor vNext: a thin fork of Hermes plus a Janitor layer. Existing installs
are migrated automatically on the first `janitor` start, with a backup first.

### Changed
- **Layout:** everything Janitor-specific moved into fork-only directories:
  `janitor/` (launcher, update flow, migrations, plugin, services),
  `janitor/skills/{core,services,agents,integrations}/`, `assets/janitor/`,
  `apps/desktop-janitor/` and `tests/janitor/`. The root `janitor_*.py` modules
  remain as compatibility aliases for pre-1.0 console scripts.
- **Skills** are read in place through `skills.external_dirs` instead of being
  copied into `~/.janitor/skills`.
- **Telegram** `/start` and avatar, plus the language prompt section, moved from
  core edits into the Janitor plugin (`plugins.enabled: [janitor]`).
- **TUI look** now comes entirely from the `sentry-janitor` skin. Upstream
  palettes are restored, and the only TUI hook left is the
  `branding.tagline`/`vendor` skin keys.
- **Desktop** is built from upstream with the `apps/desktop-janitor/` overlay
  (appId, name, icons). Upstream `apps/desktop/` assets are untouched, and the
  packaged `productName` stays `Hermes` so existing desktop data keeps its
  location.
- **CI** runs the `tests/janitor/` directory plus `python -m janitor.overlay check`
  through `scripts/janitor-sync-verify.sh`, replacing a test list kept in six
  places. `upstream-sync.yml` merges the newest upstream release tag and runs
  the same gate.
- **Installer:** re-running it over an existing home keeps `config.yaml`,
  `SOUL.md`, `honcho.json` and the skin, and backs up `.env` before rewriting it.

### Added
- `janitor services list|status|deploy|start|stop|uninstall` for the
  self-hosted services, driven by each skill's `service.yaml`. It never removes
  Docker volumes.
- `janitor agents list|show` for the specialized-agent catalog.
- `janitor/migrations` + `scripts/migrate-janitor-v1.sh [--dry-run]`: backup
  (including a SQLite-consistent `state.db`), enable the plugin and external
  skill dirs, remove only unedited Janitor skill copies, and report edited ones.
- `janitor/overlay.yaml`: inventory of every divergence from upstream, checked
  against the upstream base.
- Desktop release workflow publishing `Janitor-<version>-linux-x86_64.AppImage`.
- **MCP dashboard endpoints:** `POST /api/mcp/servers/{name}/discover` (returns
  full tool descriptors with `inputSchema`) and `GET /api/mcp/servers/{name}/logs`
  (returns per-server tail of `mcp-stderr.log`). The workspace UI image
  expects both; previously the fork returned 404 and the workspace fell back
  to `config.yaml`. The auth gap between workspace and dashboard (workspace
  sends `HERMES_API_TOKEN` as bearer; dashboard requires `_SESSION_TOKEN`) is
  tracked separately — these endpoints are reachable today via browser cookie
  or `X-Hermes-Session-Token` header. See
  `docs/superpowers/specs/2026-08-09-mcp-discover-logs-endpoints-design.md`.

### Removed
- Merge residue in the core: duplicate definitions and files upstream had
  deleted or moved (old gateway platforms, Electron `.cjs`, stale desktop
  sources), plus unwired fork modules.
- The `load_soul_md` monkey-patch, since upstream already reads
  `HERMES_HOME/SOUL.md`.
