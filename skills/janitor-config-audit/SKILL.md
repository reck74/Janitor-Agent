---
name: janitor-config-audit
description: Diffs active config/SOUL against master assets.
version: 1.0.0
license: MIT

metadata:
  author: Janitor Agent
  created: 2026-05-25
  hermes:
    tags: [config, audit, janitor, maintenance]
    category: devops
    related_skills: [janitor-onboarding]
---

# Janitor Config Audit Skill

Compares the user's active configuration files (`config.yaml`, `SOUL.md`) against the bundled master assets shipped with `janitor-core`. Reports differences and can apply updates selectively or in full.

## When to Use

- After upgrading `janitor-core` to ensure the user's config and persona reflect new defaults.
- When the agent detects a schema drift or missing keys in the active `config.yaml`.
- Before troubleshooting behavior that may stem from stale configuration.

## Prerequisites

- Python 3 and the `pyyaml` package (usually already installed by the base environment).
- The `janitor-core` assets must exist at `$JANITOR_HOME/janitor-core/assets/janitor/`.
- If `$JANITOR_HOME` is unset, the script falls back to `~/.janitor`.

## How to Run

```bash
# Show differences only
python skills/janitor-config-audit/scripts/audit.py

# Show differences for a specific file
python skills/janitor-config-audit/scripts/audit.py config
python skills/janitor-config-audit/scripts/audit.py soul

# Apply all updates automatically (backs up originals first)
python skills/janitor-config-audit/scripts/audit.py --apply

# Dry-run (default) — shows diff without writing anything
python skills/janitor-config-audit/scripts/audit.py --dry-run
```

## Quick Reference

| Target | Command |
|---|---|
| Both files (default) | `audit.py` |
| Only `config.yaml` | `audit.py config` |
| Only `SOUL.md` | `audit.py soul` |
| Apply updates | `audit.py --apply` |
| Dry-run (no writes) | `audit.py --dry-run` |

## Procedure

1. The script reads `$JANITOR_HOME` (or falls back to `~/.janitor`).
2. It compares the active file against the matching asset in `janitor-core/assets/janitor/`.
3. For `config.yaml`, it flattens nested dicts and reports added, removed, or changed keys.
4. For `SOUL.md`, it prints a unified text diff.
5. In `--apply` mode, it copies the active file to a `.bak` backup, overwrites it with the asset, and validates the resulting YAML. If validation fails, it restores the backup automatically.

## Pitfalls

- Manual edits to the active `config.yaml` that produce malformed YAML will trigger an automatic restore in `--apply` mode, but the update will not be applied until the YAML is fixed manually.
- `--apply` overwrites the entire active file; there is no key-by-key merge yet. Use the diff output to decide whether to apply.
- Missing assets (e.g., `janitor-core` not installed) result in a hard error rather than a silent skip.

## Verification

After applying `config.yaml`, the script runs `yaml.safe_load()` on the result and reports `[OK] YAML valido tras aplicacion.` If the load fails, the backup is restored and the script exits with code 1.
