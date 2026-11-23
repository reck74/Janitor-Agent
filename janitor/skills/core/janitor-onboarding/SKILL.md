---
name: janitor-onboarding
description: "Mapa de Janitor: agentes, skills, aplicativos y archivos."
version: 4.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [onboarding, orientation, skills, profiles, templates, services]
    category: devops
---

# Janitor Onboarding Skill

Explains what Janitor is today and where everything lives, so the agent can answer
"what can you do / how do I add X" with real commands. It changes nothing by itself:
every command below that mutates state is run only after the user confirms.

## When to Use

- The user asks what Janitor is, what it can do, or how it is organised.
- The user wants another agent (researcher, project creator), an optional app
  (n8n, NocoDB, ...), or a skill added to or removed from an agent.
- The user asks where the config, persona, keys or memory are.

## Prerequisites

- The `janitor` command on `PATH` (installed by the desktop app or the installer).
- Optional apps need Docker running (`docker info` succeeds).

## How to Run

Read-only answers come from these commands via `terminal`:

```bash
janitor plantillas list                 # specialist templates and their skills
janitor profile list                    # existing agents (one profile each)
janitor skills list --enabled-only      # skills the main agent loads
janitor -p <perfil> skills list --enabled-only
janitor services list                   # optional apps and their state
janitor config path                     # main agent's config.yaml (-p <perfil> for another)
```

## Quick Reference

**Product.** Janitor runs as a desktop app and as a terminal UI (`janitor`). There is
one main agent (Janitor). Specialists are optional, each a separate Hermes profile
with its own skills, keys and empty memory — nothing is shared with the main agent.

| Need | Command |
|------|---------|
| Create a specialist | `janitor plantillas crear investigador` or `janitor plantillas crear creador-proyectos [--nombre NOMBRE]` |
| Talk to a specialist | `janitor -p <perfil>` |
| Install an optional app | `janitor services deploy <name>` |
| App state / stop / start | `janitor services status [name]`, `janitor services stop <name>`, `janitor services start <name>` |
| Remove an app (keeps data volumes) | `janitor services uninstall <name>` |
| Update Janitor | `janitor update` |

**Where things live** (main agent; a specialist uses `~/.janitor/profiles/<perfil>/`):

| Path | What |
|------|------|
| `~/.janitor/config.yaml` | Settings, model, `janitor.skills` |
| `~/.janitor/SOUL.md` | Persona (a specialist's = this persona + its role section) |
| `~/.janitor/.env` | API keys only |
| `~/.janitor/memories/` | Long-term memory of that agent |
| `~/.janitor/skins/sentry-janitor.yaml` | Terminal theme |
| `~/.janitor/docker/` | Files of the optional apps |
| `${HERMES_SKILL_DIR}/../../../catalog.yaml` | The skill catalog (every skill an agent may use, by purpose and template) |

## Procedure

**Which skills an agent has.** Run `janitor [-p <perfil>] skills list --enabled-only`.
The source of truth is the list `janitor.skills` in that agent's `config.yaml`: catalog
ids only. `skills.external_dirs` is generated from it — never edit it by hand.

**Change an agent's skills.**
1. Read the catalog with `read_file` on `${HERMES_SKILL_DIR}/../../../catalog.yaml`;
   pick ids (entries with `templates: []` are optional skills the user ticks).
2. Get the file with `janitor [-p <perfil>] config path`, show the user the edit to
   `janitor.skills`, and after confirmation apply it with `patch`.
3. The next start of that agent regenerates `skills.external_dirs`. The new list
   applies from the next session, never mid-conversation.

A skill the user removes stays removed: when a Janitor update adds a skill to the
agent's template, it is offered once (recorded in `janitor.catalog_seen`). A home
whose `config.yaml` has no `janitor.skills` (older installs) keeps loading the whole
Janitor skill tree.

**Create a specialist.** `janitor plantillas list`, confirm the name, then
`janitor plantillas crear <plantilla> [--nombre NOMBRE]`. It refuses an existing
profile, copies only the main model provider's key from `~/.janitor/.env` (never
messaging tokens) and starts with empty memory.

## Pitfalls

- `janitor profile create --clone` copies memory; specialists are created with
  `janitor plantillas crear` instead.
- Optional apps are never installed by default: deploy them only when asked.
- `janitor services uninstall` keeps Docker volumes; data is lost only if the user
  removes volumes with Docker themselves.

## Verification

- `janitor -p <perfil> skills list --enabled-only` shows the selected ids plus `hermes-agent`.
- `janitor services status <name>` reports `running` after a deploy.
