---
name: janitor-browser
description: "Install Playwright browser automation for Janitor."
version: 1.0.0
platforms: [linux, macos, win32]

metadata:
  hermes:
    tags: [browser, playwright, automation, scraping]
    category: devops
---

# janitor-browser

Install Playwright browser automation tools for Janitor. Optional — only needed
if you want browser automation capabilities (scraping JavaScript-heavy sites,
taking screenshots, etc.).

## Prerequisites

- Python 3.11+ with `uv` or `pip`
- `apt-get` available on Debian/Ubuntu for system dependencies

## Usage

```bash
bash skills/janitor-browser/scripts/install.sh
```

## What Gets Installed

- Python package `playwright`
- Chromium browser binary and system dependencies

## Verification

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

## Rollback

```bash
uv pip uninstall playwright
# Or: pip uninstall playwright
```

System dependencies installed via `apt-get` are not automatically removed.
