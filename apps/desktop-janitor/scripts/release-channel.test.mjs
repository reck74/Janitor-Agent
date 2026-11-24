// F1-28 release-channel patches (P19): the app installs and updates along the
// release channel (janitor/release_channel.py), never along main. Behaviour of
// the patched sources, evaluated in memory / against temp copies; read-only on
// apps/desktop.

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import vm from 'node:vm'

import { REPO_ROOT, RELEASE_CHANNEL_PATCHES, healedBranchSource, readReleaseBranch } from '../brand/release-channel.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'

const patched = computePatchedFiles(APP_DIR, allPatches())
const text = file => {
  assert.ok(patched.has(file), `${file} is not patched`)

  return patched.get(file).toString('utf8')
}

const channel = readReleaseBranch()

test('the build reads the same channel Python does (janitor/release_channel.py)', t => {
  const python = spawnSync(
    'python3',
    ['-I', '-c', 'import runpy, sys; print(runpy.run_path(sys.argv[1])["RELEASE_BRANCH"])', path.join(REPO_ROOT, 'janitor', 'release_channel.py')],
    { encoding: 'utf8' }
  )

  if (python.error) {
    t.skip('python3 not available')

    return
  }

  assert.equal(python.status, 0, python.stderr)
  assert.equal(python.stdout.trim(), channel)
  assert.notEqual(channel, 'main')

  for (const patch of RELEASE_CHANNEL_PATCHES) {
    assert.ok(patch.id.startsWith('P19-'), patch.id)
  }
})

/** The patched main.ts's DEFAULT_UPDATE_BRANCH and resolveHealedBranch, run against fakes. */
function loadHealedBranch({ probeCode, configBranch }) {
  const main = text('electron/main.ts')
  const constLine = main.match(/^const DEFAULT_UPDATE_BRANCH = .*$/m)[0]
  const fn = healedBranchSource()

  // What ships is exactly the tested function, once.
  assert.equal(main.split(fn).length - 1, 1, 'patched resolveHealedBranch not found verbatim in main.ts')

  const calls = { git: [], writes: [] }
  const context = vm.createContext({
    OFFICIAL_REPO_HTTPS_URL: 'https://example.invalid/official.git',
    getOriginUrl: async () => 'https://github.com/reck74/Janitor-Agent.git',
    isOfficialSshRemote: () => false,
    runGit: async args => {
      calls.git.push(args)

      return { code: probeCode, stdout: '', stderr: '' }
    },
    rememberLog: () => {},
    readDesktopUpdateConfig: () => ({ branch: configBranch }),
    writeDesktopUpdateConfig: config => calls.writes.push(config)
  })

  vm.runInContext(`${constLine.replace(/^const /, 'var ')}\n${fn}\nthis.resolveHealedBranch = resolveHealedBranch`, context)

  return { resolve: context.resolveHealedBranch, calls, defaultBranch: context.DEFAULT_UPDATE_BRANCH }
}

test('an install on the channel stays on it, and a branch gone from origin heals to the channel, not main', async () => {
  const onChannel = loadHealedBranch({ probeCode: 2, configBranch: channel })

  assert.equal(onChannel.defaultBranch, channel)
  assert.equal(await onChannel.resolve('/engine', channel), channel)
  assert.equal(await onChannel.resolve('/engine', ''), channel)
  assert.equal(onChannel.calls.git.length, 0, 'the channel itself is never probed')

  const gone = loadHealedBranch({ probeCode: 2, configBranch: 'feature/gone' })

  assert.equal(await gone.resolve('/engine', 'feature/gone'), channel)
  assert.deepEqual(gone.calls.writes.map(config => config.branch), [channel])

  // A developer's branch origin still publishes, and a network error (exit 128), keep the branch.
  for (const probeCode of [0, 128]) {
    const kept = loadHealedBranch({ probeCode, configBranch: 'janitor-app/dev' })

    assert.equal(await kept.resolve('/engine', 'janitor-app/dev'), 'janitor-app/dev')
    assert.equal(kept.calls.writes.length, 0)
  }
})

test('a non-git build stamps the channel as the install branch', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-stamp-'))

  try {
    fs.copyFileSync(path.join(APP_DIR, 'scripts', 'utils.mjs'), path.join(dir, 'utils.mjs'))
    fs.writeFileSync(path.join(dir, 'write-build-stamp.mjs'), text('scripts/write-build-stamp.mjs'))

    const stamp = await import(pathToFileURL(path.join(dir, 'write-build-stamp.mjs')).href)
    const resolved = stamp.resolveStamp({ env: {}, execFn: () => null, repoRoot: dir })

    assert.equal(resolved.source, 'fallback')
    assert.equal(resolved.branch, channel)
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
