# Janitor Fork Changelog

Notable changes specific to the Janitor fork of hermes-agent. Upstream
changes are documented in the upstream release notes.

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
