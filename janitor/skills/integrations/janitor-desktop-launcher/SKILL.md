---
name: janitor-desktop-launcher
description: "Launch Janitor Desktop against the Janitor home."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [desktop, electron, appimage, launcher]
    category: devops
---

# janitor-desktop-launcher Skill

Starts the Janitor Desktop app (Electron AppImage) with `HERMES_HOME` set to the
Janitor home, so it shares config, sessions and skills with the `janitor` CLI.
Uses a local build when one exists, otherwise downloads the latest release of
the fork. It does not build the app.

## When to Use

- The user wants the desktop UI for their Janitor agent.
- A desktop build was just produced and needs a smoke launch.

## Prerequisites

- Linux x86_64 (the AppImage is x86_64-only).
- `curl` and `python3` for the release download.
- `xvfb-run` only for `--headless`.

## How to Run

```bash
bash ${HERMES_SKILL_DIR}/scripts/launch.sh
```

## Quick Reference

| Flag | Effect |
|------|--------|
| `--download` | Fetch the latest release even if a local AppImage exists |
| `--repo owner/name` | Release source (default `reck74/Janitor-Agent`) |
| `--unpacked` | Run `apps/desktop/release/linux-unpacked/Janitor` (local build) |
| `--headless` | Wrap in `xvfb-run` |
| `--background` | Detach from the shell |
| `--print-path` | Print the resolved binary and exit |

AppImage lookup order: `<install tree>/apps/desktop/release/Janitor-*-linux-x86_64.AppImage`,
then `$HERMES_HOME/desktop/` (previous downloads), then the latest GitHub release.

## Procedure

1. Run `launch.sh --print-path` with `terminal` to see which binary will be used.
2. Launch with `launch.sh` (or `--background` when the shell must stay free).
3. To build locally instead of downloading, from the install tree run
   `node apps/desktop-janitor/scripts/build.mjs --linux AppImage`. The build
   overlays Janitor branding on the upstream `apps/desktop` and restores it after.

## Pitfalls

- Desktop settings (window state, connection) live in Electron's userData
  directory, which keeps the upstream name so earlier Janitor desktop installs
  keep their settings. Agent data always lives in `HERMES_HOME`.
- Do not run as root: Electron's `chrome-sandbox` refuses to escalate.
- `--background` only detaches; stop the app from its window or with `kill`.

## Verification

`launch.sh --print-path` prints an existing path, and after launch the app's
logs appear under `$HERMES_HOME/logs/desktop.log`.
