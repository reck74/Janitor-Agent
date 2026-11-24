// P19 (task F1-28, plan decision 2.10): the Janitor app follows the release
// channel, not `main`.
//
// Users receive tagged versions only. The release workflow fast-forwards the
// `stable` branch to every published `v…` tag, and everything that installs or
// updates follows that branch. Its name lives in janitor/release_channel.py
// (RELEASE_BRANCH); the build reads it from there, so there is one source of
// truth for the engine and the app.
//
// Upstream's updater keeps the branch the checkout is on (a `stable` install
// stays on `stable`, a developer's branch stays on that branch) and only
// "heals" a branch origin no longer publishes. Upstream heals to `main`; the
// Janitor build heals to the channel, and the defaults (no updates.json, no
// stamp branch) are the channel as well.
//
// resolveHealedBranch is injected into main.ts as its own source text
// (Function#toString), so the tested function is byte-for-byte what ships. It
// may only use main.ts module-scope names: DEFAULT_UPDATE_BRANCH, getOriginUrl,
// isOfficialSshRemote, OFFICIAL_REPO_HTTPS_URL, runGit, rememberLog,
// readDesktopUpdateConfig, writeDesktopUpdateConfig.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
export const RELEASE_CHANNEL_FILE = path.join('janitor', 'release_channel.py')

const BRANCH_RE = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/

/** RELEASE_BRANCH from janitor/release_channel.py (one `RELEASE_BRANCH = "…"` line). */
export function readReleaseBranch(repoRoot = REPO_ROOT) {
  const file = path.join(repoRoot, RELEASE_CHANNEL_FILE)
  const matches = [...fs.readFileSync(file, 'utf8').matchAll(/^RELEASE_BRANCH\s*=\s*["']([^"'\n]+)["']\s*$/gm)]

  if (matches.length !== 1) {
    throw new Error(`${file}: expected exactly one RELEASE_BRANCH = "<branch>" line, found ${matches.length}`)
  }

  const branch = matches[0][1]

  if (!BRANCH_RE.test(branch) || branch.includes('..')) {
    throw new Error(`${file}: RELEASE_BRANCH ${JSON.stringify(branch)} is not a plain branch name`)
  }

  return branch
}

// Self-heal the tracked update branch (Janitor build, P19): a branch origin
// still publishes is kept (the checkout's own branch, `stable` or a developer's
// branch); one origin definitively no longer has (ls-remote exit 2) falls back
// to the release channel and is persisted. A network error never flips it.
export async function resolveHealedBranch(updateRoot, branch) {
  if (!branch || branch === DEFAULT_UPDATE_BRANCH) {
    return branch || DEFAULT_UPDATE_BRANCH
  }

  const originUrl = await getOriginUrl(updateRoot)
  const remote = isOfficialSshRemote(originUrl) ? OFFICIAL_REPO_HTTPS_URL : 'origin'
  const probe = await runGit(['ls-remote', '--exit-code', '--heads', remote, branch], { cwd: updateRoot })

  if (probe.code !== 2) {
    return branch
  }

  rememberLog(`[updates] origin/${branch} is gone; falling back to the release channel ${DEFAULT_UPDATE_BRANCH}`)
  const config = readDesktopUpdateConfig()

  if (config.branch !== DEFAULT_UPDATE_BRANCH) {
    writeDesktopUpdateConfig({ ...config, branch: DEFAULT_UPDATE_BRANCH })
  }

  return DEFAULT_UPDATE_BRANCH
}

// Upstream's function and its comment, verbatim: the anchor P19 replaces.
const UPSTREAM_HEALED_BRANCH = `// Self-heal the tracked update branch: if origin no longer publishes it (e.g.
// bb/gui was merged into main and deleted), fall back to main and persist so
// every later check/apply follows main — no manual flip, even for already-
// installed clients. Read-only ls-remote probe; only flips on a definitive
// "ref absent" (exit 2), never on a transient network error, so a flaky
// connection can't strand a user on the wrong branch.
async function resolveHealedBranch(updateRoot, branch) {
  if (!branch || branch === 'main') {
    return branch || 'main'
  }

  const originUrl = await getOriginUrl(updateRoot)
  const remote = isOfficialSshRemote(originUrl) ? OFFICIAL_REPO_HTTPS_URL : 'origin'
  const probe = await runGit(['ls-remote', '--exit-code', '--heads', remote, branch], { cwd: updateRoot })

  if (probe.code !== 2) {
    return branch
  }

  rememberLog(\`[updates] origin/\${branch} is gone (merged?); falling back to main\`)
  const config = readDesktopUpdateConfig()

  if (config.branch !== 'main') {
    writeDesktopUpdateConfig({ ...config, branch: 'main' })
  }

  return 'main'
}
`

export function healedBranchSource() {
  return [
    '// Janitor build (P19, apps/desktop-janitor/brand/release-channel.mjs): a branch origin',
    '// no longer publishes falls back to the release channel, never to main.',
    resolveHealedBranch.toString(),
    ''
  ].join('\n')
}

export function releaseChannelPatches(branch = readReleaseBranch()) {
  // readReleaseBranch guarantees a plain branch name: no quote can appear.
  const quoted = `'${branch}'`

  return [
    {
      id: 'P19-default-update-branch',
      purpose: `Self-update default branch (no updates.json, branch reset): main → ${branch} (janitor/release_channel.py)`,
      file: 'electron/main.ts',
      find: "const DEFAULT_UPDATE_BRANCH = 'main'\n",
      replace: `const DEFAULT_UPDATE_BRANCH = ${quoted} // Janitor build (P19): the release channel, janitor/release_channel.py\n`,
      count: 1
    },
    {
      id: 'P19-healed-branch',
      purpose: 'resolveHealedBranch: the channel is never probed; a branch gone from origin falls back to the channel',
      file: 'electron/main.ts',
      find: UPSTREAM_HEALED_BRANCH,
      replace: healedBranchSource(),
      count: 1
    },
    {
      id: 'P19-manual-command-branch',
      purpose: 'Manual update command (CLI install without staged updater): bare only on the channel, --branch otherwise',
      file: 'electron/main.ts',
      find: "            if (branch !== 'main') {\n              command = `hermes update --branch ${branch}`",
      replace: '            if (branch !== DEFAULT_UPDATE_BRANCH) {\n              command = `hermes update --branch ${branch}`',
      count: 1
    },
    {
      id: 'P19-posix-handoff-branch',
      purpose: 'POSIX update hand-off: a detached HEAD (no branch) updates along the channel, not main',
      file: 'electron/main.ts',
      find: '  // self-heal to main when the pinned branch no longer exists on origin).\n  let branch = \'main\'\n',
      replace:
        '  // self-heal to the release channel when the pinned branch no longer exists on origin; Janitor P19).\n' +
        '  let branch = DEFAULT_UPDATE_BRANCH\n',
      count: 1
    },
    {
      id: 'P19-bootstrap-fallback-branch',
      purpose: `First-run install from a non-git build (all-zero stamp, no branch): fetch install.sh from ${branch}, not main`,
      file: 'electron/bootstrap-runner.ts',
      find: "const FALLBACK_BRANCH = 'main'\n",
      replace: `const FALLBACK_BRANCH = ${quoted} // Janitor build (P19): the release channel\n`,
      count: 1
    },
    {
      id: 'P19-stamp-fallback-branch',
      purpose: `install-stamp.json of a non-git build: branch ${branch}, not main`,
      file: 'scripts/write-build-stamp.mjs',
      find: 'export const FALLBACK_BRANCH = "main"\n',
      replace: `export const FALLBACK_BRANCH = ${quoted} // Janitor build (P19): the release channel\n`,
      count: 1
    },
    {
      id: 'P19-backend-behind-label',
      purpose: `Backend version tooltip: "N commits detrás de ${branch}" (the engine's update probe follows the channel)`,
      file: 'src/lib/version-status.ts',
      find: "copy.commitsBehind(behind, (client ? branch : 'main') || '...')",
      replace: `copy.commitsBehind(behind, (client ? branch : ${quoted}) || '...')`,
      count: 1
    }
  ]
}

export const RELEASE_CHANNEL_PATCHES = releaseChannelPatches()
