---
name: janitor-honcho
description: "Deploy Honcho memory service locally for Janitor."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [memory, honcho, docker, local-setup]
    category: devops
    config:
      janitor.honcho_port:
        description: "Local port for Honcho service"
        default: 1973
        type: integer
---

# janitor-honcho

Deploy a local Honcho memory instance for Janitor. This is the only service
considered fundamental for a functional Janitor installation.

## Prerequisites

- Docker daemon running
- `docker compose` available
- Port 1973 free on localhost
- `~/.janitor/.env` with `MINIMAX_API_KEY` (used as Anthropic backend for Honcho)

## Usage

```bash
bash skills/janitor-honcho/scripts/setup-honcho.sh
```

Or if already copied to `~/.janitor/scripts/`:

```bash
bash ~/.janitor/scripts/setup-honcho.sh
```

## What Gets Started

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Honcho API | `janitor-honcho-api` | 1973 | Long-term memory & session storage |
| Honcho Deriver | `janitor-honcho-deriver` | — | Background inference worker |
| Honcho Database | `janitor-honcho-database` | — | Postgres + pgvector |
| Honcho Redis | `janitor-honcho-redis` | — | Cache & pub/sub |

## Post-Activation

After starting Honcho, update `~/.janitor/.env`:

```bash
echo "HONCHO_BASE_URL=http://localhost:1973" >> ~/.janitor/.env
```

Then restart Janitor. The OWASP fail-safe will pass.

## Rollback

```bash
cd ~/.janitor/docker && docker compose -f honcho-compose.yml down
```

Data volumes are preserved unless explicitly removed.
