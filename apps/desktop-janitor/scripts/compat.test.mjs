// F1-21a app↔engine contract (P13): the pure verdict, the boot gate injected
// into main.ts (evaluated with stubbed Electron), and the patches against the
// real apps/desktop. Read-only on apps/desktop.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import module from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import vm from 'node:vm'

import {
  COMPAT_DIALOG,
  FORK_RELEASE_URL,
  compatGateSource,
  compatPatches,
  decideDesktopCompat,
  readDesktopContract
} from '../brand/compat.mjs'
import { STRUCTURAL_PATCHES } from '../brand/patches.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR, runCheck } from './build.mjs'
import { checkPatches, computePatchedFiles } from './patch-engine.mjs'
import { checkTranspiles } from './transpile-check.mjs'

const engineFile = (contract, releaseUrl = FORK_RELEASE_URL) => JSON.stringify({ contract, release_url: releaseUrl })

// ---- pure verdict ---------------------------------------------------------

test('engine contract above, equal to and below the app\'s', () => {
  assert.equal(decideDesktopCompat(3, engineFile(4)).status, 'app_vieja')
  assert.equal(decideDesktopCompat(3, engineFile(3)).status, 'compatible')
  assert.equal(decideDesktopCompat(3, engineFile(2)).status, 'motor_viejo')
  assert.deepEqual(decideDesktopCompat(3, engineFile(4)), {
    status: 'app_vieja',
    appContract: 3,
    engineContract: 4,
    releaseUrl: FORK_RELEASE_URL
  })
})

test('an absent engine file (engine older than the contract) is compatible', () => {
  assert.equal(decideDesktopCompat(1, null).status, 'compatible')
  assert.equal(decideDesktopCompat(1, null).engineContract, null)
})

test('an unreadable engine file never blocks', () => {
  const unreadable = ['', '{not json', '[]', 'null', '42', '{}', '{"contract": "2"}', '{"contract": 1.5}', '{"contract": 0}', '{"contract": -1}']

  for (const raw of unreadable) {
    const verdict = decideDesktopCompat(1, raw)

    assert.equal(verdict.status, 'ilegible', raw)
    assert.equal(verdict.releaseUrl, FORK_RELEASE_URL, raw)
  }

  // A bad baked number cannot block either.
  assert.equal(decideDesktopCompat(0, engineFile(5)).status, 'ilegible')
})

test('release_url is honoured only inside the fork on github.com over https', () => {
  const inside = 'https://github.com/reck74/Janitor-Agent/releases/tag/v0.22.0-janitor.1'

  assert.equal(decideDesktopCompat(1, engineFile(2, inside)).releaseUrl, inside)

  const outside = [
    'https://evil.example/reck74/Janitor-Agent/releases/latest',
    'http://github.com/reck74/Janitor-Agent/releases/latest',
    'https://github.com/NousResearch/hermes-agent/releases/latest',
    'https://github.com/reck74/Janitor-Agent-evil/releases/latest',
    'https://github.com/reck74/Janitor-Agent/../../evil/x',
    'https://github.com:8443/reck74/Janitor-Agent/releases/latest',
    'https://user:pw@github.com/reck74/Janitor-Agent/releases/latest',
    'https://github.com.evil.example/reck74/Janitor-Agent/releases/latest',
    'javascript:alert(1)',
    'file:///etc/passwd',
    'not a url',
    42
  ]

  for (const url of outside) {
    assert.equal(decideDesktopCompat(1, engineFile(2, url)).releaseUrl, FORK_RELEASE_URL, String(url))
  }
})

// ---- the repo's file and the baked number ----------------------------------

test('the build bakes the repo\'s contract; a malformed file stops the build', () => {
  const baked = readDesktopContract()

  assert.ok(Number.isInteger(baked) && baked >= 1)
  assert.equal(decideDesktopCompat(baked, fs.readFileSync(path.join(APP_DIR, '..', '..', 'janitor', 'desktop-compat.json'), 'utf8')).status, 'compatible')

  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-compat-repo-'))

  try {
    fs.mkdirSync(path.join(repo, 'janitor'))

    for (const raw of ['{"contract": "1"}', '{"contract": 0}', '{}', '{broken']) {
      fs.writeFileSync(path.join(repo, 'janitor', 'desktop-compat.json'), raw)
      assert.throws(() => readDesktopContract(repo), undefined, raw)
    }
  } finally {
    fs.rmSync(repo, { recursive: true, force: true })
  }

  assert.throws(() => compatGateSource(0))
  assert.throws(() => compatPatches(1.5))
})

// ---- the boot gate as injected ----------------------------------------------

function loadGate(contract, engineRoot, platform = 'linux') {
  const calls = { dialogs: [], opened: [], quit: 0, openUpdates: 0, logs: [] }
  let onQuit
  const quitCalled = new Promise(resolve => (onQuit = resolve))
  const answer = { response: 0 }

  const context = {
    URL,
    process: { platform },
    fs,
    path,
    resolveUpdateRoot: () => engineRoot,
    rememberLog: line => calls.logs.push(line),
    sendOpenUpdatesRequested: () => (calls.openUpdates += 1),
    dialog: {
      showMessageBox: async options => {
        calls.dialogs.push(options)

        return { response: answer.response }
      }
    },
    shell: {
      openExternal: async url => {
        calls.opened.push(url)
      }
    },
    app: {
      quit: () => {
        calls.quit += 1
        onQuit()
      }
    }
  }

  const js = module.stripTypeScriptTypes(compatGateSource(contract))
  const exported = vm.runInNewContext(`${js}\n;({ janitorDesktopCompatGate })`, context)

  return { calls, quitCalled, answer, gate: exported.janitorDesktopCompatGate }
}

function engineWith(raw) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-compat-engine-'))

  if (raw !== null) {
    fs.mkdirSync(path.join(root, 'janitor'))
    fs.writeFileSync(path.join(root, 'janitor', 'desktop-compat.json'), raw)
  }

  return root
}

test('engine newer than the app: blocking Spanish dialog, download opens, app quits, the gate never lets the backend start', async () => {
  const root = engineWith(engineFile(3, 'https://evil.example/x'))

  try {
    const { calls, quitCalled, gate } = loadGate(2, root)
    let settled = false

    gate().then(
      () => (settled = true),
      () => (settled = true)
    )
    await quitCalled
    await new Promise(resolve => setImmediate(resolve))

    assert.equal(settled, false, 'the gate must stay parked so no backend starts')
    assert.equal(calls.quit, 1)
    assert.equal(calls.dialogs.length, 1)

    const [shown] = calls.dialogs

    assert.equal(shown.message, COMPAT_DIALOG.message)
    assert.ok(shown.detail.startsWith(COMPAT_DIALOG.details.linux))
    assert.ok(shown.detail.endsWith(FORK_RELEASE_URL))
    assert.deepEqual([...shown.buttons], ['Abrir la descarga', 'Salir'])
    assert.equal(shown.cancelId, 1)
    assert.doesNotMatch(JSON.stringify(shown), /Hermes/)
    assert.deepEqual(calls.opened, [FORK_RELEASE_URL], 'an off-fork release_url is never opened')
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

// F6-04d: the update instructions name the file the user downloads on each platform.
test('the blocking dialog tells each platform how to replace the app, in Spanish', async () => {
  const expected = { linux: /AppImage/, win32: /instalador \(\.exe\)/, darwin: /\.dmg[\s\S]*Aplicaciones/, freebsd: /AppImage/ }

  for (const [platform, pattern] of Object.entries(expected)) {
    const root = engineWith(engineFile(3))

    try {
      const { calls, quitCalled, gate } = loadGate(2, root, platform)

      gate()
      await quitCalled

      const [shown] = calls.dialogs

      assert.match(shown.detail, pattern, platform)
      assert.ok(shown.detail.startsWith(COMPAT_DIALOG.details[platform] ?? COMPAT_DIALOG.details.linux), platform)
      assert.ok(shown.detail.endsWith(`\n\n${FORK_RELEASE_URL}`), platform)
      assert.doesNotMatch(shown.detail, /Hermes/)
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  }
})

test('«Salir» quits without opening anything', async () => {
  const root = engineWith(engineFile(9))

  try {
    const { calls, quitCalled, answer, gate } = loadGate(1, root)

    answer.response = 1
    void gate()
    await quitCalled

    assert.deepEqual(calls.opened, [])
    assert.equal(calls.quit, 1)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('compatible, absent or unreadable engine file: the gate passes without a dialog', async () => {
  for (const raw of [engineFile(2), null, '{broken', '{"contract": "x"}']) {
    const root = engineWith(raw)

    try {
      const { calls, gate } = loadGate(2, root)

      await gate()

      assert.deepEqual(calls.dialogs, [], String(raw))
      assert.equal(calls.quit, 0, String(raw))
      assert.equal(calls.openUpdates, 0, String(raw))
    } finally {
      fs.rmSync(root, { recursive: true, force: true })
    }
  }
})

test('engine older than the app: no block, the updates view is requested', async () => {
  const root = engineWith(engineFile(1))

  try {
    const { calls, gate } = loadGate(2, root)

    await gate()

    assert.equal(calls.openUpdates, 1)
    assert.deepEqual(calls.dialogs, [])
    assert.equal(calls.quit, 0)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('F1-26e: the gate also runs after an install; an engine older than the app opens the updates view once', async () => {
  const root = engineWith(engineFile(1))

  try {
    const { calls, gate } = loadGate(2, root)

    await gate() // before the local start
    await gate() // after the install / on a retry: same verdict, acted on already

    assert.equal(calls.openUpdates, 1)
    assert.equal(calls.logs.length, 2, 'both evaluations are logged')
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('F1-26e: before the install the engine is absent; after it, an engine newer than the app blocks once', async () => {
  const root = engineWith(null)

  try {
    const { calls, quitCalled, gate } = loadGate(1, root)

    await gate() // first launch, nothing installed yet: compatible

    assert.deepEqual(calls.dialogs, [])

    fs.mkdirSync(path.join(root, 'janitor'))
    fs.writeFileSync(path.join(root, 'janitor', 'desktop-compat.json'), engineFile(2))

    void gate() // after the install (P13-compat-after-bootstrap)
    void gate() // a concurrent local start while the dialog is up
    await quitCalled
    await new Promise(resolve => setImmediate(resolve))

    assert.equal(calls.dialogs.length, 1, 'never a second dialog')
    assert.equal(calls.quit, 1)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

// ---- patches against the real apps/desktop ----------------------------------

test('P13 patches are registered, exact literals, resolve against apps/desktop and write no "Hermes"', () => {
  const p13 = compatPatches()
  const structural = new Set(STRUCTURAL_PATCHES.map(p => p.id))
  const all = new Set(allPatches().map(p => p.id))

  for (const patch of p13) {
    assert.ok(structural.has(patch.id) && all.has(patch.id), `${patch.id} not registered`)
    assert.equal(typeof patch.find, 'string', patch.id)
    assert.doesNotMatch(patch.replace, /Hermes/, patch.id)
  }

  const { ok, results } = checkPatches(APP_DIR, p13)

  assert.ok(ok, results.map(r => r.error).filter(Boolean).join('\n'))
})

test('build.mjs --check resolves every patch, P13 included', () => {
  const lines = []

  assert.equal(runCheck(APP_DIR, allPatches(), line => lines.push(line)), true, lines.join('\n'))

  for (const patch of compatPatches()) {
    assert.ok(lines.some(line => line.startsWith('ok') && line.endsWith(` ${patch.id}`)), `${patch.id} not reported ok`)
  }
})

test('main.ts with every patch applied still transpiles', t => {
  const mainTs = computePatchedFiles(APP_DIR, allPatches()).get('electron/main.ts').toString('utf8')
  const result = checkTranspiles(mainTs, 'electron/main.ts', APP_DIR)

  if (result.ok === null) return t.skip(result.reason)

  assert.equal(result.ok, true, result.error)
})
