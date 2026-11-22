import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import {
  APP_DIR,
  OVERLAY_DIR,
  OVERLAY_FILES,
  applyOverlay,
  janitorBuilderConfig,
  mergeBuilderConfig,
  readJson
} from './build.mjs'

// The desktop-overlay CI job runs only this file; the brand layer suites
// register their tests on import.
import './patch-engine.test.mjs'
import './brand.test.mjs'
import './first-run.test.mjs'
import './spanish.test.mjs'
import './theme.test.mjs'
import './servicios-plugin.test.mjs'

test('overrides deep-merge into the upstream config without dropping keys', () => {
  const upstream = readJson(path.join(APP_DIR, 'package.json')).build
  const merged = janitorBuilderConfig()

  for (const key of Object.keys(upstream)) {
    assert.ok(key in merged, `upstream key ${key} lost`)
  }

  assert.equal(merged.productName, 'Janitor')
  assert.deepEqual(merged.files, upstream.files)
  assert.deepEqual(merged.extraResources, upstream.extraResources)

  for (const [key, value] of Object.entries(upstream.mac.extendInfo)) {
    if (!key.startsWith('CFBundle')) {
      assert.equal(merged.mac.extendInfo[key], value)
    }
  }
})

test('the packaged productName is Janitor, so userData is ~/.config/Janitor (plan 4.3)', () => {
  const pkg = readJson(path.join(APP_DIR, 'package.json'))
  const merged = janitorBuilderConfig()

  // extraMetadata.productName is what Electron reads at runtime for app.name /
  // userData; it must match the packaged product so neither state nor the
  // single-instance lock is shared with a real Hermes Desktop.
  assert.equal(merged.extraMetadata.productName, merged.productName)
  assert.notEqual(merged.extraMetadata.productName, pkg.productName)
})

test('arrays are replaced, nested objects merged', () => {
  const merged = mergeBuilderConfig({ a: { b: 1, c: 2 }, list: [1, 2] }, { a: { c: 3 }, list: [9] })

  assert.deepEqual(merged, { a: { b: 1, c: 3 }, list: [9] })
})

test('every overlay source exists and every target still exists upstream', () => {
  for (const [source, target] of OVERLAY_FILES) {
    assert.ok(fs.existsSync(path.join(OVERLAY_DIR, source)), `missing overlay asset ${source}`)

    if (target !== 'assets/janitor-icon.png') {
      assert.ok(fs.existsSync(path.join(APP_DIR, target)), `upstream no longer ships ${target}`)
    }
  }
})

test('applyOverlay restores every touched file', () => {
  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-overlay-app-'))

  for (const [, target] of OVERLAY_FILES) {
    if (target === 'assets/janitor-icon.png') continue
    fs.mkdirSync(path.dirname(path.join(appDir, target)), { recursive: true })
    fs.writeFileSync(path.join(appDir, target), `upstream:${target}`)
  }

  fs.mkdirSync(path.join(appDir, 'assets'), { recursive: true })

  const restore = applyOverlay(appDir)

  const icon = fs.readFileSync(path.join(appDir, 'assets/janitor-icon.png'))

  assert.deepEqual(icon, fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-mark.png')))

  restore()

  assert.equal(fs.existsSync(path.join(appDir, 'assets/janitor-icon.png')), false)
  assert.equal(fs.existsSync(path.join(appDir, '.janitor-build-journal')), false)

  for (const [, target] of OVERLAY_FILES) {
    if (target === 'assets/janitor-icon.png') continue
    assert.equal(fs.readFileSync(path.join(appDir, target), 'utf8'), `upstream:${target}`)
  }
})
