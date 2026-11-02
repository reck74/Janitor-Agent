import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import {
  APP_DIR,
  BUILDER_CONFIG,
  OVERLAY_DIR,
  OVERLAY_FILES,
  UPSTREAM_BUILDER_CONFIG,
  applyOverlay,
  janitorBuilderConfig,
  mergeBuilderConfig,
  readJson,
  upstreamBuilderConfig
} from './build.mjs'

test('overrides deep-merge into the upstream config without dropping keys', () => {
  const upstream = upstreamBuilderConfig()
  const merged = janitorBuilderConfig()

  for (const key of Object.keys(upstream)) {
    assert.ok(key in merged, `upstream key ${key} lost`)
  }

  assert.equal(merged.productName, 'Janitor')
  assert.equal(merged.appId, 'ai.janitor.desktop')
  assert.deepEqual(merged.files, upstream.files)
  assert.deepEqual(merged.extraResources, upstream.extraResources)

  for (const [key, value] of Object.entries(upstream.mac.extendInfo)) {
    if (!key.startsWith('CFBundle')) {
      assert.equal(merged.mac.extendInfo[key], value)
    }
  }
})

test('the packaged productName keeps the userData directory of earlier builds', () => {
  const pkg = readJson(path.join(APP_DIR, 'package.json'))

  assert.equal(janitorBuilderConfig().extraMetadata.productName, pkg.productName)
})

test('arrays are replaced, nested objects merged', () => {
  const merged = mergeBuilderConfig({ a: { b: 1, c: 2 }, list: [1, 2] }, { a: { c: 3 }, list: [9] })

  assert.deepEqual(merged, { a: { b: 1, c: 3 }, list: [9] })
})

test('every overlay source exists and every target still exists upstream', () => {
  assert.ok(fs.existsSync(path.join(APP_DIR, BUILDER_CONFIG)), `upstream no longer ships ${BUILDER_CONFIG}`)

  for (const [source, target] of OVERLAY_FILES) {
    assert.ok(fs.existsSync(path.join(OVERLAY_DIR, source)), `missing overlay asset ${source}`)

    if (target !== 'assets/janitor-icon.png') {
      assert.ok(fs.existsSync(path.join(APP_DIR, target)), `upstream no longer ships ${target}`)
    }
  }
})

test('applyOverlay packages with the Janitor config and restores every touched file', () => {
  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-overlay-app-'))
  const upstreamConfig = "module.exports = { appId: 'upstream', productName: 'Hermes', extraMetadata: { name: 'Hermes' } }\n"

  for (const [, target] of OVERLAY_FILES) {
    if (target === 'assets/janitor-icon.png') continue
    fs.mkdirSync(path.dirname(path.join(appDir, target)), { recursive: true })
    fs.writeFileSync(path.join(appDir, target), `upstream:${target}`)
  }

  fs.mkdirSync(path.join(appDir, 'assets'), { recursive: true })
  fs.writeFileSync(path.join(appDir, 'package.json'), '{"productName": "Hermes"}\n')
  fs.writeFileSync(path.join(appDir, BUILDER_CONFIG), upstreamConfig)

  const restore = applyOverlay(appDir)

  const icon = fs.readFileSync(path.join(appDir, 'assets/janitor-icon.png'))

  assert.deepEqual(icon, fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-mark.png')))

  const packaged = createRequire(path.join(appDir, 'package.json'))(path.join(appDir, BUILDER_CONFIG))

  assert.equal(packaged.appId, 'ai.janitor.desktop')
  assert.equal(packaged.extraMetadata.name, 'Hermes')
  assert.equal(packaged.extraMetadata.productName, 'Hermes')

  restore()

  assert.equal(fs.existsSync(path.join(appDir, 'assets/janitor-icon.png')), false)
  assert.equal(fs.existsSync(path.join(appDir, UPSTREAM_BUILDER_CONFIG)), false)
  assert.equal(fs.readFileSync(path.join(appDir, BUILDER_CONFIG), 'utf8'), upstreamConfig)

  for (const [, target] of OVERLAY_FILES) {
    if (target === 'assets/janitor-icon.png') continue
    assert.equal(fs.readFileSync(path.join(appDir, target), 'utf8'), `upstream:${target}`)
  }
})
