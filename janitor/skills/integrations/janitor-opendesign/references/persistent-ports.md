# Persistent Ports — Why This Skill Pins Them

## The Problem

Open Design runs three sidecars (daemon, web, desktop) under the
`pnpm tools-dev` control plane. Without explicit port flags, `tools-dev`
picks **random free ports** in the 55k-57k range every time it starts.
This breaks:

- **MCP clients** that hardcode the daemon URL in their config
  (Claude Desktop, Cursor, etc.)
- **Browser bookmarks** to the web UI
- **Reverse proxy configs** that forward to a known port
- **Documentation and onboarding scripts** that reference specific ports

## What This Skill Does

`scripts/start.sh` always invokes:

```bash
./node_modules/.bin/tools-dev start \
  --daemon-port "${OD_DAEMON_PORT:-45351}" \
  --web-port    "${OD_WEB_PORT:-45343}"
```

The `tools-dev` control plane has native flags for this (see
`tools/dev/src/index.ts:1082`). When both flags are present, ports are
deterministic. When absent, `tools-dev` allocates randomly.

## The Stop Caveat

`tools-dev stop` does NOT accept `--daemon-port` / `--web-port`. It only
needs `--namespace` (which defaults to `default`). So `stop.sh` is
simpler:

```bash
./node_modules/.bin/tools-dev stop
```

This is fine because `stop` doesn't need to know the port — it
identifies the sidecars by the canonical `--od-stamp-app=daemon|web|desktop`
discriminator in their command line (visible via `ps`).

## When Ports COLLIDE

If 45351 or 45343 are already taken on the host (another service, a
previous install, etc.), override before starting:

```bash
OD_DAEMON_PORT=56095 OD_WEB_PORT=55983 bash scripts/start.sh
```

Then update every place that referenced the old ports:

- MCP client config
- Browser bookmarks
- Reverse proxy upstream definitions
- Documentation that shows URLs

The skill does NOT track port history — once you change them, you own
the new values.

## Why 45351 / 45343?

- Both are in the IANA "dynamic/private" range (49152-65535), so they
  don't collide with well-known services
- They are not the Open Design upstream default range (55k-57k), so a
  default `tools-dev start` without flags will pick DIFFERENT ports,
  making port collisions easy to spot
- 45351 → 4-5-3-5-1 (readable) for the daemon, which is the one MCP
  clients connect to
- 45343 → 4-5-3-4-3 (also readable) for the web UI

You can change them; these are just the defaults this skill ships with.
