---
name: janitor-onboarding
description: "Janitor orientation and capability selector."
version: 2.1.0
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

## Optional Capabilities (Install as Skills)

Each skill has its own `deploy.sh` (or equivalent) under `~/.janitor/skills/<name>/scripts/`.
Install whichever you need; they are fully independent.

| Skill | What It Does | Install Command |
|-------|-------------|-----------------|
| janitor-honcho | Local Honcho memory (if skipped at install) | `bash ~/.janitor/skills/janitor-honcho/scripts/setup-honcho.sh` |
| janitor-firecrawl | Web scraping service | `bash ~/.janitor/skills/janitor-firecrawl/scripts/deploy.sh` |
| janitor-browser | Playwright browser automation | `bash ~/.janitor/skills/janitor-browser/scripts/install.sh` |

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

Each skill ships a compose file under `~/.janitor/docker/`. Stop a skill with:

```bash
docker compose -f ~/.janitor/docker/<skill>-compose.yml down
```

Data volumes are preserved unless you pass `-v` or explicitly `docker volume rm`.

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
missing `~/.janitor/docker/<skill>.env` file (re-run the skill's `deploy.sh`),
or stale credentials (delete the env file and re-run `deploy.sh`).

### `janitor update` fails with "Fast-forward not possible"

If `janitor update` fails with "Fast-forward not possible (history diverged)",
run `bash scripts/migrate-janitor-update-flow.sh` from the Janitor repo, then
re-run `janitor update`.
