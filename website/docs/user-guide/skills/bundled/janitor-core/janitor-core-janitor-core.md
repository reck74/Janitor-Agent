---
title: "Janitor Core — Clean stale caches and corrupted artifacts from the agent"
sidebar_label: "Janitor Core"
description: "Clean stale caches and corrupted artifacts from the agent"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Core

Clean stale caches and corrupted artifacts from the agent.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-core` |
| Version | `1.0.0` |
| Author | Janitor Agent |
| License | MIT |
| Platforms | linux, macos |
| Tags | `cache-clean`, `security`, `hygiene`, `janitor` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# janitor-core

Cleans stale caches, session artifacts, and corrupted tool data from the Janitor/Hermes
environment. Built for paranoid operators who assume all cached state is suspect.

## Usage

```
/janitor-clean [--dry-run] [--days N]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--dry-run` | List files that would be deleted, without deleting them |
| `--days N` | Only delete entries older than N days (default: from config, 7) |

## Security Notes

- Never deletes files outside `~/.hermes/` cache directories
- Session caches are removed individually, never wholesale
- All deletions are logged to the agent log with full paths
- Tool artifact caches (compressed states, model checkpoints) require `--force` to remove

## Requirements

- `find` utility (Linux/macOS)
- Read access to `~/.hermes/` and its subdirectories
- Write access to delete cache files owned by the current user
