---
name: janitor-onboarding
description: "Janitor orientation and capability selector."
version: 3.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [onboarding, orientation, skills, capabilities]
    category: devops
---

# janitor-onboarding

Welcome to Janitor. This skill does not deploy infrastructure itself.
Instead, it guides you through available capabilities that can be
installed as separate skills post-first-run.

## What Janitor Installed by Default

The first-run installer (`scripts/janitor-install.sh`) gives you a working agent with:

- `~/.janitor/.env` — environment variables (API keys)
- `~/.janitor/config.yaml` — agent configuration
- `~/.janitor/SOUL.md` — agent persona
- `~/.janitor/skins/sentry-janitor.yaml` — visual theme
- Optional: local Honcho memory (if you chose local setup during install)
- Optional: local Firecrawl web scraping (the installer prompts for it after Honcho)

Per AGENTS.md directive #9, none of this requires external services — you can
run `janitor` immediately after the base install.

## Optional Capabilities

Janitor's skills ship with the install tree under `janitor/skills/` and are
loaded through `skills.external_dirs`, so they update with `janitor update`.
They are grouped by kind:

| Group | Skills |
|-------|--------|
| `core` | janitor-core, janitor-config-audit, janitor-onboarding |
| `services` | janitor-honcho, janitor-firecrawl, janitor-n8n, janitor-lightrag, janitor-nocodb, janitor-waha |
| `agents` | janitor-code-review-agent, janitor-repo-research-agent |
| `integrations` | janitor-browser, janitor-desktop-launcher, janitor-opendesign, janitor-skill-integration |

Self-hosted services share one lifecycle command. Every deploy is idempotent
and fully independent of the others:

```bash
janitor services list              # what exists and what is running
janitor services deploy firecrawl  # install or repair
janitor services status honcho
janitor services stop n8n
janitor services start n8n
```

| Service | What It Does |
|---------|-------------|
| honcho | Local long-term memory (if skipped at install) |
| firecrawl | Web scraping and crawling API |
| n8n | Workflow automation |
| lightrag | Graph RAG knowledge base |
| nocodb | Spreadsheet-style database |
| waha | WhatsApp HTTP API |

Non-service capabilities still ship a script inside their skill, e.g.
`janitor-browser` → `scripts/install.sh`. `janitor agents list` shows the
specialized agents.

## Verification

Each skill's `SKILL.md` documents its own health checks. Common patterns:

```bash
# Honcho
curl -f http://localhost:1973/health

# Firecrawl
curl -f http://127.0.0.1:1974/v0/health/liveness

# Generic Docker health
docker ps --filter "name=janitor-" --format "{{.Names}}\t{{.Status}}"
```

## Rollback

```bash
janitor services stop <name>       # stop containers, keep everything
janitor services uninstall <name>  # remove containers, keep volumes and ~/.janitor/docker
```

`janitor services` never deletes Docker volumes. Data is only lost if you run
`docker volume rm` yourself.

## Post-Activation

After installing a capability skill, **restart Janitor** to pick up new
environment variables or configuration changes. The web tools (in particular)
only activate when `FIRECRAWL_API_URL` and `FIRECRAWL_API_KEY` are present in
`~/.janitor/.env` — `janitor-firecrawl`'s `deploy.sh` injects them for you.

## Requirements

- Docker daemon running (`docker info` must succeed)
- `docker compose` v2+ available
- For individual skills, check their `SKILL.md` for port and RAM requirements

## Troubleshooting

### Docker not found or not running

Install Docker via the official script, then start the daemon:

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"  # then log out and back in
```

Verify with `docker info` — it must return server info without errors.

### Port conflicts

If a skill's container cannot bind its port (e.g. `1974` for Firecrawl,
`1973` for Honcho), find what is holding it:

```bash
ss -tlnp | grep -E ':(1973|1974|5672)\b'
# or
sudo lsof -iTCP:1974 -sTCP:LISTEN
```

Kill the conflicting process or change the port mapping in the skill's
compose file (`~/.janitor/docker/<skill>-compose.yml`).

### Service won't start

Check container logs first:

```bash
docker logs <container-name> --tail 100
# e.g.
docker logs janitor-firecrawl-api --tail 100
```

Common causes: insufficient RAM (Firecrawl needs ~4GB across its 5 containers),
missing `~/.janitor/docker/<skill>.env` file (re-run `janitor services deploy <name>`),
or stale credentials (delete the env file and re-run the deploy).

### `janitor update` fails with "Fast-forward not possible"

If `janitor update` fails with "Fast-forward not possible (history diverged)",
run `bash scripts/migrate-janitor-update-flow.sh` from the Janitor repo, then
re-run `janitor update`.

### A Janitor skill still shows an old version after upgrading to 1.0

The first `janitor` start after an upgrade moves `~/.janitor` to the 1.0
layout: Janitor skills are read from the install tree, and unedited old copies
in `~/.janitor/skills` are removed (backup in `~/.janitor/.backup/v1-*/`).
Copies you edited are kept on purpose and shadow the shipped skill; the
migration lists them. Delete one to use the shipped version, or preview with
`bash scripts/migrate-janitor-v1.sh --dry-run` from the Janitor repo.
