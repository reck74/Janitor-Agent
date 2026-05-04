---
name: janitor-core
description: |
  Janitor core skill — cache cleaning and environment hygiene for Hermes/Janitor agents.
  Removes stale session caches, temp files, and corrupted tool artifacts to keep the
  agent environment clean and secure. Operates with cínico paranoia: assumes all cached
  data is potentially compromised until verified.
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [cache-clean, security, hygiene, janitor]
    category: devops
    config:
      janitor.cache_clean_days:
        description: "Delete cache entries older than N days"
        default: 7
        type: integer
      janitor.dry_run:
        description: "Show what would be deleted without actually deleting"
        default: false
        type: boolean
---

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