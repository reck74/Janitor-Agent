# Plan: Integrate Self-Hosted Service Skills into Janitor Core

**Branch:** `feat/janitor-selfhost-service-skills`
**Date:** 2026-08-11
**Status:** In Progress

## Objective

Move 4 self-hosted service skills from `~/.janitor/skills/devops/` (local-only)
into the Janitor-Agent repository at `skills/devops/` so they are distributed
to all installations via `janitor update` → `sync_skills()`.

## Skills Being Integrated

| Skill | Service | Containers | Port |
|-------|---------|------------|------|
| `janitor-n8n` | n8n workflow automation | 1 (n8n) | 5678 |
| `janitor-lightrag` | LightRAG knowledge graph + RAG | 2 (app + PostgreSQL pgvector) | 9621 |
| `janitor-waha` | WhatsApp HTTP API (WAHA) | 1 (waha) | 3000 |
| `janitor-nocodb` | NocoDB no-code database | 4 (app + worker + PG + Redis) | 1980 |

## Distribution Mechanism (Verified)

The repo already has a skill distribution pipeline — no new infrastructure needed:

1. `skills/devops/<name>/` in the repo → discovered by `_discover_bundled_skills()`
   via `rglob("SKILL.md")`
2. Every `janitor` launch calls `sync_skills()` (`hermes_cli/main.py:2465`)
3. `sync_skills()` compares directory hashes repo vs `~/.janitor/skills/` and
   copies new/changed skills (including `scripts/`, `references/`)
4. `janitor update` does `git pull` → next launch syncs automatically
5. Category structure preserved: `skills/devops/janitor-n8n/` →
   `~/.janitor/skills/devops/janitor-n8n/`

## Architecture Per Skill (Ubicacion A — Bundled)

```
skills/devops/<skill-name>/
├── SKILL.md              # Knowledge (always visible to agent)
├── scripts/
│   ├── deploy.sh         # Idempotent deploy (generates creds, starts stack)
│   ├── <service>-compose.yml  # Docker Compose for the service
│   └── <helper>.sh       # Auth/pairing helpers as needed
└── references/
    └── *.md              # API reference, extraction playbooks
```

SKILL.md points deploy commands to `~/.janitor/skills/devops/<name>/scripts/deploy.sh`
— the sync pipeline places scripts there automatically.

## Sanitization Checklist

Every file must be scrubbed of machine-specific and personal data before commit.

### Hardcoded paths
- `/home/reck/...` → `${HERMES_HOME:-$HOME/.janitor}/...`
- `~/.janitor/docker/` (external scripts) → bundled inside `scripts/`

### Credentials & personal data
| What | Where | Replacement |
|------|-------|-------------|
| `janitor@airp.ws` | n8n, nocodb SKILL.md + scripts | `janitor@example.com` |
| `Jan1t0r!2026` (password in clear) | n8n SKILL.md:97,229 | `${N8N_USER_PASSWORD}` env ref |
| `reck` (dashboard username) | setup-waha.sh:48,257 | `admin` |
| `573012553871@c.us` (real phone) | waha SKILL.md:279,288 | `573001234567@c.us` (example) |
| `120363023195376833@g.us` (real group) | waha SKILL.md:537 | `120363000000000000@g.us` (synthetic) |
| `120363427601391559@g.us` (real group) | waha references, scripts | `120363000000000001@g.us` (synthetic) |
| Real contact names/phones | waha references | Generic examples |
| `172.17.0.1` (assumed bridge IP) | lightrag SKILL.md | Dynamic detection note |

### What stays as-is (correct conventions)
- `~/.janitor` → fork convention (`janitor_cli.py:25` forces `HERMES_HOME=~/.janitor`)
- `127.0.0.1:PORT` → correct for loopback-only services
- Container names `janitor-*` → AGENTS.md directive #5

## Execution Phases

### Phase 1: Scaffold (this plan document)
- [x] Create branch
- [x] Read all source files
- [x] Write this plan

### Phase 2: Port skills (parallel delegation — 4 subagents)
Each subagent receives one skill + its scripts/compose and produces:
- Sanitized SKILL.md (frontmatter compliant)
- scripts/deploy.sh (idempotent, `${HERMES_HOME}` parameterized)
- scripts/<service>-compose.yml (clean)
- Helper scripts as needed
- references/ (sanitized)

### Phase 3: Verification
- Regex sweep: `grep -rE '/home/reck|airp\.ws|Jan1t0r|573012553871|12036342|12036302|reck[^-]'`
- Frontmatter check: description ≤60 chars, platforms present
- Directory structure check

### Phase 4: Commit
- Single commit on `feat/janitor-selfhost-service-skills`

## File Inventory (What Gets Added)

```
skills/devops/janitor-n8n/
├── SKILL.md
├── scripts/
│   ├── deploy.sh
│   ├── n8n-compose.yml
│   └── n8n-auth.sh
└── references/
    └── n8n-docs-extraction.md

skills/devops/janitor-lightrag/
├── SKILL.md
└── scripts/
    ├── deploy.sh
    └── lightrag-compose.yml

skills/devops/janitor-waha/
├── SKILL.md
├── scripts/
│   ├── deploy.sh
│   ├── pair-waha.sh
│   ├── waha-compose.yml
│   └── diff-waha-group.py
└── references/
    └── contacts-and-groups.md

skills/devops/janitor-nocodb/
├── SKILL.md
├── scripts/
│   ├── deploy.sh
│   └── nocodb-compose.yml
└── references/
    └── multiselect-api.md
```

## Notes

- `janitor-waha/references/contacts-and-groups.md` contains real group names,
  phone numbers, and LIDs from the Aug 2026 audit. These must be replaced with
  synthetic examples before commit.
- The `diff-waha-group.py` script references real group IDs in its docstring —
  those get sanitized too.
- `setup-*.sh` scripts get renamed to `deploy.sh` to match the convention used
  by `janitor-firecrawl` and `janitor-honcho` (the existing bundled skills).
