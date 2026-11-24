---
name: janitor-firecrawl
description: "Instalación guiada de Firecrawl local para extraer webs."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [web, scraping, search, firecrawl, docker, local-setup]
    category: devops
    related_skills: [janitor-system-health]
    config:
      janitor.firecrawl_port:
        description: "Local port for the Firecrawl API (loopback only)"
        default: 1974
        type: integer
---

# Janitor Firecrawl Skill

Installs Firecrawl **hosted on the user's own machine** and, once it answers, points this
profile's web tools (`web_search`, `web_extract`) at it. Purpose, exactly: web extraction
and search with a self-hosted Firecrawl. The service runs locally; **the pages are still
fetched from the Internet** by that service. Never promise "total privacy", "offline
search" or "fully local search": the sites still see the requests (from the user's IP
instead of Firecrawl's cloud), and search results still come from the web.

**Janitor already searches and reads the web without Firecrawl** (Hermes picks a keyless
backend by itself). Say so before anything else: most users do not need this. It is worth
it when the user wants JavaScript-heavy pages rendered by a local browser, crawling, or
does not want to depend on Firecrawl's cloud or a third-party search key. The user talks;
you run the scripts. It never runs `sudo`, never removes a container or a Docker volume,
and never asks for or prints a secret.

## When to Use

- "Instala / monta Firecrawl en local", "quiero extraer páginas con mi propio Firecrawl".
- "¿Firecrawl funciona?", "desactiva Firecrawl", "vuelve al buscador normal".

Not for: Firecrawl's cloud API (that is `janitor config set FIRECRAWL_API_KEY ...` and no
Docker), deleting Firecrawl data (give the commands in Pitfalls; never run them).

## Prerequisites

- Linux or macOS, `python3` on `PATH`; `activate` / `rollback` re-launch themselves with the
  Janitor runtime (the install tree's venv) because they use Hermes' config writers.
- `HERMES_HOME` set (the agent's `terminal` exports the active profile's home).
- Docker with `docker compose` v2, ~6 GB free for the images, ~4 GB of RAM to spare, the
  port free (default 1974). No API key of any kind is needed.

## How to Run

All steps run one script with the `terminal` tool:

```bash
S=${HERMES_SKILL_DIR}/scripts/firecrawl_setup.py
python3 $S preflight [--port N]              # read-only
python3 $S deploy [--port N]                 # containers only, no profile change
python3 $S verify [--port N] [--scrape URL]  # prove it answers, write nothing
python3 $S activate [--port N]               # this profile's web tools -> local Firecrawl
python3 $S rollback [--stop-containers]      # previous web backend back
python3 $S stop                              # stop the containers, keep data
```

- stdout: one JSON document (`ok`, and `reason` when `ok` is false). stderr: Spanish
  progress lines. Exit 0 ok, 1 refused/failed, 2 `HERMES_HOME` unset.
- `--port`: the skill config `janitor.firecrawl_port` (default 1974).
- `deploy` pulls ~5 GB the first time: run it with `terminal(background=true, notify=true)`
  and wait with `process(action="wait")`.
- `janitor services deploy firecrawl` runs the same deploy (no activation).

## Quick Reference

| Command | Writes | Guarantees |
|---|---|---|
| `preflight` | nothing | presence/equality only, never values |
| `deploy` | `<root>/docker/{firecrawl-compose.yml,firecrawl.env}` | idempotent; loopback port; `up -d` only; keeps a user-edited compose and an existing `firecrawl.env` |
| `verify` | nothing | `liveness.responds` is a real HTTP answer on `127.0.0.1` |
| `activate` | `.env` `FIRECRAWL_API_URL`, `config.yaml` `web.backend: firecrawl` (Hermes' own writers, same as `janitor config set`), state file | runs only if the local instance answers |
| `rollback` | `config.yaml`, `.env` | previous backend and URL back; volumes and files stay |

Preflight keys you act on: `recommendation` (`deploy`, `activate`, `already-active`,
`blocked`), `blockers[]`, `warnings[]`, `docker.install_hint.command`, `docker.fix_hint`,
`port`, `service.state`, `activation.per_capability_overrides`,
`activation.cloud_api_key_present`.

Blocker → what to tell the user (they run any command themselves):

| Blocker | Action |
|---|---|
| `docker_missing` | Show `docker.install_hint.command` |
| `docker_daemon_down`, `docker_permission_denied` | Show `docker.fix_hint` |
| `compose_v2_missing` | Arch: `sudo pacman -S docker-compose`; others: the `docker-compose-plugin` package |
| `port_busy` | Ask for another port; use it as `--port` and in the skill config |
| `disk_low` | Say how much is free (`disk.free_gb`) and what is needed |
| `stack_env_incomplete` | `firecrawl.env` was edited: the user restores the listed keys or moves the file away (the Postgres volume keeps the old password) |
| warning `low_memory` | Warn it may crawl slowly or crash; ask before going on |

## Procedure

Reply in Spanish, dry and direct (Janitor's tone). Show what you will change before
changing it.

1. Run `preflight`. If `recommendation` is `already-active`, run `verify`, report and stop
   unless the user wants a rollback.
2. Before installing, tell the user in two or three sentences: Janitor already searches
   without this; what they gain; it is five `janitor-firecrawl-*` containers (API, browser,
   Postgres, Redis, RabbitMQ) using ~5 GB of disk and a few GB of RAM; the pages are still
   fetched from the Internet. Something like: «Janitor ya busca en la web sin esto. Si aun
   así quieres tu propio Firecrawl: cinco contenedores, ~5 GB, y las páginas se siguen
   pidiendo a Internet, solo que desde tu equipo.» Ask if they still want it.
3. Resolve every blocker with the table above; re-run `preflight`.
4. State the plan and get a yes: download the images, start the containers on
   `127.0.0.1:<port>`, generate internal stack passwords in `firecrawl.env`. Then run
   `deploy --port <port>` (background). On `ok: false` report `reason`; for
   `health_timeout` quote each `failing[].container` with its `log_tail`. Volumes are kept;
   after a fix, re-run `deploy`.
5. Run `verify`. Optionally, with the user's OK (it fetches a real page from the Internet),
   `verify --scrape https://example.com` to prove extraction end to end.
6. Ask before switching: «¿Hago que este perfil use tu Firecrawl local para buscar y
   extraer?». On yes run `activate`. It changes `FIRECRAWL_API_URL` in the profile `.env`
   and `web.backend` in `config.yaml` with Hermes' own config writers. Report `changed[]`
   and the previous backend. If `activation.per_capability_overrides` is not empty, tell the
   user `web.search_backend` / `web.extract_backend` still win for that capability and give
   `janitor config set web.<key> firecrawl` for them to run if they want it.
7. After `activate` tell the user: it takes effect in the next session (open a new
   conversation or restart `janitor` / the app; the tool set is not swapped mid
   conversation); check with `python3 $S verify` or `janitor services status firecrawl`;
   undo by asking you for a rollback.
8. Rollback (on request): confirm, run `rollback` (add `--stop-containers` if they want the
   containers stopped) and list `kept_on_disk`. Never delete volumes.

## Pitfalls

- `activation.cloud_api_key_present: true` means the profile also has a Firecrawl cloud
  key. With `FIRECRAWL_API_URL` set, Hermes sends that key to the local instance instead of
  the cloud (local auth is off, so it is ignored there). It is kept; say so.
- If, after activation, `web_extract` fails with "API key is required", the Firecrawl SDK
  wants a non-empty key even for a self-hosted URL (not verified against the SDK). The local
  instance has authentication off, so any value works: the user runs
  `janitor config set FIRECRAWL_API_KEY local` themselves.
- The Services screen probes the `url` of `service.yaml` (port 1974). On another port it
  shows the containers but cannot confirm the service answers; `verify --port N` can.
- `firecrawl.env` holds only stack-internal passwords and is never regenerated (the
  Postgres volume was initialised with them). The profile `.env` never reaches the
  containers.
- Images are `:latest` tags from `ghcr.io/firecrawl/*`: a re-deploy may pull a newer
  Firecrawl.
- Deleting the data is a separate, explicit request. Give the commands, do not run them:
  `janitor services uninstall firecrawl` (containers), then
  `docker volume rm janitor-firecrawl-pgdata janitor-firecrawl-redis-data` (irreversible).

## Verification

- `python3 $S verify` → `ok: true`, `liveness.responds: true`; after activation
  `activation.active: true`.
- `python3 $S activate` → `hermes_resolution.extract_backend: firecrawl` and
  `hermes_resolution.api_url` equal to the local URL.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_firecrawl_skill.py`.
