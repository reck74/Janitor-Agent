---
name: janitor-agentmemory
description: "Deploy AgentMemory coding memory service locally for Janitor."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [memory, agentmemory, coding, docker, local-setup]
    category: devops
    config:
      janitor.agentmemory_port:
        description: "Local port for AgentMemory API service"
        default: 3111
        type: integer
---

# janitor-agentmemory

Deploy a local AgentMemory coding memory instance. Optional — provides
additional coding context memory beyond Honcho's session storage.

## Prerequisites

- Docker daemon running (for containerized deployment)
- Or: Node.js + npm (for native installation)
- Ports 3111, 3113 free on localhost (if using Docker)

## Usage

```bash
bash skills/janitor-agentmemory/scripts/deploy.sh
```

## What Gets Started

| Service | Container/Process | Port | Purpose |
|---------|-------------------|------|---------|
| AgentMemory | `janitor-agentmemory` | 3111, 3113 | Coding memory & context management |

## Verification

```bash
curl -f http://localhost:3111/health || echo "AgentMemory not responding"
```

## Rollback

```bash
cd ~/.janitor/docker && docker compose -f agentmemory-compose.yml down 2>/dev/null
# Or stop the systemd service:
# systemctl --user stop janitor-agentmemory
```
