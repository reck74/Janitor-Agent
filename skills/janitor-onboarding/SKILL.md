---
name: janitor-onboarding
description: |
  Onboarding skill for Janitor Agent — spins up local Honcho (memory) and Firecrawl
  (web scraping) services via Docker when JANITOR_LOCAL_SETUP=true is detected.
  This is the dirty work nobody wants to do: configure containers, map ports,
  verify that the services are actually listening before the agent tries to use them.
  If you found this skill, congratulations — you've been assigned the janitorial task
  of making sure the infrastructure doesn't collapse.
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [onboarding, docker, honcho, firecrawl, local-setup, infrastructure]
    category: devops
    config:
      janitor.local_services_timeout:
        description: "Seconds to wait for Docker services to become healthy"
        default: 60
        type: integer
      janitor.honcho_port:
        description: "Local port for Honcho service"
        default: 1973
        type: integer
      janitor.firecrawl_port:
        description: "Local port for Firecrawl service"
        default: 1974
        type: integer
---

# janitor-onboarding

Spin up local Honcho and Firecrawl services using Docker. Activated automatically
when `JANITOR_LOCAL_SETUP=true` is found in `~/.janitor/.env`.

This skill exists because apparently someone has to be the adult in the room and make
sure the plumbing works before the agent tries to flush data through it.

## Prerequisites

- Docker daemon running (`docker info` must succeed)
- `docker compose` available (v2 recommended)
- Ports 1973 and 1974 must be free on localhost

## Usage

```
/onboard
```

Or call the helper directly:

```bash
bash skills/janitor-onboarding/scripts/local-services.sh start
```

## What Gets Started

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Honcho | `honcho/agent` or equivalent | 1973 | Long-term memory & session storage |
| Firecrawl | `firecrawl/agent` or equivalent | 1974 | Web page scraping & extraction |

## Verification

After startup, the skill verifies each service is healthy:

```bash
curl -f http://localhost:1973/health || echo "Honcho not responding"
curl -f http://localhost:1974/health || echo "Firecrawl not responding"
```

If a service fails health checks, the skill logs the failure and instructs the user
on how to debug:

```
SERVICE UNAVAILABLE: honcho
  Likely causes:
    1. Port 1973 already in use:  lsof -i :1973
    2. Docker daemon not running:  docker info
    3. Image not pulled:           docker pull honcho/agent:latest
  Manual start:
    cd ~/.janitor/skills/janitor-onboarding/scripts
    docker compose up -d honcho
```

## Security Notes

- Local services are bound to `localhost` only — not exposed to external interfaces
- No API keys are required for local mode — services use anonymous auth
- If you ever change your mind and get real API keys, delete `JANITOR_LOCAL_SETUP=true`
  from `~/.janitor/.env` and set `HONCHO_API_KEY` / `FIRECRAWL_API_KEY` instead

## Troubleshooting

### Docker not found

```bash
# Install Docker if missing (Linux)
curl -fsSL https://get.docker.com | sh

# Verify
docker info
```

### Port conflicts

```bash
# Find what's using port 1973
lsof -i :1973
# or
ss -tlnp | grep 1973

# Kill the process or configure a different port in SKILL.md metadata
```

### Service won't start

```bash
# Check Docker logs
docker compose -f ~/.janitor/skills/janitor-onboarding/scripts/docker-compose.yml logs

# Pull latest images
docker compose -f ~/.janitor/skills/janitor-onboarding/scripts/docker-compose.yml pull
```

## Rollback

To stop local services:

```bash
bash skills/janitor-onboarding/scripts/local-services.sh stop
```

This shuts down containers but preserves data volumes.

## Post-Activation: Reconfigurar Janitor para Usar los Servicios Locales

**This is the critical step everyone skips, and then wonders why Janitor keeps blocking on OWASP.**

Once the Docker containers are confirmed healthy (see Verification above), you MUST reconfigure
Janitor's memory provider to actually use the local Honcho instance. Without this step,
Janitor will keep firing the OWASP fail-safe on every startup.

Run these commands in sequence using the `terminal` tool:

```bash
# 1. Agregar Honcho local base URL al .env
echo "HONCHO_BASE_URL=http://localhost:1973" >> ~/.janitor/.env

# 2. Agregar Firecrawl local base URL al .env
echo "FIRECRAWL_BASE_URL=http://localhost:1974" >> ~/.janitor/.env

# 3. Actualizar config.yaml para usar honcho como memory provider
python3 - << 'PYTHON_EOF'
import yaml
from pathlib import Path

config_path = Path.home() / ".janitor" / "config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f) or {}

config["memory"] = {"provider": "honcho"}

with open(config_path, "w") as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
PYTHON_EOF
```

After running these commands, restart Janitor. The OWASP fail-safe will pass because
`HONCHO_BASE_URL` is now set, and your memory sessions will be stored in the local
Docker volume instead of trying to reach a cloud endpoint with invalid credentials.

**Why this matters:** The installer sets `memory.provider: honcho` only when you provide
API keys upfront (Option 1). If you chose Option 2 (local Docker), Janitor starts with
no memory provider configured — by design, so it can boot without blocking. But once the
containers are running, you need to flip that switch yourself. I'm not going to do it
for you, but I'm also not going to let you run without doing it.

## Requirements

- Docker Engine ≥ 20.10
- docker compose plugin or docker-compose binary
- localhost network access