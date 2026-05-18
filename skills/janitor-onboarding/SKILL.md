---
name: janitor-onboarding
description: "Onboarding for Janitor Agent — spins up 5 local Docker services."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [onboarding, docker, honcho, firecrawl, agentmemory, infisical, local-setup, infrastructure]
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
      janitor.agentmemory_port:
        description: "Local port for AgentMemory API service"
        default: 3111
        type: integer
      janitor.infisical_port:
        description: "Local port for Infisical service"
        default: 8080
        type: integer
---

# janitor-onboarding

Spin up local Honcho, Firecrawl, AgentMemory, Infisical, and Playwright services
using Docker. Activated automatically when `JANITOR_LOCAL_SETUP=true` is found
in `~/.janitor/.env`.

## Prerequisites

- Docker daemon running (`docker info` must succeed)
- `docker compose` available (v2 recommended)
- Ports 1973, 1974, 1975, 3111, 3113, and 8080 must be free on localhost
- Optional: Infisical CLI (`npm install -g @infisical/cli`) for secret injection

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
| Honcho | `janitor-honcho` | 1973 | Long-term memory & session storage |
| Firecrawl | `janitor-firecrawl` | 1974 | Web page scraping & extraction |
| AgentMemory | `janitor-agentmemory` | 3111, 3113 | Coding memory & context management |
| Infisical | `janitor-infisical` | 8080 | Secret management & env injection |
| Playwright | `janitor-playwright` | 1975 | Browser automation |

## Verification

After startup, the skill verifies each service is healthy:

```bash
curl -f http://localhost:1973/health || echo "Honcho not responding"
curl -f http://localhost:1974/health || echo "Firecrawl not responding"
curl -f http://localhost:3111/health || echo "AgentMemory not responding"
curl -f http://localhost:8080/api/v1/health || echo "Infisical not responding"
docker ps --filter "name=janitor-playwright" --filter "status=running" || echo "Playwright not running"
```

If a service fails health checks, the skill logs the failure and instructs the user
on how to debug:

```
SERVICE UNAVAILABLE: honcho
  Likely causes:
    1. Port 1973 already in use:  lsof -i :1973
    2. Docker daemon not running:  docker info
    3. Image not pulled:           docker pull janitor-honcho:latest
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

## Honcho .env — Infrastructure Hack (MiniMax as Anthropic Backend)

When `local-services.sh start` runs, it automatically generates a `honcho.env` file
in the scripts directory by reading credentials from `~/.janitor/.env`.

The generated file contains:

```
TRANSPORT=anthropic
BASE_URL=https://api.minimax.io/anthropic
LLM_ANTHROPIC_API_KEY=<MINIMAX_API_KEY from ~/.janitor/.env>
LLM_OPENAI_API_KEY=<OPENAI_API_KEY from ~/.janitor/.env>
```

**Why this hack exists:** Honcho exposes an Anthropic-compatible API transport, but the
actual model can be MiniMax (or any OpenAI-compatible backend). By setting
`TRANSPORT=anthropic` and `BASE_URL=https://api.minimax.io/anthropic`, the MiniMax
API key (stored as `MINIMAX_API_KEY` in the Janitor .env) gets re-used as
`LLM_ANTHROPIC_API_KEY` so Honcho can call MiniMax via the Anthropic transport.
OpenAI is similarly forwarded as `LLM_OPENAI_API_KEY` for any pure-OpenAI calls Honcho
might make directly.

This is injected into the container via `env_file: ./honcho.env` in docker-compose.yml.

## Rollback

To stop local services:

```bash
bash skills/janitor-onboarding/scripts/local-services.sh stop
```

This shuts down containers but preserves data volumes.

## Post-Activation: Reconfigurar Janitor para Usar los Servicios Locales

**This is the critical step everyone skips, and then wonders why Janitor keeps blocking on OWASP.**

Once `local-services.sh start` has confirmed both containers are healthy, you MUST reconfigure
Janitor's memory provider to use the local Honcho instance. The Honcho .env (with your
MiniMax key as `LLM_ANTHROPIC_API_KEY`) is generated automatically — you just need to
flip the memory provider switch.

Run these commands using the `terminal` tool:

```bash
# 1. Tell Janitor where Honcho is running locally
echo "HONCHO_BASE_URL=http://localhost:1973" >> ~/.janitor/.env

# 2. Flip memory.provider to honcho in config.yaml
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
`HONCHO_BASE_URL` is now set, and your memory sessions will live in the local Docker
volume — no cloud calls, no credential leakage, no excuses.

**Why this matters:** The installer skips `memory.provider: honcho` when you chose
Option 2 (local Docker). Janitor boots with no memory provider so it can start without
blocking. But the moment your Docker containers are up, you need to close that gap.
The `.env` generation happens automatically on `local-services.sh start` — you just
need to restart Janitor to pick it up.

## Requirements

- Docker Engine ≥ 20.10
- docker compose plugin or docker-compose binary
- localhost network access