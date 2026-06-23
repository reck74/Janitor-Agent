---
name: janitor-desktop-launcher
description: "Launch the compiled Janitor Desktop AppImage."
version: 1.1.0
platforms: [linux]

metadata:
  hermes:
    tags: [desktop, electron, appimage, launcher]
    category: devops
---

# janitor-desktop-launcher

Launches the already-compiled Janitor Desktop binary (Electron AppImage) that
ships under `apps/desktop/release/`. Resolves the install location across
multiple known layouts so the same script works for end users (`HERMES_HOME`),
developers running from a checkout, and CI/sandbox scenarios.

## When to Use

- An AppImage or unpacked ELF already exists from a prior build or `janitor update`.
- You want to launch the desktop UI without paying the build cost again.

If you need to *rebuild* the AppImage first, use `npm run dist:linux` from
`apps/desktop/` directly — this skill only launches existing artifacts.

## Prerequisites

- Linux x86_64 host (AppImage is built against glibc ≥ 2.6.18).
- For headless servers, `xvfb-run` (provides a virtual X display).
- The release artifact must exist in one of the searched locations.
  If it does not, run `cd apps/desktop && npm run dist:linux` once.
- The AppImage ships via Git LFS in this repo (138 MB exceeds
  GitHub's 100 MB push limit). New clones need `git lfs install`
  on first run before `git pull` to materialize the binary.
  Without LFS the launcher falls back to the unpacked ELF path.

## Path Resolution

The script searches for `apps/desktop/` in the following locations,
in priority order, and uses the first one that contains both
`package.json` and a `release/` directory:

| # | Location | When this matches |
|---|----------|-------------------|
| 1 | `$HERMES_HOME/janitor-core/apps/desktop` | **Default for end users.** `janitor-install.sh` mirrors the repo to `~/.janitor/janitor-core/`, and `janitor update` keeps the AppImage current under `release/`. |
| 2 | `$HERMES_HOME/apps/desktop` | Alternative layout if a future installer drops `janitor-core/` from the path. |
| 3 | Path relative to this script (`../..` from `scripts/launch.sh`) | Developer running from the repo checkout — the same place `npm run dist:linux` produces the binary. |
| 4 | `./apps/desktop` from current working dir | CI / sandbox scenarios where the repo is the CWD. |

`HERMES_HOME` defaults to `$HOME/.janitor` when unset. Use
`HERMES_HOME=/custom/path bash launch.sh` to override.

Run `launch.sh --print-path` to see exactly which path was selected
without launching anything — useful for debugging "wrong binary" reports.

## How to Run

```bash
bash skills/janitor-desktop-launcher/scripts/launch.sh
```

### Flags

| Flag | Effect |
|------|--------|
| `--unpacked` | Run the unpacked binary at `release/linux-unpacked/janitor` instead of the AppImage. Faster cold start; use during development. |
| `--headless` | Wrap the launch in `xvfb-run` so the app runs on a server with no display. |
| `--background` | Fork and detach so the shell does not block waiting for the GUI. |
| `--version` | Print detected app version and exit. |
| `--print-path` | Print the resolved AppImage path and exit. |

### Examples

```bash
# Foreground, AppImage (default) — uses whatever location matches
bash skills/janitor-desktop-launcher/scripts/launch.sh

# Debug: see which binary the launcher picked
bash skills/janitor-desktop-launcher/scripts/launch.sh --print-path

# Custom HERMES_HOME (e.g., multi-profile setup)
HERMES_HOME=/home/me/.janitor-prod bash skills/janitor-desktop-launcher/scripts/launch.sh

# Faster: run the unpacked binary (dev only)
bash skills/janitor-desktop-launcher/scripts/launch.sh --unpacked

# Headless server (CI, VPS)
bash skills/janitor-desktop-launcher/scripts/launch.sh --headless --background

# Just check what version is bundled
bash skills/janitor-desktop-launcher/scripts/launch.sh --version
```

## What the Script Does

1. Walks the candidate list above, picks the first one with `package.json` and `release/`.
2. Reads the app version from `<selected>/apps/desktop/package.json`.
3. Locates the AppImage (or `--unpacked` ELF) under that tree.
4. `chmod +x` the AppImage if needed (the LFS pointer replacement can land as non-executable).
5. Optionally wraps in `xvfb-run` (`--headless`) and/or `nohup` (`--background`).
6. `exec`s the binary.

## Quick Reference

| Artifact | Path (relative to resolved apps/desktop) |
|----------|----------|
| AppImage | `release/J4nitor-Agent-0.15.1-linux-x86_64.AppImage` |
| Unpacked binary | `release/linux-unpacked/janitor` |
| Version source | `package.json` (`name`, `version`) |

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
- **Path resolution is file-based, not registry-based.** The script does
  not call into Janitor or Hermes to ask "where is the install?" — it
  reads the filesystem. If you reorganize Janitor's directory layout in
  the future, update the `CANDIDATES` array at the top of `launch.sh`.

## Verification

After launch, check that the process is alive:

```bash
pgrep -af 'J4nitor-Agent|janitor' | head
```

Boot logs land in `HERMES_HOME/logs/desktop.log` (defaults to
`~/.janitor/logs/desktop.log` for this fork).