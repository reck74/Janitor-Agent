---
name: janitor-desktop-launcher
description: "Launch the compiled Janitor Desktop AppImage."
version: 1.0.0
platforms: [linux]

metadata:
  hermes:
    tags: [desktop, electron, appimage, launcher]
    category: devops
---

# janitor-desktop-launcher

Launches the already-compiled Janitor Desktop binary (Electron AppImage) that
ships in `apps/desktop/release/`. Use this when you want to open the desktop
app without rebuilding it.

## When to Use

- A `.AppImage` or unpacked Linux binary already exists in
  `apps/desktop/release/` from a prior `npm run dist:linux`.
- You want to launch the desktop UI without paying the build cost again.

If you need to *rebuild* the AppImage first, use `npm run dist:linux` from
`apps/desktop/` directly — this skill only launches existing artifacts.

## Prerequisites

- Linux x86_64 host (AppImage is built against glibc ≥ 2.6.18).
- For headless servers, `xvfb-run` (provides a virtual X display).
- The release artifact must exist. If it does not, run
  `cd apps/desktop && npm run dist:linux` once.
- The AppImage ships via Git LFS in this repo (138 MB exceeds
  GitHub's 100 MB push limit). New clones need `git lfs install`
  on first run before `git pull` to materialize the binary.
  Without LFS the launcher falls back to the unpacked ELF path.

## How to Run

```bash
bash skills/janitor-desktop-launcher/scripts/launch.sh
```

### Flags

| Flag | Effect |
|------|--------|
| `--unpacked` | Run the unpacked binary at `apps/desktop/release/linux-unpacked/janitor` instead of the AppImage. Faster cold start; use during development. |
| `--headless` | Wrap the launch in `xvfb-run` so the app runs on a server with no display. |
| `--background` | Fork and detach so the shell does not block waiting for the GUI. |
| `--version` | Print detected app version and exit. |

### Examples

```bash
# Foreground, AppImage (default)
bash skills/janitor-desktop-launcher/scripts/launch.sh

# Faster: run the unpacked binary
bash skills/janitor-desktop-launcher/scripts/launch.sh --unpacked

# Headless server (CI, VPS)
bash skills/janitor-desktop-launcher/scripts/launch.sh --headless --background

# Just check what version is bundled
bash skills/janitor-desktop-launcher/scripts/launch.sh --version
```

## What the Script Does

1. Resolves the repo root (walks up from its own path).
2. Verifies the requested artifact exists; aborts with a clear error if not.
3. Logs the detected app version (from `apps/desktop/package.json`).
4. Executes the binary with the requested flags, forwarding stdout/stderr.

## Quick Reference

| Artifact | Path |
|----------|------|
| AppImage | `apps/desktop/release/J4nitor-Agent-0.15.1-linux-x86_64.AppImage` |
| Unpacked binary | `apps/desktop/release/linux-unpacked/janitor` |
| Version source | `apps/desktop/package.json` (`name`, `version`) |

## Pitfalls

- **AppImage is x86_64-only.** It will not run on ARM hosts (Raspberry Pi,
  Apple Silicon under Linux). Rebuild with `npm run dist:linux` on the
  target arch if needed.
- **First launch needs network.** The packaged Electron app installs the
  Hermes Agent runtime into `HERMES_HOME` on first boot — same as a CLI
  install. Make sure outbound HTTPS to the install endpoint is reachable.
- **`--background` does not stop the app.** It only detaches from the
  current shell. Kill the process via `pkill janitor` or your process
  manager when done.
- **Do not run as root inside the AppImage.** Electron's `chrome-sandbox`
  refuses to escalate; either run as your normal user or pass
  `--no-sandbox` (not recommended).
- **Binary ships via Git LFS.** End users who clone the repo must run
  `git lfs install` once on the host so `git pull` materializes the
  AppImage. Without LFS, the file appears as a 3-line pointer and the
  launcher errors out with "no AppImage found" — fallback to
  `--unpacked` (still requires `npm run pack` locally) or install LFS.

## Verification

After launch, check that the process is alive:

```bash
pgrep -af 'J4nitor-Agent|janitor' | head
```

Boot logs land in `HERMES_HOME/logs/desktop.log` (defaults to
`~/.janitor/logs/desktop.log` for this fork).