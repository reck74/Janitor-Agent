---
name: janitor-opendesign
description: "Register Janitor as Open Design's native coding agent."
version: 1.0.0
author: janitor
license: MIT
platforms: [linux, macos, wsl2]

metadata:
  hermes:
    tags: [opendesign, design-tools, coding-agent, janitor, integration]
    category: devops
    related_skills: [janitor-onboarding, janitor-config-audit]
---

# janitor-opendesign

Register Janitor in an explicitly installed Open Design source checkout. The
registration command applies four idempotent source patches; it does not clone
Open Design or install its dependencies. This capability is optional and does
not run during Janitor's base installation.

## Supported source and toolchain

The recovery validation uses Open Design **0.25.0**, tag
`open-design-v0.25.0`, commit `de6d2c072a18dfef80ecad4a455b31f0d5aca090` from
[the official repository](https://github.com/nexu-io/open-design/releases/tag/open-design-v0.25.0).
Use **Node 24** (`24.21.0` validated) and **pnpm 10.33.2**. Janitor's own Node 26
requirement does not apply to this separate checkout. The scripts validate the
Node executable that their child commands will actually use.

An existing Open Design installation can contain local agent definitions,
custom icons and data. Do not replace it or pull a newer release automatically.
Review its local changes and back up its configuration and data before a
separate migration. The 0.25.0 check below uses a fresh checkout; it does not
certify migration of databases from older releases.

## Fresh installation and registration

Set `JANITOR_SKILLS_DIR` to the installed skills directory or this repository's
`skills` directory. `janitor` must already be on PATH.

```bash
export JANITOR_SKILLS_DIR="${JANITOR_SKILLS_DIR:-$HOME/.janitor/skills}"
export OD_SOURCE_DIR="$HOME/open-design"
export OD_INSTALL_DIR="$OD_SOURCE_DIR"

# For a NEW checkout only; an existing directory must be reviewed separately.
git clone --depth 1 --branch open-design-v0.25.0 \
  https://github.com/nexu-io/open-design.git "$OD_SOURCE_DIR"
test "$(git -C "$OD_SOURCE_DIR" rev-parse HEAD)" = \
  de6d2c072a18dfef80ecad4a455b31f0d5aca090

# Activate the checkout's Node 24 toolchain; do not change global Janitor Node.
cd "$OD_SOURCE_DIR"
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/integrate-janitor.sh" register
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/safe-pnpm-install.sh" install --frozen-lockfile

# Daemon + browser UI; this headless mode does not launch Electron.
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/start.sh" web
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/status.sh"
```

Without mise, put the installed Node 24 and pnpm 10.33.2 executables on PATH
before running these commands. `safe-pnpm-install.sh` uses a
`janitor-opendesign-pnpm-*` systemd user scope when systemd-run is available,
with CPU and memory limits. It propagates installation and user-bus failures;
a missing user session is an installation failure, not a successful setup.

For the upstream Electron application, run `start.sh` without `web` from a
graphical session. The recovery checks cover daemon/web startup, not Open
Design's Electron UI. Start accepts upstream tools-dev arguments, for example
`web --no-env-file` for an isolated check that must not load local env files.

## Paths and persistent ports

`OD_SOURCE_DIR` and the compatibility alias `OD_INSTALL_DIR` identify the same
checkout. The orchestrator rejects conflicting values. Neither variable may
point at an unrelated installation during a test or repair.

| Service | Default URL |
|---------|-------------|
| Daemon health | `http://127.0.0.1:45351/api/health` |
| Browser UI | `http://127.0.0.1:45343` |
| MCP configuration | `http://127.0.0.1:45351/api/mcp/install-info` |

Set `OD_DAEMON_PORT` and `OD_WEB_PORT` before start and status if these ports
are occupied. The
services bind to loopback; remote access requires an authenticated tunnel or
proxy. `status.sh` succeeds only when both HTTP endpoints return 200, and its
requests have bounded connect and total timeouts.

Open Design 0.25.0 uses **stdio MCP**, not an HTTP `/mcp` route. Read
`/api/mcp/install-info` or Settings → MCP to obtain the official `command`,
`args` and `env` for the running daemon. Preserve all returned environment
fields: they identify its data directory and sidecar connection. The command
runs the pinned Node executable with `apps/daemon/dist/cli.js mcp`. Do not
replace this with a guessed HTTP endpoint or omit its sidecar environment.

```bash
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/stop.sh"
```

The scripts use tools-dev's default namespace within the selected source
checkout. Avoid sharing that checkout with another running test namespace.

## Registration and updates

Registration changes only these Open Design paths:

- `apps/daemon/src/runtimes/defs/janitor.ts`: Janitor ACP agent definition.
- `apps/daemon/src/runtimes/registry.ts`: import and registration beside Hermes.
- `apps/web/public/agent-icons/janitor.png`: bundled Janitor icon.
- `apps/web/src/components/AgentIcon.tsx`: PNG icon mapping.

Re-running registration leaves those generated outputs identical. The bundled
icon lives under this skill's `icon/`; the repository-root PNG is a compatibility
fallback. Review any customized `janitor.ts` before registration because the
script replaces that generated definition. After changing source registration,
rebuild dependencies with the guarded installer and restart the selected stack.
A successful source patch does not by itself prove compatibility with an
untested future Open Design version.

Open Design 0.25.0 names its built-in array `SHIPPED_AGENT_DEFS`; older versions
used `BASE_AGENT_DEFS`. The existing Hermes entry is the insertion anchor, so
both layouts can be patched without renaming upstream internals.

## Validation and recovery

- Confirm registration twice produces identical outputs, then build the patched
  daemon and web. A green registration message alone is insufficient.
- Check `/api/health`, the browser root and the agent inventory. MCP discovery
  can be checked without generating a design or supplying model credentials.
- If the Node gate fails, activate the required Node in the current shell or
  use `mise exec -- bash ...`. Do not create a conflicting `.mise.toml` or
  change the global Node used by Janitor.
- If installation fails, inspect its nonzero exit and log. Do not announce
  completion or start a partially built workspace.
- If health fails, inspect the selected checkout's
  `.tmp/tools-dev/default/logs/` and check for port conflicts.
- If the icon is missing, run `03-copy-icon.sh` and `04-patch-agent-icon.sh`,
  rebuild the web app, and restart it.

Actual model requests and design generation require the user's configured
Janitor provider. They are separate acceptance steps and must not be inferred
from HTTP health or ACP discovery alone.

## See also

- `janitor-onboarding`: optional capability discovery.
- `janitor-config-audit`: preview configuration changes before merging them.
- `references/persistent-ports.md`: endpoint configuration.
- `references/upstream-compatibility.md`: registration anchors.
