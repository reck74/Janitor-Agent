---
name: janitor-firecrawl
description: "Deploy Firecrawl web scraping service locally for Janitor."
version: 1.1.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [scraping, firecrawl, web, docker, local-setup]
    category: devops
    config:
      janitor.firecrawl_port:
        description: "Local port for Firecrawl service"
        default: 1974
        type: integer
---

# janitor-firecrawl

Deploy a local Firecrawl web scraping instance. Optional — only needed if you
want local web scraping without using Firecrawl's cloud API. Once deployed,
the agent's `web_search` and `web_extract` tools will route through this local
instance instead of the cloud API.

## Prerequisites

- Docker daemon running (`docker info` must succeed)
- `docker compose` v2 available
- Ports 1974 (API), 5672 (RabbitMQ) free on localhost
- ~4GB RAM available for the 5 containers
- `openssl` available (deploy.sh uses it to generate credentials)

## Usage

```bash
bash ~/.janitor/skills/janitor-firecrawl/scripts/deploy.sh
```

The script is idempotent — re-running it preserves existing credentials and
data volumes, only refreshing the compose file and restarting containers if
needed.

After a successful deploy, the script injects `FIRECRAWL_API_URL` and
`FIRECRAWL_API_KEY` into `~/.janitor/.env`. **Restart Janitor** for the web
tools to detect these variables and activate.

## What Gets Started

| Service | Container | Image | Port | Purpose |
|---------|-----------|-------|------|---------|
| Firecrawl API | `janitor-firecrawl-api` | `ghcr.io/firecrawl/firecrawl:latest` | 1974 | Web page scraping & extraction |
| Firecrawl Playwright | `janitor-firecrawl-playwright` | `ghcr.io/firecrawl/playwright-service:latest` | — | Browser automation worker |
| Firecrawl Postgres | `janitor-firecrawl-postgres` | `ghcr.io/firecrawl/nuq-postgres:latest` | — | Queue & metadata DB (pg_cron) |
| Firecrawl Redis | `janitor-firecrawl-redis` | `redis:alpine` | — | Rate limiting & caching |
| Firecrawl RabbitMQ | `janitor-firecrawl-rabbitmq` | `rabbitmq:3-management` | 5672 | Job queue broker |

All containers, volumes (`janitor-firecrawl-redis-data`, `janitor-firecrawl-pgdata`), and the network (`janitor-firecrawl-network`) carry the `janitor-` prefix per AGENTS.md directive #5.

## Verification

```bash
# Health check
curl -f http://127.0.0.1:1974/v0/health/liveness
# Expected: {"status":"ok"}

# Scrape test (note the space in the API key — that's intentional)
curl -f -X POST http://127.0.0.1:1974/v0/scrape \
  -H "Authorization: Bearer fc janitor-local" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","formats":["markdown"]}'

# pg_cron + container health (run from Janitor repo root)
bash scripts/verify-firecrawl-pgcron.sh
```

## Critical Notes

- **`POSTGRES_DB` MUST be `postgres`** — the `ghcr.io/firecrawl/nuq-postgres`
  image hardcodes `cron.database_name=postgres` and `CREATE EXTENSION pg_cron`
  fails with any other database name. `deploy.sh` enforces this; do not change it.
- **`NUQ_RABBITMQ_URL` is mandatory**, not optional. Firecrawl v2's extract-worker
  crashes without it. The deploy script wires it to the local RabbitMQ with a
  generated password that matches `RABBITMQ_DEFAULT_PASS`.
- **Local API key is `fc janitor-local` (with a space)** — this is the value the
  upstream Firecrawl image expects in `TEST_API_KEY`, mirrored into
  `FIRECRAWL_API_KEY` in `~/.janitor/.env`. The two must match exactly or scrape
  requests get 401.
- **Credentials live in `~/.janitor/docker/firecrawl.env`** (chmod 600), not in
  `~/.janitor/.env`. The compose file reads them via `env_file:` — do not inline
  secrets in the compose.

## Rollback

```bash
docker compose -f ~/.janitor/docker/firecrawl-compose.yml down
```

Data volumes (`janitor-firecrawl-pgdata`, `janitor-firecrawl-redis-data`) are
preserved unless explicitly removed with `docker volume rm`. To nuke everything:

```bash
docker compose -f ~/.janitor/docker/firecrawl-compose.yml down -v
rm ~/.janitor/docker/firecrawl.env ~/.janitor/docker/firecrawl-compose.yml
```

To deactivate web tools without removing the stack, comment out (or delete) the
`FIRECRAWL_API_URL` and `FIRECRAWL_API_KEY` lines in `~/.janitor/.env` and
restart Janitor.
