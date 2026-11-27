---
name: janitor-honcho
description: "Instalación guiada de la memoria Honcho, nube o local."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [memory, honcho, docker, local-setup, cloud]
    category: devops
    related_skills: [janitor-system-health]
    config:
      janitor.honcho_port:
        description: "Local port for the Honcho API (loopback only)"
        default: 1973
        type: integer
---

# Janitor Honcho Skill

Installs Honcho — the advanced memory level — when the user asks for it: checks the
machine, deploys the local `janitor-honcho-*` containers or connects Honcho Cloud,
verifies a real round trip and only then switches the profile's `memory.provider` to
`honcho`. The user talks; you run the scripts. The base memory stays Hermes' built-in
memory until this skill finishes successfully. It never runs `sudo`, never removes a
container or a Docker volume, and never asks for a secret in the chat.

## When to Use

- "Install / set up / activate Honcho", "I want better long-term memory".
- "Is Honcho working?", "turn Honcho off", "go back to the normal memory".

Not for: other memory providers, deleting Honcho data (give the user the commands in
Pitfalls; never run them).

## Prerequisites

- Linux or macOS, `python3` on `PATH`. The scripts re-launch themselves with the Janitor
  runtime (the install tree's venv) for steps that use Hermes code.
- `HERMES_HOME` set (the agent's `terminal` exports the active profile's home).
- Local mode: Docker with `docker compose` v2, `git`, ~5 GB free, the port free, and an
  `OPENAI_API_KEY` in the profile `.env` (Honcho's LLM and embeddings; with
  `MINIMAX_API_KEY` also present the LLM part uses MiniMax). Cloud mode: an account at
  https://app.honcho.dev and its API key.

## How to Run

All steps run one script with the `terminal` tool:

```bash
S=${HERMES_SKILL_DIR}/scripts/honcho_setup.py
python3 $S preflight [--port N]                   # read-only
python3 $S deploy [--port N] [--llm auto|openai|minimax]
python3 $S verify --mode local|cloud [--port N]   # prove it, write nothing
python3 $S activate --mode local|cloud [--port N] [--peer-name NAME]
python3 $S verify                                 # check what is active on disk
python3 $S rollback [--stop-containers]
python3 $S cloud-login                            # device-code sign-in (see Pitfalls)
```

- stdout: one JSON document (`ok`, and `reason` when `ok` is false). stderr: Spanish
  progress lines. Exit 0 ok, 1 refused/failed, 2 `HERMES_HOME` unset.
- `--port`: the value of the skill config `janitor.honcho_port` (default 1973).
- `deploy` can take 10+ minutes the first time (image build): run it with
  `terminal(background=true, notify=true)` and wait with `process(action="wait")`.
- `janitor services deploy honcho` runs the same deploy.

## Quick Reference

| Command | Writes | Guarantees |
|---|---|---|
| `preflight` | nothing | presence of secrets only, never values |
| `deploy` | `<root>/docker/{honcho-compose.yml,honcho-llm.env,honcho-db.env}`, `<root>/src/honcho` | idempotent; loopback port; `up -d` only; keeps user-edited files; failure names the container + last log lines |
| `activate` | `honcho.json` (backup first), `.env` `HONCHO_BASE_URL` (local), `config.yaml` `memory.provider` | runs only after a successful round trip; refuses if the `janitor` launcher would refuse to start |
| `rollback` | `config.yaml`, `.env` | restores the previous provider; volumes, `honcho.json`, backups stay |

Preflight keys you act on: `recommendation` (`local`, `cloud`, `already-active`),
`modes.local.blockers[]`, `modes.cloud.credential` (`api_key`/`oauth`/`none`),
`docker.install_hint.command`, `docker.fix_hint`, `port`, `deriver`, `service.state`,
`service.db_credentials` (`legacy-shared` → see Pitfalls: re-run `deploy`).

Blocker → what to tell the user (they run any command themselves):

| Blocker | Action |
|---|---|
| `docker_missing` | Show `docker.install_hint.command`, or offer cloud |
| `docker_daemon_down`, `docker_permission_denied` | Show `docker.fix_hint` |
| `compose_v2_missing` | Arch: `sudo pacman -S docker-compose`; others: the `docker-compose-plugin` package |
| `port_busy` | Ask for another port; use it as `--port` and in the skill config |
| `llm_credential_missing`, `embeddings_credential_missing` | `OPENAI_API_KEY` must be stored (see Procedure step 4), or offer cloud |
| `disk_low`, `git_missing` | Say what is missing; offer cloud |

## Procedure

Reply in Spanish. Show what you will change before changing it.

1. Run `preflight`. If `recommendation` is `already-active`, run `verify` (no `--mode`),
   report the result and stop unless the user wants changes or a rollback.
2. Explain the choice in two or three sentences and recommend `recommendation`:
   - **A · Honcho Cloud**: no Docker; needs an account at app.honcho.dev; the
     conversations are stored and processed by Honcho's cloud.
   - **B · Local**: four `janitor-honcho-*` containers on this machine (API, deriver,
     Postgres, Redis); needs Docker and an LLM key for the deriver; data stays here,
     the text the deriver analyses goes to that LLM provider (MiniMax/OpenAI).
   Add once: the current built-in memory is not copied into Honcho, and Honcho's memory
   is not copied back on rollback. List the blockers of the mode you do not recommend.
   Ask which one. Ask nothing else yet.
3. Secrets. Never ask the user to paste a key in the chat. A key is stored by the user:
   - desktop app: the Honcho API key field in the memory settings (Honcho), or the API
     keys settings for `OPENAI_API_KEY` — both write the profile `.env`;
   - their own terminal: `janitor config set HONCHO_API_KEY <clave>` /
     `janitor config set OPENAI_API_KEY <clave>` (upper-case keys go to `.env`).
   Tell them which key and where, wait until they say it is done, re-run `preflight` and
   check `credentials.<NAME>` is `true`. If they paste a key anyway: do not repeat it,
   tell them it is now in this conversation's history and should be rotated, and still
   have it stored through one of the paths above.
4. Mode B (local):
   1. Resolve every `modes.local.blockers` entry with the table above; re-run `preflight`.
   2. State the plan and get a yes: clone Honcho (pinned commit) into `<root>/src/honcho`,
      build one image (~2-3 GB), start four containers on `127.0.0.1:<port>`, then switch
      memory to Honcho for this profile.
   3. Run `deploy --port <port>` (background, see How to Run). On `ok: false`, report
      `reason`; for `health_timeout` quote each `failing[].container` with its
      `log_tail`. Volumes are kept; after the fix, re-run `deploy`.
   4. Run `activate --mode local --port <port>`.
5. Mode A (cloud):
   1. If `modes.cloud.credential` is `none`, do step 3 for `HONCHO_API_KEY`
      (from https://app.honcho.dev), or offer `cloud-login` (see Pitfalls).
   2. Run `verify --mode cloud`; on failure report `round_trip.error` (wrong key,
      no network) and stop.
   3. Get a yes, then run `activate --mode cloud`.
6. `activate` refusals change nothing: `verification_failed` (report
   `verification.reason` / `round_trip.error`, fix, retry), `failsafe_would_block`
   (cloud with no `HONCHO_API_KEY` and no API key or OAuth grant in `honcho.json`: go to
   step 3), `honcho_json_unparseable` (the user
   fixes or moves the file).
7. After `activate` with `ok: true` tell the user, in this order:
   - what changed (`changed[]`) and the backup of the old `honcho.json`
     (`honcho_json_backup`), and the previous provider;
   - it takes effect in the next session: this conversation keeps its memory (the system
     prompt is not rebuilt mid-conversation); open a new conversation or restart
     `janitor` / the app;
   - check: `python3 $S verify` or `janitor honcho status`; containers:
     `janitor services status honcho`, stop/start: `janitor services stop|start honcho`;
   - undo: ask you for a rollback.
8. Rollback (on request): confirm, run `rollback` (add `--stop-containers` if the user
   wants the containers stopped) and list `kept_on_disk`. Never delete volumes.

## Pitfalls

- Activation only after verification is the safety net: the `janitor` launcher refuses to
  open a session when `memory.provider: honcho` has no credential (`HONCHO_API_KEY` /
  `HONCHO_BASE_URL`, or an API key, OAuth grant or base URL in `honcho.json`); the user
  gets out of it with `janitor memory off`. Never set `memory.provider` by hand or with
  another command.
- `cloud-login` (device code: the user opens a URL and types a code; prints one
  `device_code` JSON line first, run it in the background and relay `user_code` and
  `verification_uri`) stores an OAuth grant in `honcho.json`, which the launcher accepts:
  then run `verify --mode cloud` and `activate --mode cloud` as with an API key. Do not
  use `janitor memory setup honcho`: it activates before verifying.
- `deploy` keeps a `honcho-compose.yml` or `honcho-llm.env` the user edited
  (`kept-user-file`); it only replaces files Janitor shipped (old copy backed up).
- Postgres credentials are per install: `deploy` generates them in `honcho-db.env` (mode
  0600) and the compose file ships none. Installs made before that share one password
  that is public in the repository history. When `preflight` reports
  `service.db_credentials: legacy-shared`, tell the user and, with their yes, re-run
  `deploy`: it keeps the `janitor-honcho-pgdata` volume and its role, sets a new password
  inside the database and recreates the containers (`db_credentials: rotated`). On
  `db_credential_sync_failed` nothing is lost; fix what `log` names and re-run `deploy`.
  The database port was never published, so the old password was reachable only from
  this machine's Docker network. `user-managed` (the user's own compose): say that a
  password copied from Janitor's old compose is public and theirs to change. Never
  print the contents of `honcho-db.env`.
- `honcho-llm.env` holds only the LLM keys Honcho needs (mode 0600); the containers
  never see the rest of `.env`. Changing keys later: re-run `deploy`.
- One local Honcho serves every profile on the machine; `activate` / `rollback` act on
  the active profile only.
- Deleting Honcho data is a separate, explicit request. Give the commands, do not run
  them: `janitor services uninstall honcho` (containers), then
  `docker volume rm janitor-honcho-pgdata janitor-honcho-redis-data janitor-honcho-api-data`
  (irreversible).

## Verification

- `python3 $S verify` → `ok: true`, `memory_provider: honcho`, `round_trip.ok: true`,
  `launcher_gate: true`.
- `python3 $S preflight` → `service.api_healthy: true` (local).
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_honcho_skill.py`.
