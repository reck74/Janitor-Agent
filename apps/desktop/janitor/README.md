# Janitor Desktop distribution

Janitor uses the stable Hermes Desktop UI and gateway protocol through an isolated
source overlay. `build.mjs` copies the source and lock-pinned dependencies to a
private temporary stage, installs the Janitor identity/bootstrap/update seams,
checks renderer and Electron TypeScript, then builds a Linux AppImage. Upstream
source files are not renamed in the checkout. Failed packaging leaves the live
release untouched; completed outputs are promoted afterwards.

From the repository root:

```bash
npm ci
node apps/desktop/janitor/build.mjs
node apps/desktop/scripts/janitor-smoke.mjs --appimage apps/desktop/release/janitor-desktop-1.0.0-linux-x86_64.AppImage
bash skills/janitor-desktop-launcher/scripts/launch.sh --version
```

`janitor desktop --build-only` prepares dependencies through PM and runs this same
overlay under the checkout/build locks. `janitor desktop --skip-build` opens the
current Janitor AppImage. `build.mjs --build-only --keep-stage` produces a temporary
source stage for development and prints its location. Remove that stage when it
is no longer needed. Release output belongs in the ignored `apps/desktop/release`
directory; native binaries are not committed or stored in Git LFS.

The AppImage contains Electron and the UI, and prepares the Janitor Python runtime
in `JANITOR_HOME/janitor-core` (default `~/.janitor/janitor-core`) on first local
setup. It uses `scripts/janitor` and PM's selected environment. The native setup
window collects MiniMax and either Honcho cloud credentials or the OpenAI key for
local Honcho embeddings. Docker is required. Secrets travel through child
environment variables, never argv or bootstrap event logs. Cancelling the form
starts no installation. Other integrations are explicit optional skills.

The native version is independent of Hermes: `janitor_ext/release.json` records
both. Before distributing an AppImage, its stamped source commit must be
available in the Janitor GitHub fork. Publish a stable `vX.Y.Z` release containing
the architecture-specific AppImage and its generated `.sha256` file. Legacy
four-part tags and prerelease suffixes are rejected by this stable feed.

The updater verifies the fork's asset and hash before closing Desktop, transfers
ownership to a worker, updates the runtime to the same published tag through
`janitor update`, then replaces/reopens the AppImage. The runtime completion uses
the distribution provider in `janitor_ext.desktop`; a native transaction preserves
its independently prepared AppImage. Runtime stderr is drained without storing
arbitrary text in the native result.

Update coordination requires util-linux `flock`. A kernel-held guard protects
owner adoption and recovery; PID, boot identity and token prevent taking over a
live update. The private transaction receipt records phases without credentials.
An interrupted swap restores the previous AppImage; an interrupted runtime step
reports its state as unknown and directs the user to the PM receipt. Reopening
Desktop recovers an abandoned lock and shows the result. Download, runtime,
swap/relaunch failure, handoff, process crash, reboot and secret handling are
covered by `scripts/janitor-desktop.test.mjs`. The AppImage smoke exercises the
actual native identity, MiniMax/Honcho window, cancellation and packaged PTY in a
temporary home; it does not install Docker/Honcho or make paid model calls.

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
