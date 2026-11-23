---
name: janitor-n8n
description: "Instalación guiada de n8n para automatizaciones locales."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [n8n, automation, workflows, docker, local-setup]
    category: devops
    related_skills: [janitor-nocodb, janitor-lightrag]
---

# Janitor n8n Skill

Installs n8n — visual workflow automation with webhooks and hundreds of integrations — as
one local container, `janitor-n8n`, on `127.0.0.1` only. The user talks; you run the script.
It never runs `sudo`, never removes a container or a volume, and never asks for, stores or
prints a password or key: the n8n owner account is created by the user in the web UI.

## When to Use

- "Install / set up n8n", "I want automations", "something to run workflows / webhooks".
- "Is n8n working?", "stop n8n".
- Building or calling workflows on an n8n that is already installed (see Using n8n).

Not for: n8n Cloud, deleting n8n data (give the commands in Pitfalls; never run them).

## Prerequisites

- Linux or macOS, `python3` on `PATH`, `HERMES_HOME` set (the agent's `terminal` does it).
- Docker with `docker compose` v2, ~2 GB free, the port free (default 5678).
- Network access to pull `docker.n8n.io/n8nio/n8n:latest` the first time.

## How to Run

```bash
S=${HERMES_SKILL_DIR}/scripts/n8n_setup.py
python3 $S preflight [--port N]           # read-only
python3 $S deploy [--port N]              # prints the plan, changes nothing
python3 $S deploy [--port N] --yes        # only after the user said yes to that plan
python3 $S verify [--port N]              # read-only: does n8n answer on loopback?
python3 $S stop [--yes]                   # stops the container, keeps everything
```

- stdout: one JSON document (`ok`, and `reason` when `ok` is false). stderr: Spanish hints.
  Exit 0 ok, 1 refused/failed, 2 `HERMES_HOME` unset.
- The first `deploy --yes` pulls the image (a few minutes): run it with
  `terminal(background=true, notify=true)` and wait with `process(action="wait")`.
- `janitor services deploy n8n` runs the same deploy (that command is the confirmation).
- `--port` is remembered in `n8n.env`; later commands use it without the flag. The app's
  services screen checks the default port declared in `service.yaml` (5678).

## Quick Reference

| Command | Writes | Guarantees |
|---|---|---|
| `preflight` | nothing | Docker calls are inspect/info only |
| `deploy` | nothing | returns `plan` + `reason: confirmation_required` |
| `deploy --yes` | `<root>/docker/{n8n-compose.yml,n8n.env,n8n-files/}` | loopback port; `compose up -d` only; keeps a compose you edited; `n8n.env` (0600) holds only the encryption key and timezone |
| `verify` | nothing | GET `/healthz` on `127.0.0.1`; `ok` only on HTTP 200 |
| `stop --yes` | nothing on disk | `docker stop`; volume `janitor-n8n-data` and files stay |

Preflight keys you act on: `blockers[]`, `docker.install_hint.command`, `docker.fix_hint`,
`port`, `service.state`, `health`, `foreign_containers[]`, `files`.

| Blocker | What to tell the user (they run any command themselves) |
|---|---|
| `docker_missing` | Show `docker.install_hint.command` |
| `docker_daemon_down`, `docker_permission_denied` | Show `docker.fix_hint` |
| `compose_v2_missing` | Arch: `sudo pacman -S docker-compose`; others: the `docker-compose-plugin` package |
| `port_busy` | Something else listens there: ask for another port, use it as `--port` |
| `disk_low` | Say how much is free (`disk.free_gb`) and what is needed |
| `foreign_containers` | A `janitor-n8n` container exists from an older install; see Pitfalls |

## Procedure

Talk to the user in Spanish, dry and direct (Janitor's voice). Show what you will change
before changing it.

1. Run `preflight`. If `service.state` is `running` and `health.responding` is true, say it
   is already installed, run `verify`, and stop unless they want something else.
2. Resolve each blocker with the table, one at a time; re-run `preflight` after each fix.
3. Run `deploy` (without `--yes`). Show the `plan` in plain Spanish: the files under
   `<root>/docker/`, the image, the container, the volume, `127.0.0.1:<port>`, and that
   nothing is ever deleted. Ask for a yes. Example tone: «Voy a descargar n8n, crear un
   contenedor que solo escucha en tu equipo y un volumen para sus datos. ¿Le doy?».
4. On yes, run `deploy --yes` (background). On `ok: false`, report `reason`; for
   `health_timeout` quote each `failing[].container` with its `log_tail`. Volumes are kept;
   after the fix, re-run `deploy --yes`.
5. Run `verify`. Only with `ok: true` say it works. Then tell the user, in this order:
   - open `http://127.0.0.1:<port>` and create the owner account there (their email and
     password; you never see them);
   - `n8n.env` holds the key that encrypts the credentials n8n stores: lose it and those
     credentials are unreadable. It stays in `<root>/docker/n8n.env`; back it up with the rest;
   - state / stop / start: `janitor services status|stop|start n8n`.
6. Stop (on request): confirm, run `stop --yes`, list `kept`.

## Using n8n

The n8n public REST API needs an API key the user creates in the UI (Settings → n8n API).
Never ask for it in the chat: the user stores it with `janitor config set N8N_API_KEY <clave>`
in their own terminal (or the API keys settings of the app). Then use it without printing it:

```bash
K=$(grep -m1 '^N8N_API_KEY=' "$HERMES_HOME/.env" | cut -d= -f2-)
curl -s -H "X-N8N-API-KEY: $K" http://127.0.0.1:5678/api/v1/workflows
```

- Production webhooks (`/webhook/<path>`) answer only while the workflow is active;
  `/webhook-test/<path>` only while the editor is listening.
- Show the user a workflow (nodes, what it calls, what it sends where) before creating or
  activating it; activation is a mutation.
- n8n's own docs are the source of truth: see `${HERMES_SKILL_DIR}/references/n8n-docs-extraction.md`
  (every page of docs.n8n.io is available as markdown by appending `.md`).

## Pitfalls

- `foreign_containers`: a container named `janitor-n8n` that this skill did not create
  (an older Janitor install). Deploy refuses rather than fight it. The user decides: the
  old one can be removed with `docker rm -f janitor-n8n` (the volume `janitor-n8n-data`
  survives and the new container reuses it, but credentials saved by the old install need
  the old encryption key). Never run it yourself.
- `deploy --yes` keeps a `n8n-compose.yml` the user edited (`kept-user-file`), and an
  `n8n.env` without Janitor's first-line marker is used as is if it defines every variable
  the compose needs (else `env_file_incomplete` with the missing names, never values).
- Never use `docker compose down`, `--remove-orphans` or `-v`: other Janitor stacks share
  `<root>/docker`.
- The image is `:latest`; re-running `deploy --yes` does not pull a newer one. Updating is a
  separate, explicit request: `docker pull docker.n8n.io/n8nio/n8n:latest` then `deploy --yes`.
- Deleting n8n data is a separate, explicit request. Give the commands, do not run them:
  `janitor services uninstall n8n`, then `docker volume rm janitor-n8n-data` (irreversible).

## Verification

- `python3 $S verify` → `ok: true`, `health.status: 200`.
- `janitor services status n8n` → `running: responde`.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_guided_services.py`.
