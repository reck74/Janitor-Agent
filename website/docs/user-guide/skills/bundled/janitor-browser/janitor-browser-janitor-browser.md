---
title: "Janitor Browser — Install browser automation managed by Janitor PM"
sidebar_label: "Janitor Browser"
description: "Install browser automation managed by Janitor PM"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Browser

Install browser automation managed by Janitor PM.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-browser` |
| Version | `1.0.0` |
| Author | Janitor Agent |
| License | MIT |
| Platforms | linux, macos |
| Tags | `browser`, `automation`, `scraping` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# janitor-browser

Browser automation is explicitly installed after the base Janitor setup:

```bash
bash ~/.janitor/skills/janitor-browser/scripts/install.sh
```

The script enters the owning installation's PM runtime and installs its pinned
`agent-browser`, Chromium, and `cua-driver` packages. It uses the same packages
as the upstream browser tools, preserves PM receipts, and propagates failures.
Use WSL2 on Windows. No host pip environment is modified.

Verify with `janitor pm status`. To opt out of future default installs, use
`janitor pm install --without agent-browser --without cua-driver`; PM owns the
package lifecycle and any retained cache bytes.
