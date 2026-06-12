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

Provisions a complete Open Design local stack and registers Janitor as its
native coding agent. The same `pnpm tools-dev` control plane that ships
with Open Design is the install target; Janitor is wired in via four
idempotent patches so future `git pull upstream` updates don't clobber the
integration.

## What This Skill Installs

- **Open Design source tree** at `~/open-design` (cloned from `nexu-io/open-design`, latest `open-design-v*` tag)
- **pnpm workspace** with `@open-design/daemon`, `web`, `sidecar`, `tools-dev`
- **Janitor agent registration** in `apps/daemon/src/runtimes/defs/janitor.ts`
- **Janitor in `BASE_AGENT_DEFS`** in `apps/daemon/src/runtimes/registry.ts`
- **Janitor PNG icon** in `apps/web/public/agent-icons/janitor.png`
- **Janitor in `ICON_EXT`** (and explicitly removed from `MONO_ICONS`) in `apps/web/src/components/AgentIcon.tsx`
- **Persistent port binding** so the MCP server URL never changes between restarts

## What This Skill Does NOT Do

- Does not modify the Open Design remote — `origin` stays at `nexu-io/open-design`
- Does not touch any file outside `apps/daemon/src/runtimes/` and `apps/web/src/components/` and `apps/web/public/agent-icons/`
- Does not install Janitor itself (assumed already installed at `~/.local/bin/janitor`)
- Does not run the Open Design daemon automatically — you start it with `scripts/start.sh` to keep ports stable

## Quick Start

The skill ships at `~/.janitor/skills/janitor-opendesign/` on a deployed Janitor
install. The examples below use `JANITOR_SKILLS_DIR` so they work regardless
of where the skill is installed (default install, profile, worktree, or
in-repo development checkout):

```bash
# Default install path
export JANITOR_SKILLS_DIR="${JANITOR_SKILLS_DIR:-$HOME/.janitor/skills}"

# 1. Install + register Janitor (idempotent, safe to re-run)
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/integrate-janitor.sh" register

# 2. Start the stack on persistent ports
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/start.sh"

# 3. Verify
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/status.sh"
```

For an in-repo development checkout, override the path:

```bash
export JANITOR_SKILLS_DIR="/path/to/Janitor-Agent/skills"
```

After step 2, the agent picker in Open Design shows **The Janitor** as a
native agent and your MCP clients can target `http://127.0.0.1:45351/mcp`.

## Persistent Ports

Open Design exposes a MCP server. If the daemon port changes between
restarts, every external MCP client config breaks. This skill binds the
daemon and web to fixed ports that survive restarts:

| Service  | Port | URL                                |
|----------|------|------------------------------------|
| Daemon   | 45351 | `http://127.0.0.1:45351`          |
| Web UI   | 45343 | `http://127.0.0.1:45343`          |
| **MCP**  | 45351 | `http://127.0.0.1:45351/mcp`      |

Override via env vars if defaults collide with other services on the host:

```bash
OD_DAEMON_PORT=56095 OD_WEB_PORT=55983 \
  bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/start.sh"
# Now document the new MCP URL everywhere you configured it.
```

## Idempotency Guarantees

Every script in this skill is **safe to re-run** at any time:

- `01-register-agent-def.sh` overwrites the def file (idempotent copy)
- `02-patch-registry.sh` checks for the import and the `BASE_AGENT_DEFS` entry; skips if present
- `03-copy-icon.sh` looks for `janitor.png` in two paths (alongside the script and in the project root)
- `04-patch-agent-icon.sh` uses `sed` with anchored patterns that never double-insert

This means you can re-run `integrate-janitor.sh` after every `git pull` upstream without breaking the integration. The skill rebuilds on the fly.

## Bundle Contents

```
janitor-opendesign/
├── SKILL.md                          # this file
├── agent-defs/
│   └── janitor.ts                    # RuntimeAgentDef for The Janitor
├── icon/
│   └── janitor.png                   # 310x311 RGBA, renders as <img>
├── references/
│   ├── persistent-ports.md           # why we pin ports
│   └── upstream-compatibility.md     # what changes if upstream renames anything
└── scripts/
    ├── 01-register-agent-def.sh      # copy janitor.ts into Open Design source tree
    ├── 02-patch-registry.sh          # register in BASE_AGENT_DEFS
    ├── 03-copy-icon.sh               # install PNG to public/agent-icons/
    ├── 04-patch-agent-icon.sh        # patch AgentIcon.tsx (ICON_EXT, not MONO_ICONS)
    ├── integrate-janitor.sh          # orchestrator: register | start | stop | status
    ├── start.sh                      # start with persistent ports
    ├── stop.sh                       # stop the stack
    └── status.sh                     # health check + MCP endpoint URL
```

## Compatibility With Upstream Syncs

When you sync Open Design upstream (`git pull upstream main`), the patches
this skill applies survive because:

1. **Janitor def file** lives under `apps/daemon/src/runtimes/defs/janitor.ts` — upstream ignores files in `defs/` that aren't in their `registry.ts` imports
2. **Registry entry** uses a stable insert point (after `hermesAgentDef,`) so merge conflicts are localized to one line
3. **Icon file** is a new addition that upstream won't touch
4. **AgentIcon.tsx** insert uses a stable anchor (`hermes: 'svg',`) — re-running the skill after a merge auto-resolves any conflict

If upstream renames the registry file or the AgentIcon component, the
skill's `sed` patterns will fail loudly. Re-author the patterns and
re-run.

## Known Limitations

- **Cold-start latency**: The first `pnpm install` rebuilds the daemon from source (15-90s depending on `better-sqlite3` prebuilt availability).
- **Agent probe latency**: `detectAgents()` runs all probes in parallel; Janitor's probe takes ~5-15s because it spawns `janitor acp --accept-hooks`. The browser may show an empty picker during the first 15s of a fresh page load.
- **WSL2 only on WSL 11+**: WSLg (Windows 11) is required for the desktop sidecar. WSL2 without WSLg runs daemon+web headless.
- **No Docker support**: This skill provisions the local pnpm workspace. For containerized deploy, use `opendesign-docker-deploy` (separate skill).

## Security Notes

- The daemon binds to `127.0.0.1` only by default. It does not expose `/api/*` externally.
- The MCP endpoint at `http://127.0.0.1:45351/mcp` is loopback-only. To expose it on the LAN, use an SSH tunnel or a reverse proxy with auth.
- v0.9.0+ enables `desktopAuthGate` on `/api/import/folder` — this is upstream spec, not a misconfiguration.
- The git remote `origin` is `nexu-io/open-design`. Verify after install: `git -C ~/open-design remote -v`.

## Recovery

- **Stack won't start**: `cd ~/open-design && pnpm install` (rebuilds any broken TypeScript)
- **Janitor missing from picker**: re-run `bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/integrate-janitor.sh" register` then restart
- **Icon missing**: re-run `bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/04-patch-agent-icon.sh"` (idempotent) then rebuild web
- **Port conflict**: another service is using 45351/45343. Override with `OD_DAEMON_PORT` / `OD_WEB_PORT` env vars and update your MCP client config
- **Health check fails**: check `~/open-design/.tmp/tools-dev/default/logs/daemon/latest.log`

## See Also

- `janitor-onboarding` — orientation for first-time Janitor users
- `janitor-config-audit` — diffs active config against the canonical janitor-core assets
- `opendesign-install` (upstream Janitor core) — original install skill this one extends
