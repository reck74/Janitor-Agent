# Janitor Fork Changelog

Cambios propios del fork Janitor de hermes-agent. Los de upstream están en sus
notas de release. Una versión solo llega a los usuarios cuando se etiqueta
(`v…`) y el workflow de release mueve la rama `stable` (directiva #13); una
fusión a `main` no se entrega. Las entradas anteriores a la app de escritorio
se conservan tal como se escribieron, en inglés, y describen código que ya se
retiró.

## `0.21.5+janitor.3` — etiqueta `v0.21.5-janitor.3` (2026-11-27)

### Añadido
- **Obreros** (`janitor obreros`, skill `janitor-obreros`): un perfil puede
  encargar trabajo en segundo plano a Claude Code o Codex ya instalados y con
  sesión del usuario, en carpetas que el usuario autoriza. Desactivado hasta
  que se activa (`janitor obreros activar`). Plan:
  `docs/janitor/plans/obreros-claude-codex.md`.

### Corregido
- El Creador de proyectos ya no recibe las skills `claude-code`, `codex` ni
  `opencode` de upstream (enseñaban a lanzar esos programas a mano, sin los
  topes ni las carpetas de los obreros); la paleta y la pantalla de skills ya
  no muestran skills retiradas.

## `0.21.5+janitor.2` — etiqueta `v0.21.5-janitor.2` (2026-11-25)

Primera versión publicada para Windows, macOS y Arch Linux.

### Añadido
- App para **Windows x64** (`Janitor-win-x64.exe`, NSIS, sin firmar) y
  **macOS** (`Janitor-mac-arm64.dmg`, `Janitor-mac-x64.dmg`, firma ad hoc, sin
  notarizar). El motor se instala en Windows con `scripts/install.ps1` en
  `%USERPROFILE%\.janitor`, y el comando `janitor` en `%USERPROFILE%\.janitor\bin`.
- Paquete de **Arch Linux** `janitor-desktop-bin` (y sus fuentes para
  `makepkg`), reempaquetado desde el AppImage; se abre con `janitor-desktop`.
- `SHA256SUMS` en cada versión y prueba de arranque de la app empaquetada en
  CI para cada sistema. Guía: `docs/janitor/instalar-app.md`.
- La app muestra la versión de Janitor, no la de upstream.

### Cambiado
- Modelo por defecto `MiniMax-M3`.
- Los aplicativos con Docker no están disponibles en Windows: `janitor
  services` lo dice en lugar de fallar.

### Corregido
- Un saludo ya no dispara herramientas: sin orden no hay trabajo.

### Sin verificar
- Nada se ha probado aún en un Windows o un Mac reales (SmartScreen,
  Gatekeeper, chatear). La actualización real de `.1` a `.2` se hizo por
  terminal (`janitor update`), no desde la app.

## `0.21.5+janitor.1` — etiqueta `v0.21.5-janitor.1` (2026-11-25)

Primera versión de Janitor como **app de escritorio** (AppImage de Linux) y
**punto cero**: las instalaciones antiguas por terminal no se adoptan ni se
migran. Incluye el sync a Hermes v2026.9.24 descrito en la entrada en inglés de
abajo. La versión se publicó con `Janitor-linux-x86_64.AppImage`; su página de
GitHub ya no existe (la etiqueta sí).

### Añadido
- La app de escritorio instala el motor por etapas con `scripts/install.sh` en
  `~/.janitor/hermes-agent` y deja `janitor` en `~/.local/bin`. Primer arranque
  con MiniMax recomendado, todo en español y con la marca Janitor aplicada al
  compilar (`apps/desktop-janitor/`, directiva #17).
- Canal de publicación por etiquetas: la rama `stable`
  (`janitor/release_channel.py`); `janitor update`, `/update` de mensajería, el
  aviso del banner y la app la siguen.
- `janitor update` en español, con comprobación de dependencias, reinicio de
  gateways y bloqueo compartido con los demás actualizadores; la app actualiza
  por el mismo flujo y comprueba la compatibilidad app–motor.
- Catálogo de skills por propósito (`janitor/catalog.yaml`); agente principal y
  especialistas por plantilla (`janitor plantillas`, pantalla **Agentes**).
- Skills del sistema (`janitor-system-health`, `janitor-maintenance`,
  `janitor-cleanup`, `janitor-file-organizer`) y de proyectos
  (`janitor-project-create`).
- Instalación guiada por conversación de Honcho, n8n, NocoDB, LightRAG,
  Firecrawl y Open Design; WAHA como auditoría de solo lectura del WhatsApp
  personal; pantallas **Servicios** y **Skills** en la app.
- Textos del motor en español por catálogo (`janitor/locales/es.yaml`).

### Cambiado
- La identidad cubre toda la tecnología, no solo código.
- La base ya no instala el navegador: se descarga la primera vez que el agente
  navega. La app oculta el Skills Hub y el catálogo de plugins de Hermes.

### Retirado
- Los instaladores y migradores por terminal (`scripts/bootstrap.sh`,
  `scripts/janitor-install.sh`, `scripts/setup-honcho.sh`,
  `scripts/migrate-janitor-*.sh`), los alias pre-1.0 (`janitor_cli.py`,
  `janitor_update_*.py`, `janitor_ext/`; queda `janitor_version.py`), el
  sistema paralelo de agentes (`janitor agents`, `janitor/opencode/`) y las
  migraciones v1 y v2 (un home nuevo nace en el layout v2). `scripts/install.sh` se niega a instalar sobre
  `~/.janitor/janitor-core`: ver `docs/janitor/desinstalar-instalacion-antigua.md`.

### Corregido
- `janitor update` fallaba en «Restoring local changes» porque
  `package-lock.json` iba a sobrescribirse: el paso del TUI hacía un
  `npm install` que reescribía el lockfile en cada actualización, y la
  siguiente lo guardaba en el stash y no podía restaurarlo. Ahora descarta los
  cambios del lockfile de npm y los de solo CRLF antes del stash, como
  `hermes update`, y el paso del TUI solo repara un `node_modules` desfasado con
  la instalación determinista de Hermes, que nunca escribe el lockfile.

## Sync a Hermes v2026.9.24 (incluido en `0.21.5+janitor.1`)

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
  or `X-Hermes-Session-Token` header.

### Removed
- Merge residue in the core: duplicate definitions and files upstream had
  deleted or moved (old gateway platforms, Electron `.cjs`, stale desktop
  sources), plus unwired fork modules.
- The `load_soul_md` monkey-patch, since upstream already reads
  `HERMES_HOME/SOUL.md`.
