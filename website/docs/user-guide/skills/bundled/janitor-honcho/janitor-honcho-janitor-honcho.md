---
title: "Janitor Honcho — Deploy and verify Janitor's mandatory Honcho memory"
sidebar_label: "Janitor Honcho"
description: "Deploy and verify Janitor's mandatory Honcho memory"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Honcho

Deploy and verify Janitor's mandatory Honcho memory.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-honcho` |
| Version | `1.0.0` |
| Author | Janitor Agent |
| License | MIT |
| Platforms | linux, macos |
| Tags | `memory`, `honcho`, `docker`, `local-setup` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Janitor Honcho

Honcho is part of the base installation. Choose local Docker or Honcho cloud during setup. Docker and MiniMax are required in both modes. Local memory additionally needs `OPENAI_API_KEY` for embeddings; cloud only needs `MINIMAX_API_KEY` and `HONCHO_API_KEY`.

Run `janitor setup` to repair configuration. The shared installer installs the catalog provider at `e2d2aba182862deeb846e5cd4a30a41bce0ed82a`, prepares dependencies through PM and checks the memory API before reporting success. The local server uses the same audited source commit.

To redeploy local memory from a configured installation:

```bash
bash skills/janitor-honcho/scripts/deploy.sh
```

The compatibility entry `bash scripts/setup-honcho.sh` delegates here. Set `HERMES_HOME` to the profile you intend to repair; it takes precedence over the installation root in `JANITOR_HOME`. The installed skill resolves the `janitor` PM launcher even outside the source checkout. Secrets are read as dotenv data, never evaluated as shell commands.

| Component | Container | Exposure |
|---|---|---|
| API | `janitor-honcho-api` | `127.0.0.1:1973` |
| Deriver | `janitor-honcho-deriver` | Internal |
| PostgreSQL + pgvector | `janitor-honcho-database` | Internal |
| Redis | `janitor-honcho-redis` | Internal |

MiniMax handles reasoning; OpenAI handles local embeddings. The compose file, private service environment and model configuration are installed under the profile home. Existing database credentials and named volumes are preserved. Upgrades take a database dump before running server migrations; a stopped existing database must be started before upgrading.

To stop this deployment without deleting data:

```bash
docker compose --project-name janitor-honcho --env-file "$HOME/.janitor/honcho.env" \
  -f "$HOME/.janitor/docker/honcho-compose.yml" down
```

Backups live under the selected profile's `backups/`. The checksum manifest includes service secrets and configuration under `docker/`, committed SQLite state, and the PostgreSQL dump taken before server migrations. Do not remove volumes during a reinstall.

To verify and restore a snapshot into a **new** recovery directory:

```bash
janitor --run-module janitor_ext.migrate --restore /path/to/backup --home /path/to/new-recovery
```

Restoration verifies every checksum before writing, never replaces live files, and reports database dumps separately under `externalArtifacts`. Review the recovered configuration before copying it back. Restore a Honcho database dump with PostgreSQL's `pg_restore` against a separately prepared database; the file restoration command never writes to Docker volumes.

`bash scripts/migrate-janitor-1.0.sh --apply` migrates only the selected profile. Add `--all-profiles` explicitly to migrate its root and all named profiles.
