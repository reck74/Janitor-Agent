#!/usr/bin/env node
// Exercise the shipped AppImage with a fresh home, without installing services.
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { _electron } from '@playwright/test'

const { values } = parseArgs({ options: { appimage: { type: 'string' }, keep: { type: 'boolean' }, report: { type: 'string' } } })
if (!values.appimage) throw new Error('Usage: janitor-smoke.mjs --appimage /absolute/Janitor.AppImage [--keep]')
const binary = path.resolve(values.appimage)
const metadata = JSON.parse(readFileSync(`${binary}.json`, 'utf8'))
const sandbox = mkdtempSync(path.join(os.tmpdir(), 'janitor-appimage-smoke-'))
for (const name of ['tmp', 'workspace']) mkdirSync(path.join(sandbox, name))
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
  !/(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)/i.test(key) && !/^(?:HERMES_|JANITOR_|ELECTRON_RUN_AS_NODE|APPIMAGE|APPDIR)/.test(key)))
Object.assign(env, { HOME: sandbox, JANITOR_HOME: path.join(sandbox, '.janitor'), HERMES_HOME: path.join(sandbox, '.janitor'),
  HERMES_DESKTOP_USER_DATA_DIR: path.join(sandbox, 'userData'), HERMES_DESKTOP_CWD: path.join(sandbox, 'workspace'),
  JANITOR_UPDATE_READY_PATH: path.join(sandbox, 'ready.json'), JANITOR_UPDATE_READY_TOKEN: randomUUID(),
  HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1', APPIMAGE_EXTRACT_AND_RUN: '1', TMPDIR: path.join(sandbox, 'tmp') })
let app
try {
  app = await _electron.launch({ executablePath: binary, env, timeout: 60000,
    args: ['--ozone-platform=headless', '--no-sandbox', '--disable-gpu'] })
  const page = await app.firstWindow()
  const native = await app.evaluate(({ app }) => ({ name: app.getName(), version: app.getVersion(),
    home: process.env.HERMES_HOME, override: process.env.HERMES_DESKTOP_HERMES_ROOT, electron: process.versions.electron, commit: JSON.parse(process.getBuiltinModule('fs').readFileSync(process.resourcesPath + '/janitor-release.json', 'utf8')).commit,
    bootstrapCommit: JSON.parse(process.getBuiltinModule('fs').readFileSync(process.resourcesPath + '/install-stamp.json', 'utf8')).commit }))
  assert.equal(native.name, 'Janitor Agent')
  assert.equal(native.version, metadata.janitorVersion)
  assert.equal(native.commit, metadata.commit, 'The packaged runtime bootstrap must identify the same immutable source as its sidecar')
  assert.equal(native.bootstrapCommit, metadata.commit, 'The effective installer stamp must point to this release commit')
  assert.equal(native.home, env.JANITOR_HOME)
  assert.equal(native.override, undefined, 'The installed runtime must go through its PM launcher')
  await page.getByText('Set up Janitor Agent', { exact: true }).waitFor()
  const deadline = Date.now() + 10000
  while (!existsSync(env.JANITOR_UPDATE_READY_PATH) && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50))
  const readiness = JSON.parse(readFileSync(env.JANITOR_UPDATE_READY_PATH, 'utf8'))
  assert.equal(readiness.token, env.JANITOR_UPDATE_READY_TOKEN)
  assert.equal(readiness.version, metadata.janitorVersion)
  assert.equal(readiness.product, 'Janitor Agent')
  const setupPromise = app.waitForEvent('window')
  await page.getByRole('button', { name: /Install Janitor locally/ }).click()
  const setup = await setupPromise
  await setup.locator('#minimax').waitFor()
  await setup.locator('#mode').selectOption('cloud')
  const fields = await setup.evaluate(() => ({ localHidden: document.querySelector('#local').hidden,
    cloudHidden: document.querySelector('#cloud').hidden, bridge: typeof window.janitorSetup?.submit }))
  assert.deepEqual(fields, { localHidden: true, cloudHidden: false, bridge: 'function' })
  const closing = setup.waitForEvent('close')
  // Headless ozone has no native painted surface for mouse coordinates.
  // Exercise the real button handler through its DOM click instead.
  await setup.locator('#cancel').evaluate(button => button.click())
  await closing
  assert.equal(existsSync(path.join(env.JANITOR_HOME, 'janitor-core')), false, 'Cancel must precede installer execution')
  const terminal = await app.evaluate(async ({ app }) => {
    const { createRequire } = process.getBuiltinModule('module')
    const pty = createRequire(app.getAppPath() + '/dist/electron-main.mjs')('node-pty')
    return new Promise((resolve, reject) => {
      const child = pty.spawn('/bin/sh', ['-c', 'printf JANITOR_PTY_OK'], { cwd: process.env.HOME, env: process.env })
      let output = ''
      const timer = setTimeout(() => { child.kill(); reject(new Error('Native PTY timed out')) }, 10000)
      child.onData(text => { output += text })
      child.onExit(({ exitCode }) => { clearTimeout(timer); resolve({ output, exitCode }) })
    })
  })
  assert.deepEqual(terminal, { output: 'JANITOR_PTY_OK', exitCode: 0 })
  const report = { ok: true, native, onboarding: 'local/cloud and cancellation passed', pty: 'passed', readiness: 'product/version and loaded renderer confirmed', sandbox: values.keep ? sandbox : 'removed' }
  if (values.report) writeFileSync(values.report, JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report))
} finally {
  if (app) await app.close()
  if (!values.keep) rmSync(sandbox, { recursive: true, force: true })
}
