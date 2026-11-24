// F1-26 (first real install): P15 boot wait during an install, P16 probe home,
// P17 Spanish stage labels. The injected code is evaluated as shipped (after
// type stripping); read-only on apps/desktop.

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import module from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import vm from 'node:vm'

import {
  BOOT_TIMEOUT_ES,
  INSTALL_BOOT_PATCHES,
  RECONNECT_TIMEOUT_ES,
  bootWaitSource,
  janitorBootWaitVerdict,
  janitorRetryBootAfterInstall,
  janitorStageLabel
} from '../brand/install-boot.mjs'
import { STRUCTURAL_PATCHES } from '../brand/patches.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { checkPatches, computePatchedFiles } from './patch-engine.mjs'

const REPO_ROOT = path.resolve(APP_DIR, '..', '..')
const BUDGET = 45_000
const NOW = 1_000_000

const snapshot = overrides => ({
  active: false,
  manifest: null,
  stages: {},
  error: null,
  log: [],
  startedAt: null,
  completedAt: null,
  setupChoice: null,
  unsupportedPlatform: null,
  ...overrides
})

// ---- (a) is the boot failure shown? -----------------------------------------

test('boot wait: an install running, a pending setup choice or a fresh install keep waiting', () => {
  const cases = [
    [snapshot({ active: true, startedAt: NOW - 200_000 }), 'instalando'],
    [snapshot({ setupChoice: { platform: 'linux', activeRoot: '/x' } }), 'eligiendo'],
    [snapshot({ completedAt: NOW - 1_000 }), 'recien-instalado']
  ]

  for (const [state, reason] of cases) {
    assert.deepEqual(janitorBootWaitVerdict(state, NOW, BUDGET), { wait: true, reason })
  }
})

test('boot wait: without an install, after a failed one or an old one, the failure is real', () => {
  const cases = [
    [null, 'sin-estado'],
    [undefined, 'sin-estado'],
    [snapshot(), 'sin-instalacion'],
    [snapshot({ completedAt: NOW - BUDGET }), 'sin-instalacion'],
    [snapshot({ error: 'Falló la etapa repository' }), 'instalacion-fallida'],
    [snapshot({ active: true, error: 'x' }), 'instalacion-fallida']
  ]

  for (const [state, reason] of cases) {
    assert.deepEqual(janitorBootWaitVerdict(state, NOW, BUDGET), { wait: false, reason }, String(reason))
  }
})

test('a latched boot failure re-runs only on a completed install of an unfinished, current boot', () => {
  const latched = { bootFailed: true, bootCompleted: false, cancelled: false, switching: false }

  assert.equal(janitorRetryBootAfterInstall('complete', latched), true)

  for (const type of ['manifest', 'stage', 'log', 'failed', 'setup-choice', 'dismissed', undefined]) {
    assert.equal(janitorRetryBootAfterInstall(type, latched), false, String(type))
  }

  assert.equal(janitorRetryBootAfterInstall('complete', { ...latched, bootFailed: false }), false, 'boot still in flight')
  assert.equal(janitorRetryBootAfterInstall('complete', { ...latched, bootCompleted: true }), false, 'boot already done')
  assert.equal(janitorRetryBootAfterInstall('complete', { ...latched, cancelled: true }), false, 'unmounted')
  assert.equal(janitorRetryBootAfterInstall('complete', { ...latched, switching: true }), false, 'connection switch')
  assert.equal(janitorRetryBootAfterInstall('complete', null), false)
})

// The injected module-level code, run against a stubbed withTimeout/bridge.
function loadBootWait(getBootstrapState) {
  class TimeoutError extends Error {
    constructor(message) {
      super(message)
      this.name = 'TimeoutError'
    }
  }

  const withTimeout = (promise, ms, message) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new TimeoutError(message)), ms)

      Promise.resolve(promise).then(
        value => {
          clearTimeout(timer)
          resolve(value)
        },
        error => {
          clearTimeout(timer)
          reject(error)
        }
      )
    })

  const context = {
    Date,
    Number,
    Object,
    Promise,
    setTimeout,
    clearTimeout,
    withTimeout,
    RECONNECT_ATTEMPT_TIMEOUT_MS: 50,
    window: { hermesDesktop: getBootstrapState === undefined ? undefined : { getBootstrapState } }
  }

  const js = module.stripTypeScriptTypes(bootWaitSource())

  return vm.runInNewContext(`${js}\n;({ janitorAwaitBackend })`, context).janitorAwaitBackend
}

const later = (ms, value) => new Promise(resolve => setTimeout(() => resolve(value), ms))

test('injected boot wait: a backend that arrives after a long install connects, no failure', async () => {
  let installing = true
  const awaitBackend = loadBootWait(async () => snapshot({ active: installing }))
  const backend = later(120, 'conn').then(value => {
    installing = false

    return value
  })

  assert.equal(await awaitBackend(backend, 20, BOOT_TIMEOUT_ES), 'conn', 'six budgets elapse, the install keeps the wait open')
  assert.equal(installing, false)
})

test('injected boot wait: right after the install the backend gets a fresh budget', async () => {
  const awaitBackend = loadBootWait(async () => snapshot({ completedAt: Date.now() }))

  assert.equal(await awaitBackend(later(30, 'conn'), 20, BOOT_TIMEOUT_ES), 'conn')
})

test('injected boot wait: with no install (or an unreadable bridge) the timeout fails as upstream', async () => {
  const bridges = [
    async () => snapshot(),
    async () => snapshot({ error: 'instalación fallida' }),
    async () => {
      throw new Error('ipc down')
    },
    () => new Promise(() => {}), // wedged IPC: bounded by RECONNECT_ATTEMPT_TIMEOUT_MS
    undefined // no bridge at all
  ]

  for (const bridge of bridges) {
    const awaitBackend = loadBootWait(bridge)

    await assert.rejects(awaitBackend(new Promise(() => {}), 20, BOOT_TIMEOUT_ES), error => {
      assert.equal(error.name, 'TimeoutError')
      assert.equal(error.message, BOOT_TIMEOUT_ES)

      return true
    })
  }
})

test('injected boot wait: a real connection error is not swallowed', async () => {
  const awaitBackend = loadBootWait(async () => snapshot({ active: true }))

  await assert.rejects(awaitBackend(Promise.reject(new Error('backend exited')), 20, BOOT_TIMEOUT_ES), /backend exited/)
})

test('patched classifier: the Spanish timeouts still read as «no respondió a tiempo»', async () => {
  const source = computePatchedFiles(APP_DIR, allPatches()).get('src/components/boot-failure-cause.ts').toString('utf8')
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-cause-'))

  try {
    const file = path.join(dir, 'boot-failure-cause.mjs')

    fs.writeFileSync(file, module.stripTypeScriptTypes(source))

    const { classifyLocalBootFailure } = await import(pathToFileURL(file).href)

    assert.equal(classifyLocalBootFailure(BOOT_TIMEOUT_ES), 'timedOut')
    assert.equal(classifyLocalBootFailure(RECONNECT_TIMEOUT_ES), 'timedOut')
    assert.equal(classifyLocalBootFailure('Timed out connecting to Hermes backend after 45000ms'), 'timedOut')
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

// ---- (b) every runtime probe carries HERMES_HOME -----------------------------

async function loadPatchedProbes() {
  const source = computePatchedFiles(APP_DIR, allPatches()).get('electron/backend-probes.ts').toString('utf8')
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-probes-'))
  const file = path.join(dir, 'backend-probes.mjs')

  fs.writeFileSync(file, module.stripTypeScriptTypes(source))

  return { dir, probes: await import(pathToFileURL(file).href) }
}

function recorder(dir, name) {
  const out = path.join(dir, `${name}.env`)
  const script = path.join(dir, name)

  // Stands in for the engine's python / hermes: records the environment it got.
  fs.writeFileSync(script, `#!/bin/sh\nprintf '%s|%s' "$HERMES_HOME" "$PYTHONPATH" > '${out}'\nexit 0\n`, { mode: 0o755 })

  return { script, read: () => fs.readFileSync(out, 'utf8').split('|') }
}

test('patched probes: the import probe and the --version probe run with the Janitor home', async t => {
  if (process.platform === 'win32') return t.skip('POSIX recorder script')

  const { dir, probes } = await loadPatchedProbes()
  const saved = process.env.HERMES_HOME

  try {
    delete process.env.HERMES_HOME
    const home = path.join(dir, 'home', '.janitor')
    probes.janitorSetProbeHermesHome(home)

    const python = recorder(dir, 'python')

    assert.equal(await probes.canImportHermesCli(python.script, { env: { PYTHONPATH: '/engine' } }), true)
    assert.deepEqual(python.read(), [home, '/engine'], 'HERMES_HOME added, caller env kept')

    assert.equal(await probes.canImportHermesCli(python.script), true)
    assert.equal(python.read()[0], home, 'call site without env (system-Python rung)')

    const hermes = recorder(dir, 'hermes')

    assert.equal(await probes.verifyHermesCli(hermes.script), true)
    assert.equal(hermes.read()[0], home)
  } finally {
    if (saved === undefined) delete process.env.HERMES_HOME
    else process.env.HERMES_HOME = saved

    fs.rmSync(dir, { recursive: true, force: true })
  }
})

// ---- (d) every installer stage has a Spanish label --------------------------

test('every stage of the fork installer manifest has a Spanish label', t => {
  if (process.platform === 'win32') return t.skip('install.sh needs bash')

  const run = spawnSync('bash', [path.join(REPO_ROOT, 'scripts', 'install.sh'), '--manifest'], {
    encoding: 'utf8',
    timeout: 30_000
  })

  assert.equal(run.status, 0, run.stderr)

  const { stages } = JSON.parse(run.stdout)

  assert.ok(stages.length > 0)

  for (const { name } of stages) {
    const label = janitorStageLabel(name)

    assert.ok(label, `stage "${name}" has no Spanish label (brand/install-boot.mjs janitorStageLabel)`)
    assert.doesNotMatch(label, /Hermes/, name)
  }
})

test('an unknown stage falls back to upstream formatting', () => {
  assert.equal(janitorStageLabel('etapa-nueva'), null)
  assert.equal(janitorStageLabel('constructor'), null)
  assert.equal(janitorStageLabel('__proto__'), null)
})

// ---- the patches against the real apps/desktop ------------------------------

test('F1-26 patches are registered and resolve against apps/desktop; their visible text is Spanish', () => {
  const structural = new Set(STRUCTURAL_PATCHES.map(p => p.id))
  const all = new Set(allPatches().map(p => p.id))

  for (const patch of INSTALL_BOOT_PATCHES) {
    assert.ok(structural.has(patch.id) && all.has(patch.id), `${patch.id} not registered`)
  }

  const { ok, results } = checkPatches(APP_DIR, allPatches())

  assert.ok(ok, results.map(r => r.error).filter(Boolean).join('\n'))
  assert.doesNotMatch(BOOT_TIMEOUT_ES + RECONNECT_TIMEOUT_ES, /Hermes|timed out/i)
})
