# Persistent ports and MCP

The selected Open Design source checkout uses tools-dev. Janitor supplies
`--daemon-port` and `--web-port` so browser bookmarks and direct HTTP health
checks remain stable. Defaults are 45351 and 45343; these are configurable
application ports, not a reserved or guaranteed collision-free range.

```bash
OD_DAEMON_PORT=56095 OD_WEB_PORT=55983 bash scripts/start.sh web
```

Pass the same variables to `status.sh`. The `web` target starts daemon and
browser UI without Electron. Without a target, tools-dev starts its default
GUI stack. `stop.sh` addresses the default namespace inside the selected
checkout and does not need port arguments.

In Open Design 0.25.0, MCP runs over stdio through `od mcp`. There is no
HTTP `/mcp` endpoint. Fetch `/api/mcp/install-info` on the daemon or use
Settings → MCP and copy its `command`, `args` and complete `env` to the
external client. Sidecar-based configurations discover the running daemon;
the returned sidecar connection and data-directory fields must be preserved.
Direct CLI configurations may use the upstream `--daemon-url` option.

Keep this source checkout and its data separate from another running install.
If ports collide, choose free ports before starting; never stop an unrelated
service merely to obtain the defaults.
