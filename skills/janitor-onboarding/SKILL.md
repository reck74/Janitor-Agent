---
name: janitor-onboarding
description: "Janitor orientation and capability selector."
version: 2.0.0
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

The first-run installer gives you a working agent with:

- ~/.janitor/.env — environment variables
- ~/.janitor/config.yaml — agent configuration
- ~/.janitor/SOUL.md — agent persona
- ~/.janitor/skins/sentry-janitor.yaml — visual theme
- Optional: local Honcho memory (if you chose local setup during install)

## Optional Capabilities (Install as Skills)

| Skill | What It Does | Install Command |
|-------|-------------|-----------------|
| janitor-honcho | Local Honcho memory (if skipped at install) | bash skills/janitor-honcho/scripts/setup-honcho.sh |
| janitor-vault | Infisical secret vault | bash skills/janitor-vault/scripts/deploy.sh |
| janitor-firecrawl | Web scraping service | bash skills/janitor-firecrawl/scripts/deploy.sh |
| janitor-browser | Playwright browser automation | bash skills/janitor-browser/scripts/install.sh |
| janitor-agentmemory | Coding memory and context | bash skills/janitor-agentmemory/scripts/deploy.sh |

## Verification

After installing any skill, verify its health:

{"status":"ok"}{"status":"ok"}AgentMemory not responding
{"date":"2026-05-24T05:18:03.924Z","message":"Ok","emailConfigured":false,"inviteOnlySignup":true,"redisConfigured":true,"secretScanningConfigured":false,"auditLogStorageDisabled":false,"maxIdentityAccessTokenTTL":7776000}

## Rollback

To stop local services:



This shuts down containers but preserves data volumes.

## Post-Activation

After installing a capability skill, restart Janitor to pick up new
environment variables or configuration changes.

## Requirements

- Docker daemon running (docker info must succeed)
- docker compose available (v2 recommended)
- For individual skills, check their SKILL.md for port requirements

## Troubleshooting

### Docker not found

# Executing docker install script, commit: 2687d91ddeb3bd6aeae37a90947761efdee87030

WSL DETECTED: We recommend using Docker Desktop for Windows.
Please get Docker Desktop from https://www.docker.com/products/docker-desktop/

Client: Docker Engine - Community
 Version:    29.4.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.33.0
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.1.3
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 13
  Running: 9
  Paused: 0
  Stopped: 4
 Images: 30
 Server Version: 29.4.1
 Storage Driver: overlayfs
  driver-type: io.containerd.snapshotter.v1
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: 77c84241c7cbdd9b4eca2591793e3d4f4317c590
 runc version: v1.3.5-0-g488fc13e
 init version: de40ad0
 Security Options:
  seccomp
   Profile: builtin
  cgroupns
 Kernel Version: 6.6.87.2-microsoft-standard-WSL2
 Operating System: Ubuntu 24.04.4 LTS
 OSType: linux
 Architecture: x86_64
 CPUs: 16
 Total Memory: 25.44GiB
 Name: Dustin
 ID: 81994749-5535-4a07-926d-6688e73eb99f
 Docker Root Dir: /var/lib/docker
 Debug Mode: false
 Experimental: false
 Insecure Registries:
  127.0.0.0/8
  ::1/128
 Live Restore Enabled: false
 Firewall Backend: iptables

### Port conflicts

COMMAND     PID USER   FD   TYPE   DEVICE SIZE/OFF NODE NAME
janitor  619201 reck   38u  IPv4 33265126      0t0  TCP localhost:44762->localhost:1973 (CLOSE_WAIT)
python  3634400 reck   31u  IPv4 49517249      0t0  TCP localhost:48328->localhost:1973 (CLOSE_WAIT)

### Service wont start


