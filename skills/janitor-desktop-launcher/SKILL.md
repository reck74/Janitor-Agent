---
name: janitor-desktop-launcher
description: "Build or launch the Janitor Agent Linux desktop AppImage."
version: 2.0.1
author: Janitor Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [desktop, electron, appimage, launcher]
    category: devops
---

# Janitor Desktop

Janitor retains the upstream Electron interface and builds its own identity and
runtime adapters in a temporary source tree. Upstream source files remain intact.
The AppImage prepares the Janitor runtime on first launch; configuration requires
MiniMax and a local or cloud Honcho connection. Other integrations are opt-in.

## Build

Install the locked root workspace dependencies with `npm ci`, then run:

```bash
node apps/desktop/janitor/build.mjs
```

Artifacts, their SHA-256 sidecars, and `janitor-release.json` are written to
`apps/desktop/release/`. Publish these files together in the fork's GitHub release;
binaries are not committed to Git or Git LFS. Native Janitor versions use stable
SemVer independently of the recorded upstream engine version.

## Launch

```bash
bash skills/janitor-desktop-launcher/scripts/launch.sh
```

`HERMES_HOME` selects an explicit profile before `JANITOR_HOME`, then defaults to `~/.janitor`.
Both variables are passed to the application. The launcher checks the installed
runtime's build, the checkout beside this skill, and the current checkout. It
skips incomplete candidates and chooses the newest matching architecture.
`JANITOR_DESKTOP_DIR` explicitly selects one `apps/desktop` directory.

Flags:

- `--unpacked`: use `release/linux-unpacked/janitor-desktop`.
- `--print-path`: print the selected artifact without executing or chmodding it.
- `--version`: print the selected build's metadata without starting Electron.
- `--headless`: launch through `xvfb-run`.
- `--background`: detach the process and print its PID.
- `-- APP_ARGS`: pass explicit arguments to Electron.

The AppImage updater uses stable GitHub releases from `reck74/Janitor-Agent`,
requires matching SHA-256 assets, updates runtime through `scripts/janitor`, and
replaces/relaunches the AppImage only after successful verification and runtime
update. A package managed outside the writable AppImage path requires its owner
to update it. Failures preserve the previous AppImage and are recorded privately
under `JANITOR_HOME/.janitor-desktop-update-result.json`.

Boot logs are under `JANITOR_HOME/logs/desktop.log`. A missing runtime or setup
credential is surfaced by the existing setup/retry interface. Do not disable the
Electron sandbox as an installation workaround.

Release builds require a clean, completed Git checkout and verify that the exact
commit's Janitor bootstrap is publicly available from the fork. They refuse
dirty sources, unfinished merges and unpublished/mismatched bootstrap bytes.
For local development use `node apps/desktop/janitor/build.mjs --development`;
this writes a `-dev.<commit>` product into `release-development/`, never a stable
release artifact. Development builds are not distribution candidates.

`janitor-desktop-linux.yml` builds and smokes the actual Janitor source overlay.
A manual candidate publication additionally requires full sync/E2E acceptance
and accepts only `vX.Y.Z-rc.N` tags. It cannot publish a stable release.
The updater confirms the new product/version and loaded renderer, watches for
premature exit, and rolls the AppImage back if that handshake fails. Runtime
success is reported separately when Desktop rollback is necessary.
