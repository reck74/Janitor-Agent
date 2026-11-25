// Windows / macOS packaging (F6-02 icons, F6-03 builder config, F6-04 P20
// patches). Behaviour over the merged config, the overlay transaction and the
// patched functions run in a sandbox; read-only on apps/desktop.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import module from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import vm from 'node:vm'

import { EXE_IDENTITY, MENU_ROLE_LABELS, janitorAppId, platformPatches } from '../brand/platforms.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR, FORK_ONLY_TARGETS, OVERLAY_DIR, OVERLAY_FILES, applyOverlay, janitorBuilderConfig, readJson } from './build.mjs'
import { checkPatches, computePatchedFiles } from './patch-engine.mjs'

const upstream = () => readJson(path.join(APP_DIR, 'package.json')).build
const overlaySourceFor = target => OVERLAY_FILES.find(([, t]) => t === target)?.[0]

let patchedCache
const patched = file => {
  patchedCache ??= computePatchedFiles(APP_DIR, allPatches())

  return patchedCache.get(file).toString('utf8')
}

// A top-level `function name(` … `\n}\n` of a patched source, types stripped.
function topLevelFunction(source, name) {
  const start = source.indexOf(`\nfunction ${name}(`)

  assert.ok(start >= 0, `${name} not found`)

  const end = source.indexOf('\n}\n', start)

  return module.stripTypeScriptTypes(source.slice(start, end + 3))
}

// ---- F6-02 icons --------------------------------------------------------------

function icoEntries(buffer) {
  assert.equal(buffer.readUInt16LE(0), 0, 'ICO reserved')
  assert.equal(buffer.readUInt16LE(2), 1, 'ICO type must be icon')

  const entries = []

  for (let i = 0; i < buffer.readUInt16LE(4); i += 1) {
    const at = 6 + i * 16
    const size = buffer.readUInt32LE(at + 8)
    const offset = buffer.readUInt32LE(at + 12)

    assert.ok(offset + size <= buffer.length, `ICO entry ${i} out of bounds`)
    entries.push({ width: buffer[at] || 256, height: buffer[at + 1] || 256 })
  }

  return entries
}

function icnsChunks(buffer) {
  assert.equal(buffer.toString('latin1', 0, 4), 'icns')
  assert.equal(buffer.readUInt32BE(4), buffer.length, 'icns length header')

  const chunks = []

  for (let at = 8; at < buffer.length; ) {
    const length = buffer.readUInt32BE(at + 4)

    assert.ok(length >= 8 && at + length <= buffer.length, `bad icns chunk at ${at}`)
    chunks.push(buffer.toString('latin1', at, at + 4))
    at += length
  }

  return chunks
}

test('F6-02: the Windows icon is a valid .ico with every size up to 256 px', () => {
  const entries = icoEntries(fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-icon.ico')))
  const sizes = entries.map(e => e.width).sort((a, b) => a - b)

  assert.deepEqual(sizes, [16, 32, 48, 64, 128, 256])
  assert.ok(entries.every(e => e.width === e.height))
})

test('F6-02: the macOS icon is a valid .icns with a 1024 px (512@2x) image', () => {
  const chunks = icnsChunks(fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-icon.icns')))

  assert.ok(chunks.includes('ic10'), chunks.join(','))
  assert.ok(chunks.includes('ic09') || chunks.includes('ic14'), chunks.join(','))
})

test('F6-02: during a build assets/icon.ico is Janitor\'s and restore puts upstream\'s back; the .icns is fork-only', () => {
  assert.ok(fs.existsSync(path.join(APP_DIR, 'assets/icon.ico')), 'upstream ships assets/icon.ico')
  assert.equal(FORK_ONLY_TARGETS.has('assets/icon.ico'), false)
  assert.equal(FORK_ONLY_TARGETS.has('assets/janitor-icon.icns'), true)

  const appDir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-icons-app-'))

  try {
    for (const [, target] of OVERLAY_FILES) {
      fs.mkdirSync(path.dirname(path.join(appDir, target)), { recursive: true })
      if (!FORK_ONLY_TARGETS.has(target)) fs.copyFileSync(path.join(APP_DIR, target), path.join(appDir, target))
    }

    const restore = applyOverlay(appDir)

    assert.deepEqual(fs.readFileSync(path.join(appDir, 'assets/icon.ico')), fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-icon.ico')))
    assert.deepEqual(fs.readFileSync(path.join(appDir, 'assets/janitor-icon.icns')), fs.readFileSync(path.join(OVERLAY_DIR, 'assets/janitor-icon.icns')))

    restore()

    assert.deepEqual(fs.readFileSync(path.join(appDir, 'assets/icon.ico')), fs.readFileSync(path.join(APP_DIR, 'assets/icon.ico')))
    assert.equal(fs.existsSync(path.join(appDir, 'assets/janitor-icon.icns')), false)
  } finally {
    fs.rmSync(appDir, { recursive: true, force: true })
  }
})

// ---- F6-03 electron-builder ---------------------------------------------------

test('F6-03: every platform icon is a file the overlay writes, in the format that platform needs', () => {
  const merged = janitorBuilderConfig()

  for (const [platform, ext] of [['mac', '.icns'], ['win', '.ico'], ['linux', '.png']]) {
    const icon = merged[platform].icon

    assert.equal(path.extname(icon), ext, platform)
    assert.ok(overlaySourceFor(icon), `${platform}.icon ${icon} is not written by the overlay`)
  }

  // The .exe stamp (set-exe-identity.mjs) and resources/icon.ico read assets/icon.ico.
  assert.equal(merged.win.icon, 'assets/icon.ico')
  assert.ok(merged.extraResources.some(r => r.from === 'assets/icon.ico'))
})

test('F6-03: macOS is an ad-hoc signed dmg whose hardened runtime keeps library validation off', () => {
  const merged = janitorBuilderConfig()
  const base = upstream()

  // "-" signs ad hoc; null would skip signing and arm64 would refuse the app as damaged.
  assert.equal(merged.mac.identity, '-')
  assert.deepEqual(merged.mac.target, ['dmg'])
  assert.equal(merged.mac.hardenedRuntime, base.mac.hardenedRuntime)
  assert.equal(merged.mac.entitlements, base.mac.entitlements)
  assert.equal(merged.afterSign, base.afterSign, 'notarize.mjs stays; it skips itself without Apple credentials')

  // An ad-hoc signature has no Team ID: under the hardened runtime Electron's
  // frameworks only load with library validation disabled.
  const entitlements = fs.readFileSync(path.join(APP_DIR, merged.mac.entitlements), 'utf8')

  assert.match(entitlements, /<key>com\.apple\.security\.cs\.disable-library-validation<\/key>\s*<true\/>/)
  assert.doesNotMatch(merged.dmg.title, /Hermes/)
})

test('F6-03: every permission prompt macOS shows is Janitor\'s, in Spanish', () => {
  const info = janitorBuilderConfig().mac.extendInfo
  const prompts = Object.keys(upstream().mac.extendInfo).filter(key => /^NS\w+UsageDescription$/.test(key))

  assert.ok(prompts.length > 0)

  for (const key of prompts) {
    assert.match(info[key], /^Janitor /, key)
    assert.doesNotMatch(info[key], /Hermes|\b(uses|needs|when|the|your)\b/, key)
  }

  for (const [key, value] of Object.entries(info)) {
    assert.doesNotMatch(String(value), /Hermes/, key)
  }
})

test('F6-03: Windows is a per-user, assisted NSIS installer for x64 only, in Spanish', t => {
  const merged = janitorBuilderConfig()

  assert.deepEqual(merged.win.target, [{ target: 'nsis', arch: ['x64'] }])
  assert.equal(merged.win.signAndEditExecutable, false, 'upstream stamps the exe with rcedit instead (set-exe-identity.mjs)')
  assert.equal(merged.nsis.oneClick, false)
  assert.equal(merged.nsis.perMachine, false)
  assert.deepEqual(merged.nsis.installerLanguages, ['es_ES'])
  assert.equal(merged.nsis.shortcutName, 'Janitor')
  assert.equal(merged.nsis.uninstallDisplayName, 'Janitor')
  assert.equal(merged.publish, undefined, 'run-electron-builder.mjs already passes --publish never')

  let langs

  try {
    langs = module.createRequire(path.join(APP_DIR, 'package.json'))('app-builder-lib/out/util/langs')
  } catch {
    return t.skip('app-builder-lib not installed')
  }

  // The version-info language must be the LCID of the one installer language.
  assert.equal(Number(merged.nsis.language), langs.lcid[merged.nsis.installerLanguages[0]])
})

test('F6-03: the merged config passes electron-builder\'s own schema validation', async t => {
  let validateConfiguration, DebugLogger

  try {
    const require = module.createRequire(path.join(APP_DIR, 'package.json'))

    ;({ validateConfiguration } = require('app-builder-lib/out/util/config/config'))
    ;({ DebugLogger } = require('builder-util'))
  } catch {
    return t.skip('electron-builder not installed')
  }

  await validateConfiguration(janitorBuilderConfig(), new DebugLogger(false))
  await assert.rejects(validateConfiguration({ ...janitorBuilderConfig(), nsis: { notAnOption: true } }, new DebugLogger(false)))
})

// ---- F6-04 P20 ----------------------------------------------------------------

test('F6-04: every P20 patch resolves with its count and writes no Hermes', () => {
  const patches = platformPatches()
  const { results } = checkPatches(APP_DIR, patches)

  assert.deepEqual(results.filter(r => !r.ok), [])

  for (const patch of patches) {
    assert.doesNotMatch(patch.replace, /Hermes|Nous Research|nousresearch/, patch.id)
  }
})

function resolveHomeWith({ isWindows, env = {}, userDataOverride = null }) {
  const context = {
    path: path.posix,
    process: { env },
    IS_WINDOWS: isWindows,
    USER_DATA_OVERRIDE: userDataOverride,
    app: { getPath: name => (name === 'home' ? '/users/ana' : assert.fail(name)) },
    normalizeHermesHomeRoot: value => `normalized:${value}`,
    readWindowsUserEnvVar: () => 'C:\\Users\\ana\\AppData\\Local\\hermes',
    directoryExists: () => true
  }

  return vm.runInNewContext(`${topLevelFunction(patched('electron/main.ts'), 'resolveHermesHome')}\nresolveHermesHome()`, context)
}

test('F6-04a: the app home is ~/.janitor on Windows too, whatever upstream Hermes left behind', () => {
  // Registry HERMES_HOME and an existing %LOCALAPPDATA%\hermes or ~/.hermes are upstream's.
  assert.equal(resolveHomeWith({ isWindows: true, env: { LOCALAPPDATA: 'C:\\Users\\ana\\AppData\\Local' } }), '/users/ana/.janitor')
  assert.equal(resolveHomeWith({ isWindows: false }), '/users/ana/.janitor')
  // Overrides checked before the platform default are untouched.
  assert.equal(resolveHomeWith({ isWindows: true, userDataOverride: '/tmp/fresh' }), '/tmp/fresh/hermes-home')
  assert.equal(resolveHomeWith({ isWindows: true, env: { HERMES_HOME: '/x' } }), 'normalized:/x')
})

test('F6-04b: the Windows AppUserModelID is the builder appId (Start Menu shortcut, notifications)', () => {
  const source = patched('electron/main.ts')
  const line = source.split('\n').find(l => l.includes('app.setAppUserModelId('))
  const ids = []

  vm.runInNewContext(line, { app: { setAppUserModelId: id => ids.push(id) } })

  assert.deepEqual(ids, [janitorBuilderConfig().appId])
  assert.equal(janitorAppId(), janitorBuilderConfig().appId)
})

test('F6-04c: the exe stamp writes Janitor\'s identity and the Janitor icon', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-exe-identity-'))

  try {
    fs.mkdirSync(path.join(root, 'scripts'))
    fs.mkdirSync(path.join(root, 'assets'))
    fs.mkdirSync(path.join(root, 'node_modules', 'rcedit'), { recursive: true })
    fs.writeFileSync(path.join(root, 'scripts', 'set-exe-identity.mjs'), patched('scripts/set-exe-identity.mjs'))
    fs.copyFileSync(path.join(APP_DIR, 'scripts', 'utils.mjs'), path.join(root, 'scripts', 'utils.mjs'))
    fs.writeFileSync(path.join(root, 'node_modules', 'rcedit', 'package.json'), '{"name":"rcedit","type":"module","exports":"./index.js"}')
    fs.writeFileSync(path.join(root, 'node_modules', 'rcedit', 'index.js'), 'export const rcedit = () => { throw new Error("stub") }\n')
    fs.copyFileSync(path.join(OVERLAY_DIR, 'assets', 'janitor-icon.ico'), path.join(root, 'assets', 'icon.ico'))
    fs.writeFileSync(path.join(root, 'Janitor.exe'), '')

    const { stampExeIdentity } = await import(pathToFileURL(path.join(root, 'scripts', 'set-exe-identity.mjs')).href)
    const calls = []

    await stampExeIdentity(path.join(root, 'Janitor.exe'), root, { rcedit: async (exe, options) => calls.push(options) })

    assert.equal(calls.length, 1)

    const [options] = calls

    assert.deepEqual(fs.readFileSync(options.icon), fs.readFileSync(path.join(OVERLAY_DIR, 'assets', 'janitor-icon.ico')))

    for (const [key, value] of Object.entries(EXE_IDENTITY)) {
      assert.equal(options['version-string'][key], value, key)
    }

    assert.doesNotMatch(JSON.stringify([options['version-string'].ProductName, options['version-string'].FileDescription, options['version-string'].CompanyName]), /Hermes|Nous/)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

function buildMenu(isMac) {
  const noop = () => {}
  const context = {
    IS_MAC: isMac,
    APP_NAME: 'Janitor',
    process: { platform: isMac ? 'darwin' : 'linux' },
    Menu: { buildFromTemplate: template => template },
    mainWindow: null,
    DEFAULT_ZOOM_LEVEL: 0,
    ZOOM_STEP: 0.5,
    sendOpenUpdatesRequested: noop,
    showAboutPanelFresh: noop,
    createInstanceWindow: noop,
    sendOpenFolderRequested: noop,
    sendClosePreviewRequested: noop,
    sendPreviewNavCommand: noop,
    toggleDevTools: noop,
    setAndPersistZoomLevel: noop
  }

  return vm.runInNewContext(`${topLevelFunction(patched('electron/main.ts'), 'buildApplicationMenu')}\nbuildApplicationMenu()`, context)
}

function menuItems(template) {
  return template.flatMap(item => [item, ...(Array.isArray(item.submenu) ? menuItems(item.submenu) : [])])
}

test('F6-04e: every item of the application menu has a Spanish label, role items included', () => {
  for (const isMac of [true, false]) {
    const items = menuItems(buildMenu(isMac)).filter(item => item.type !== 'separator')

    for (const item of items) {
      assert.equal(typeof item.label, 'string', `${isMac ? 'mac' : 'other'}: ${JSON.stringify(item)} has no label`)
      assert.doesNotMatch(item.label, /Hermes|^(Quit|Hide|Undo|Redo|Cut|Copy|Paste|Delete|Select All|Minimize|Close|Zoom In|Services)\b/)
    }

    assert.ok(items.some(item => item.role === 'quit' && item.label === 'Salir de Janitor'))
  }

  const mac = menuItems(buildMenu(true))

  assert.ok(mac.some(item => item.role === 'hide' && item.label === 'Ocultar Janitor'))
  assert.equal(new Set(MENU_ROLE_LABELS.map(([role]) => role)).size, MENU_ROLE_LABELS.length)
})
