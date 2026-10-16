---
name: janitor-browser
description: "Install browser automation managed by Janitor PM."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [browser, automation, scraping]
    category: devops
---

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
