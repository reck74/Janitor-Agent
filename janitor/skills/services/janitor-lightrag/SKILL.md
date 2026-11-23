---
name: janitor-lightrag
description: "Instalación guiada de LightRAG: base de conocimiento local."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [lightrag, knowledge-base, rag, knowledge-graph, docker, local-setup]
    category: devops
    related_skills: [janitor-nocodb, janitor-n8n]
---

# Janitor LightRAG Skill

Installs LightRAG — a knowledge base: it reads the user's documents, extracts entities and
relations into a graph and answers questions over them — as two local containers on
`127.0.0.1` only: `janitor-lightrag` (API + web UI) and `janitor-lightrag-db` (Postgres with
pgvector). The user talks; you run the script. It never runs `sudo`, never removes a
container or a volume, and never asks for or prints a key or password.

The data stays on this machine, but **the text of every document indexed and every
question asked goes to the AI provider** that does the LLM and embeddings work (OpenAI, and
MiniMax when chosen). Say so before installing.

## When to Use

- "Install / set up LightRAG", "I want a knowledge base", "index my documents and ask them".
- "Is LightRAG working?", "stop LightRAG".
- Indexing or querying on a LightRAG that is already installed (see Using LightRAG).

Not for: structured tables (that is `janitor-nocodb`), deleting the knowledge base (give the
commands in Pitfalls; never run them).

## Prerequisites

- Linux, `python3` on `PATH`, `HERMES_HOME` set (the agent's `terminal` does it).
- Docker with `docker compose` v2, ~3 GB free, the port free (default 9621).
- `OPENAI_API_KEY` stored in the profile `.env` (embeddings, and the LLM unless MiniMax is
  used). With `MINIMAX_API_KEY` also present the LLM part uses MiniMax (`--llm auto`).
- Network access to pull `ghcr.io/hkuds/lightrag:latest` and `pgvector/pgvector:pg18`.

## How to Run

```bash
S=${HERMES_SKILL_DIR}/scripts/lightrag_setup.py
python3 $S preflight [--port N]                                  # read-only
python3 $S deploy [--port N] [--llm auto|openai|minimax]         # prints the plan, changes nothing
python3 $S deploy [--port N] [--llm ...] --yes                   # only after the user said yes
python3 $S verify [--port N]                                     # read-only: does it answer?
python3 $S stop [--yes]                                          # stops the containers, keeps everything
```

- stdout: one JSON document (`ok`, and `reason` when `ok` is false). stderr: Spanish hints.
  Exit 0 ok, 1 refused/failed, 2 `HERMES_HOME` unset.
- The first `deploy --yes` pulls two images (several minutes): run it with
  `terminal(background=true, notify=true)` and wait with `process(action="wait")`.
- `janitor services deploy lightrag` runs the same deploy (that command is the confirmation).
- `--port` is remembered in `lightrag.env`; later commands use it without the flag. The app's
  services screen checks the default port declared in `service.yaml` (9621).

## Quick Reference

| Command | Writes | Guarantees |
|---|---|---|
| `preflight` | nothing | Docker calls are inspect/info only; credentials reported as present/absent |
| `deploy` | nothing | returns `plan` + `reason: confirmation_required` |
| `deploy --yes` | `<root>/docker/{lightrag-compose.yml,lightrag.env}` | loopback port; `compose up -d` only; keeps a compose you edited; `lightrag.env` (0600) holds only LightRAG's own generated secrets plus the one or two provider keys it needs; regenerated each deploy, generated secrets kept |
| `verify` | nothing | GET `/health` on `127.0.0.1`; `ok` only on HTTP 200 |
| `stop --yes` | nothing on disk | `docker stop`; volumes `janitor-lightrag-{storage,inputs,pgdata}` and files stay |

Preflight keys you act on: `blockers[]`, `credentials`, `docker.install_hint.command`,
`docker.fix_hint`, `port`, `service.state`, `health`, `foreign_containers[]`, `files`.

| Blocker | What to tell the user (they run any command themselves) |
|---|---|
| `docker_missing` | Show `docker.install_hint.command` |
| `docker_daemon_down`, `docker_permission_denied` | Show `docker.fix_hint` |
| `compose_v2_missing` | Arch: `sudo pacman -S docker-compose`; others: the `docker-compose-plugin` package |
| `embeddings_credential_missing`, `llm_credential_missing` | `OPENAI_API_KEY` must be stored (Procedure step 3) |
| `port_busy` | Something else listens there: ask for another port, use it as `--port` |
| `disk_low` | Say how much is free (`disk.free_gb`) and what is needed |
| `foreign_containers` | Containers from an older install; see Pitfalls |

## Procedure

Talk to the user in Spanish, dry and direct (Janitor's voice). Show what you will change
before changing it.

1. Run `preflight`. If `service.state` is `running` and `health.responding` is true, say it
   is already installed, run `verify`, and stop unless they want something else.
2. Explain in two sentences what it is and the privacy trade-off above (documents and
   questions go to OpenAI / MiniMax). Ask whether they still want it.
3. Keys. Never ask the user to paste a key in the chat. They store it themselves: the API
   keys settings of the app, or `janitor config set OPENAI_API_KEY <clave>` in their own
   terminal. Wait until they say it is done, re-run `preflight`, check `credentials`. If they
   paste one anyway: do not repeat it, tell them it is now in this conversation's history
   and should be rotated, and still have it stored as above.
4. Resolve the other blockers with the table; re-run `preflight` after each fix.
5. Run `deploy` (without `--yes`). Show the `plan` in plain Spanish: files under
   `<root>/docker/`, the two images, containers, volumes, `127.0.0.1:<port>`, which provider
   gets the text, and that nothing is ever deleted. Ask for a yes.
6. On yes, run `deploy --yes` (background). On `ok: false`, report `reason`; for
   `health_timeout` quote each `failing[].container` with its `log_tail`. Volumes are kept;
   after the fix, re-run `deploy --yes`. Changing keys later: re-run `deploy --yes`.
7. Run `verify`. Only with `ok: true` say it works. Then tell the user:
   - web UI at `http://127.0.0.1:<port>`, user `admin`; the password is in `lightrag.env`
     (`AUTH_ACCOUNTS`, after `admin:`): they read it themselves with
     `grep '^AUTH_ACCOUNTS=' <root>/docker/lightrag.env` in their own terminal — you never print it;
   - state / stop / start: `janitor services status|stop|start lightrag`.
8. Stop (on request): confirm, run `stop --yes`, list `kept`.

## Using LightRAG

Every route except `/health` needs the API key LightRAG generated. It lives in
`lightrag.env` under `files.deploy_dir` from `preflight` (`<root>/docker`). Read it without
printing it:

```bash
K=$(grep -m1 '^LIGHTRAG_API_KEY=' <root>/docker/lightrag.env | cut -d= -f2-)
B=http://127.0.0.1:9621
curl -s -H "X-API-Key: $K" "$B/documents/pipeline_status"                       # indexing progress
curl -s -X POST -H "X-API-Key: $K" -H "Content-Type: application/json" \
  "$B/query" -d '{"query": "...", "mode": "hybrid"}'                             # ask
```

- Indexing sends the document's text to the provider: name the files and get a yes first.
  Text: `POST $B/documents/text` with `{"text": "...", "file_source": "<name>"}`
  (`file_source` is required). Processing runs in the background: poll `pipeline_status`.
- Query modes: `naive`, `local`, `global`, `hybrid`, `mix`.
- Docs and the full variable list: https://github.com/HKUDS/LightRAG

## Pitfalls

- `foreign_containers`: containers named `janitor-lightrag*` that this skill did not create
  (an older Janitor install, which also depended on Honcho). Deploy refuses rather than fight
  them. The user decides; they can be removed with `docker rm -f janitor-lightrag janitor-lightrag-db`
  — the old data stays in the old volumes (`docker volume ls | grep lightrag`), which the new
  install does not adopt. Never run it yourself.
- The embeddings model fixes the vector size stored in Postgres. Switching it later means
  re-indexing into a fresh database: a separate, explicit request.
- `lightrag.env` holds the Postgres password the `janitor-lightrag-pgdata` volume was
  initialised with: keep it. A `lightrag.env` without Janitor's first-line marker is used as
  is if it defines every variable the compose needs (else `env_file_incomplete`).
- Reasoning models (MiniMax) make indexing and answers slow: minutes per document is normal.
- Never use `docker compose down`, `--remove-orphans` or `-v`: other Janitor stacks share
  `<root>/docker`.
- Deleting the knowledge base is a separate, explicit request. Give the commands, do not run
  them: `janitor services uninstall lightrag`, then
  `docker volume rm janitor-lightrag-storage janitor-lightrag-inputs janitor-lightrag-pgdata` (irreversible).

## Verification

- `python3 $S verify` → `ok: true`, `health.status: 200`.
- `janitor services status lightrag` → `lightrag: en marcha, responde`.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_guided_services.py`.
