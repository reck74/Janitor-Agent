---
name: janitor-vault
description: "Deploy Infisical secret vault locally for Janitor."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [vault, secrets, infisical, docker, local-setup, security]
    category: security
    config:
      janitor.infisical_port:
        description: "Local port for Infisical service"
        default: 8080
        type: integer
---

# janitor-vault

Deploy a local Infisical secret vault. This is an optional capability, not
required for Janitor to function. If you already have secrets in `~/.janitor/.env`,
Janitor works without Infisical.

## Prerequisites

- Docker daemon running
- `docker compose` available
- Port 8080 free on localhost
- Optional: Infisical CLI for secret injection from external sources

## Usage

```bash
bash skills/janitor-vault/scripts/deploy.sh
```

## What Gets Started

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Infisical | `janitor-infisical` | 8080 | Secret management & env injection |
| Infisical Postgres | `janitor-postgres` | — | Infisical database |
| Infisical Redis | `janitor-redis` | — | Session/cache backend |

## Verification

```bash
curl -f http://localhost:8080/api/status || echo "Infisical not responding"
```

## Migration from plain .env

If you previously stored secrets in `~/.janitor/.env` and want to migrate to
Infisical:

1. Start Infisical via this skill.
2. Run `bash skills/janitor-vault/scripts/vault-bootstrap.sh` to import existing keys.
3. Update `~/.janitor/.env` to reference Infisical if desired (optional).

## Rollback

```bash
cd ~/.janitor/docker && docker compose -f docker-compose.yml down
```

## Security Notes

- Local services are bound to `localhost` only.
- Default admin credentials are generated during first run.
- Always change default passwords in production deployments.
