---
name: janitor-firecrawl
description: "Deploy Firecrawl web scraping service locally for Janitor."
version: 1.0.0
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
want local web scraping without using Firecrawl's cloud API.

## Prerequisites

- Docker daemon running
- `docker compose` available
- Ports 1974, 5672 (RabbitMQ) free on localhost
- ~4GB RAM available for containers

## Usage

```bash
bash skills/janitor-firecrawl/scripts/deploy.sh
```

## What Gets Started

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Firecrawl API | `janitor-firecrawl-api` | 1974 | Web page scraping & extraction |
| Firecrawl Playwright | `janitor-firecrawl-playwright` | 3000 | Browser automation worker |
| Firecrawl Postgres | `janitor-firecrawl-postgres` | — | Queue & metadata database |
| Firecrawl Redis | `janitor-firecrawl-redis` | — | Rate limiting & caching |
| Firecrawl RabbitMQ | `janitor-firecrawl-rabbitmq` | 5672 | Job queue broker |

## Verification

```bash
curl -f http://localhost:1974/v0/health/liveness || echo "Firecrawl not responding"
```

## Rollback

```bash
cd ~/.janitor/docker && docker compose -f firecrawl-compose.yml down
```

Data volumes are preserved unless explicitly removed with `docker volume rm`.
