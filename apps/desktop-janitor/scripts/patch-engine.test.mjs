// Patch engine + journal tests. Read the real apps/desktop sources, write only
// in temp dirs.

import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR, OVERLAY_FILES, applyOverlay } from './build.mjs'
import {
  applyPatch,
  beginTransaction,
  checkPatches,
  computePatchedFiles,
  readJournal,
  restoreJournal
} from './patch-engine.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))

const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')

/** Temp copy of every apps/desktop file the build touches. */
function tempAppCopy() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-patch-app-'))
  const targets = new Set(allPatches().map(p => p.file))

  for (const [, target] of OVERLAY_FILES) {
    if (fs.existsSync(path.join(APP_DIR, target))) targets.add(target)
  }

  for (const target of targets) {
    fs.mkdirSync(path.dirname(path.join(dir, target)), { recursive: true })
    fs.copyFileSync(path.join(APP_DIR, target), path.join(dir, target))
  }

  fs.mkdirSync(path.join(dir, 'assets'), { recursive: true })

  return dir
}

function snapshot(dir) {
  const out = {}

  const visit = current => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name)

      if (entry.isDirectory()) visit(full)
      else out[path.relative(dir, full).split(path.sep).join('/')] = sha(full)
    }
  }

  visit(dir)

  return out
}

test('an anchor that is missing fails with the patch id and file', () => {
  const patch = { id: 'PX-demo', file: 'electron/demo.ts', find: 'not here', replace: 'x', count: 1 }

  assert.throws(() => applyPatch('some text', patch), /\[patch PX-demo\] electron\/demo\.ts: anchor "not here" matched 0 time\(s\), expected 1/)
})

test('an anchor matching a different number of times fails instead of patching', () => {
  const patch = { id: 'PX-count', file: 'a.ts', find: 'Hermes', replace: 'Janitor', count: 1 }

  assert.throws(() => applyPatch('Hermes and Hermes', patch), /PX-count.*matched 2 time\(s\), expected 1/)
  assert.equal(applyPatch('Hermes and Hermes', { ...patch, count: 2 }), 'Janitor and Janitor')
})

test('regex anchors must be global and are counted', () => {
  assert.throws(() => applyPatch('a', { id: 'PX-re', file: 'a.ts', find: /a/, replace: 'b', count: 1 }), /must use the g flag/)
  assert.equal(applyPatch('a1 a2', { id: 'PX-re', file: 'a.ts', find: /a(\d)/g, replace: 'b$1', count: 2 }), 'b1 b2')
})

test('a failing anchor aborts the build before any file is written', () => {
  const appDir = tempAppCopy()
  const before = snapshot(appDir)
  const broken = [...allPatches(), { id: 'PX-drift', file: 'electron/main.ts', find: 'upstream removed this', replace: '', count: 1 }]

  assert.throws(() => applyOverlay(appDir, undefined, { patches: broken }), /1 build patch\(es\) failed:\n {2}\[patch PX-drift\] electron\/main\.ts/)
  assert.deepEqual(snapshot(appDir), before)
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('checkPatches reports every failure and writes nothing', () => {
  const appDir = tempAppCopy()
  const before = snapshot(appDir)
  fs.writeFileSync(path.join(appDir, 'src/i18n/languages.ts'), 'export const DEFAULT_LOCALE = "fr"\n')

  const { ok, results } = checkPatches(appDir, allPatches())
  const failed = results.filter(r => !r.ok)

  assert.equal(ok, false)
  assert.deepEqual(
    failed.map(r => r.id),
    ['P4-locale']
  )
  assert.match(failed[0].error, /src\/i18n\/languages\.ts/)
  assert.equal(fs.readFileSync(path.join(appDir, 'src/i18n/languages.ts'), 'utf8'), 'export const DEFAULT_LOCALE = "fr"\n')
  delete before['src/i18n/languages.ts']
  const after = snapshot(appDir)
  delete after['src/i18n/languages.ts']
  assert.deepEqual(after, before)
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('apply → restore round-trips byte-identical on a copy of the real sources', () => {
  const appDir = tempAppCopy()
  const before = snapshot(appDir)
  const restore = applyOverlay(appDir, undefined, { patches: allPatches() })

  const main = fs.readFileSync(path.join(appDir, 'electron/main.ts'), 'utf8')
  assert.match(main, /path\.join\(app\.getPath\('home'\), '\.janitor'\)/)
  assert.match(main, /'-m', 'janitor\.cli'/)
  assert.ok(readJournal(path.join(appDir, '.janitor-build-journal')), 'journal exists while the build runs')
  assert.notDeepEqual(snapshot(appDir), before)

  const restored = restore()

  assert.equal(restored.length, computePatchedFiles(APP_DIR, allPatches()).size + OVERLAY_FILES.length)
  assert.deepEqual(snapshot(appDir), before)
  assert.equal(fs.existsSync(path.join(appDir, '.janitor-build-journal')), false)
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('a build killed with SIGKILL is restored by --restore and by the next build', () => {
  const appDir = tempAppCopy()
  const before = snapshot(appDir)
  const engine = pathToFileURL(path.join(HERE, 'build.mjs')).href
  const patches = pathToFileURL(path.join(HERE, 'brand-patches.mjs')).href

  const crash = () =>
    spawnSync(
      process.execPath,
      [
        '--input-type=module',
        '-e',
        `const { applyOverlay } = await import(${JSON.stringify(engine)});
         const { allPatches } = await import(${JSON.stringify(patches)});
         applyOverlay(${JSON.stringify(appDir)}, undefined, { patches: allPatches() });
         process.kill(process.pid, 'SIGKILL')`
      ],
      { encoding: 'utf8' }
    )

  const first = crash()
  // Windows has no signals: process.kill(pid, 'SIGKILL') terminates the
  // process with exit code 1 and the parent sees no signal.
  if (process.platform === 'win32') assert.equal(first.status, 1, first.stderr)
  else assert.equal(first.signal, 'SIGKILL', first.stderr)
  assert.notDeepEqual(snapshot(appDir), before, 'the killed build left the tree patched')

  // `build.mjs --restore`
  const restored = restoreJournal(appDir)
  assert.ok(restored.length > 0)
  assert.deepEqual(snapshot(appDir), before)

  // Next build: recovers the leftover journal first, then patches cleanly.
  crash()
  const logs = []
  const restore = applyOverlay(appDir, undefined, { patches: allPatches(), log: m => logs.push(m) })
  assert.match(logs.join('\n'), /recovered an interrupted build/)
  restore()
  assert.deepEqual(snapshot(appDir), before)
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('a journal held by a live build is not touched', () => {
  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-patch-live-'))
  const journalDir = path.join(appDir, '.janitor-build-journal')
  fs.mkdirSync(journalDir)
  fs.writeFileSync(path.join(journalDir, 'manifest.json'), JSON.stringify({ pid: process.ppid, entries: [] }))

  assert.throws(() => beginTransaction(appDir, new Map()), new RegExp(`another Janitor desktop build \\(pid ${process.ppid}\\)`))
  assert.ok(fs.existsSync(path.join(journalDir, 'manifest.json')))
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('restore refuses to clobber a file changed after the crash, unless forced', () => {
  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-patch-conflict-'))
  fs.writeFileSync(path.join(appDir, 'a.ts'), 'original')
  beginTransaction(appDir, new Map([['a.ts', Buffer.from('patched')]]))

  // e.g. an upstream merge landed on the dirty tree after the crash
  fs.writeFileSync(path.join(appDir, 'a.ts'), 'merged upstream change')

  assert.throws(() => restoreJournal(appDir), /changed after the build patched them:\n {2}a\.ts/)
  assert.equal(fs.readFileSync(path.join(appDir, 'a.ts'), 'utf8'), 'merged upstream change')

  restoreJournal(appDir, { force: true })
  assert.equal(fs.readFileSync(path.join(appDir, 'a.ts'), 'utf8'), 'original')
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('a crash before the manifest was written leaves nothing to restore', () => {
  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-patch-early-'))
  fs.writeFileSync(path.join(appDir, 'a.ts'), 'original')
  fs.mkdirSync(path.join(appDir, '.janitor-build-journal', 'files'), { recursive: true })
  fs.writeFileSync(path.join(appDir, '.janitor-build-journal', 'files', '0'), 'stale backup')

  assert.equal(restoreJournal(appDir), null)
  assert.equal(fs.existsSync(path.join(appDir, '.janitor-build-journal')), false)
  assert.equal(fs.readFileSync(path.join(appDir, 'a.ts'), 'utf8'), 'original')
  fs.rmSync(appDir, { recursive: true, force: true })
})

test('computePatchedFiles only lists files that actually change', () => {
  const writes = computePatchedFiles(APP_DIR, allPatches())

  for (const [file, content] of writes) {
    assert.notEqual(content.toString('utf8'), fs.readFileSync(path.join(APP_DIR, file), 'utf8'), file)
  }
})
