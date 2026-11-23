---
name: janitor-nocodb
description: "Instalación guiada de NocoDB: tablas con interfaz y API."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [nocodb, database, postgres, api, docker, local-setup]
    category: devops
    related_skills: [janitor-n8n, janitor-lightrag]
---

# Janitor NocoDB Skill

Installs NocoDB — spreadsheet-style databases with a web UI and a REST API, for building
things that need a database — as two local containers on `127.0.0.1` only: `janitor-nocodb`
(the app) and `janitor-nocodb-db` (its Postgres). The user talks; you run the script. It never
runs `sudo`, never removes a container or a volume, and never asks for, stores or prints a
password or token: the first account is created by the user in the web UI.

## When to Use

- "Install / set up NocoDB", "I need a database with a UI", "an Airtable on my machine".
- "Is NocoDB working?", "stop NocoDB".
- Creating bases, tables and records on a NocoDB that is already installed (see Using NocoDB).

Not for: semantic search over documents (that is `janitor-lightrag`), deleting NocoDB data
(give the commands in Pitfalls; never run them).

## Prerequisites

- Linux or macOS, `python3` on `PATH`, `HERMES_HOME` set (the agent's `terminal` does it).
- Docker with `docker compose` v2, ~2 GB free, the port free (default 1980).
- Network access to pull `nocodb/nocodb:latest` and `postgres:16-alpine` the first time.

## How to Run

```bash
S=${HERMES_SKILL_DIR}/scripts/nocodb_setup.py
python3 $S preflight [--port N]           # read-only
python3 $S deploy [--port N]              # prints the plan, changes nothing
python3 $S deploy [--port N] --yes        # only after the user said yes to that plan
python3 $S verify [--port N]              # read-only: does NocoDB answer on loopback?
python3 $S stop [--yes]                   # stops the containers, keeps everything
```

- stdout: one JSON document (`ok`, and `reason` when `ok` is false). stderr: Spanish hints.
  Exit 0 ok, 1 refused/failed, 2 `HERMES_HOME` unset.
- The first `deploy --yes` pulls two images (a few minutes): run it with
  `terminal(background=true, notify=true)` and wait with `process(action="wait")`.
- `janitor services deploy nocodb` runs the same deploy (that command is the confirmation).
- `--port` is remembered in `nocodb.env`; later commands use it without the flag. The app's
  services screen checks the default port declared in `service.yaml` (1980).

## Quick Reference

| Command | Writes | Guarantees |
|---|---|---|
| `preflight` | nothing | Docker calls are inspect/info only |
| `deploy` | nothing | returns `plan` + `reason: confirmation_required` |
| `deploy --yes` | `<root>/docker/{nocodb-compose.yml,nocodb.env}` | loopback port; `compose up -d` only; keeps a compose you edited; `nocodb.env` (0600) holds only the internal database password and the JWT secret, generated once and kept |
| `verify` | nothing | GET `/` on `127.0.0.1`; `ok` on HTTP 2xx/3xx |
| `stop --yes` | nothing on disk | `docker stop`; volumes `janitor-nocodb-data`, `janitor-nocodb-pgdata` and files stay |

Preflight keys you act on: `blockers[]`, `docker.install_hint.command`, `docker.fix_hint`,
`port`, `service.state`, `health`, `foreign_containers[]`, `files`.

| Blocker | What to tell the user (they run any command themselves) |
|---|---|
| `docker_missing` | Show `docker.install_hint.command` |
| `docker_daemon_down`, `docker_permission_denied` | Show `docker.fix_hint` |
| `compose_v2_missing` | Arch: `sudo pacman -S docker-compose`; others: the `docker-compose-plugin` package |
| `port_busy` | Something else listens there: ask for another port, use it as `--port` |
| `disk_low` | Say how much is free (`disk.free_gb`) and what is needed |
| `foreign_containers` | Containers from an older install (it had a worker and Redis); see Pitfalls |

## Procedure

Talk to the user in Spanish, dry and direct (Janitor's voice). Show what you will change
before changing it.

1. Run `preflight`. If `service.state` is `running` and `health.responding` is true, say it
   is already installed, run `verify`, and stop unless they want something else.
2. Resolve each blocker with the table, one at a time; re-run `preflight` after each fix.
3. Run `deploy` (without `--yes`). Show the `plan` in plain Spanish: the files under
   `<root>/docker/`, the two images, the containers, the volumes, `127.0.0.1:<port>`, and that
   nothing is ever deleted. Ask for a yes.
4. On yes, run `deploy --yes` (background). On `ok: false`, report `reason`; for
   `health_timeout` quote each `failing[].container` with its `log_tail`. Volumes are kept;
   after the fix, re-run `deploy --yes`.
5. Run `verify`. Only with `ok: true` say it works. Then tell the user, in this order:
   - open `http://127.0.0.1:<port>` and sign up: the first account is the super admin
     (their email and password; you never see them). Until they do, anyone on this machine
     who opens that page first gets it;
   - for you to use the API they create a token in the UI (Team & Settings → API Tokens) and
     store it with `janitor config set NOCODB_API_TOKEN <token>` in their own terminal;
   - state / stop / start: `janitor services status|stop|start nocodb`.
6. Stop (on request): confirm, run `stop --yes`, list `kept`.

## Using NocoDB

Read the token without printing it, and send it as `xc-token`:

```bash
T=$(grep -m1 '^NOCODB_API_TOKEN=' "$HERMES_HOME/.env" | cut -d= -f2-)
B=http://127.0.0.1:1980
curl -s -H "xc-token: $T" $B/api/v2/meta/bases                                  # list bases
curl -s -H "xc-token: $T" $B/api/v2/meta/bases/<BASE_ID>/tables                 # list tables
curl -s -H "xc-token: $T" "$B/api/v2/tables/<TABLE_ID>/records?limit=25"        # read records
```

- Creating a base, table or column, and writing or deleting records, are mutations: show
  the user what you will create or change (names, columns, rows) and get a yes first.
- Responses key fields by column **title**, not `column_name`: read the table metadata
  (`GET /api/v2/meta/tables/<TABLE_ID>`) and map titles before parsing records.
- Column defaults are not applied to API inserts: send every value explicitly.
- MultiSelect columns have their own pattern: `${HERMES_SKILL_DIR}/references/multiselect-api.md`.
- API paths differ between releases (`/api/v2` vs `/api/v3`): if a documented path returns
  404, probe the other one with a read-only GET before building on it.
- A 401 with a valid token: an earlier version of this skill reported that some NocoDB
  releases also want the session cookie. Tell the user; never ask for their password.
- Read-only inspection without a token (structure only, no user data needed):
  `docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c "SELECT id, title FROM nc_bases_v2;"`.
- Official docs: https://nocodb.com/docs/product-docs

## Pitfalls

- `foreign_containers`: containers named `janitor-nocodb*` that this skill did not create
  (an older Janitor install used four containers, a different compose project and unnamed
  volumes). Deploy refuses rather than fight them. The user decides; the old containers can
  be removed with `docker rm -f janitor-nocodb janitor-nocodb-worker janitor-nocodb-db janitor-nocodb-redis`
  — their data stays in the old volumes (`docker volume ls | grep nocodb`), which the new
  install does not adopt. Never run it yourself.
- `nocodb.env` holds the Postgres password the `janitor-nocodb-pgdata` volume was initialised
  with: keep it. A `nocodb.env` without Janitor's first-line marker is used as is if it
  defines every variable the compose needs (else `env_file_incomplete` with the missing names).
- `deploy --yes` keeps a `nocodb-compose.yml` the user edited (`kept-user-file`).
- Never use `docker compose down`, `--remove-orphans` or `-v`: other Janitor stacks share
  `<root>/docker`.
- Deleting NocoDB data is a separate, explicit request. Give the commands, do not run them:
  `janitor services uninstall nocodb`, then
  `docker volume rm janitor-nocodb-data janitor-nocodb-pgdata` (irreversible).

## Verification

- `python3 $S verify` → `ok: true`, `health.status` 2xx/3xx.
- `janitor services status nocodb` → `running: responde`.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_guided_services.py`.
