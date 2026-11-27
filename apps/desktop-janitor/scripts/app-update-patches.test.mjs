// node --test apps/desktop-janitor/scripts/app-update-patches.test.mjs
//
// P22 (plan Fase 9: F9-04, F9-05, F9-08): the build wires the signed-update
// logic into the app. Read-only on apps/desktop: patched sources are computed
// in memory.

import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { APP_UPDATE_PATCHES, NOTICE, RUNTIME_MODULE, appUpdateGlueSource, appUpdatePatches, readUpdatePublicKey } from '../brand/app-update-patches.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR, FORK_ONLY_TARGETS, OVERLAY_DIR, OVERLAY_FILES } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'
import { checkTranspiles } from './transpile-check.mjs'

const REPO_ROOT = path.resolve(OVERLAY_DIR, '..', '..')
const patched = computePatchedFiles(APP_DIR, allPatches())
const text = file => patched.get(file).toString('utf8')
const upstream = file => fs.readFileSync(path.join(APP_DIR, file), 'utf8')

test('the logic the tests import is the file the build ships, and the build removes it afterwards', () => {
  assert.deepEqual(OVERLAY_FILES.find(([, target]) => target === RUNTIME_MODULE), ['brand/app-update.mjs', RUNTIME_MODULE])
  assert.ok(FORK_ONLY_TARGETS.has(RUNTIME_MODULE))
  assert.ok(!fs.existsSync(path.join(APP_DIR, RUNTIME_MODULE)), 'apps/desktop must stay upstream')
  assert.match(text('electron/main.ts'), /import \* as janitorAppUpdate from '\.\/janitor-app-update\.mjs'/)
})

test('the logic ships with Node built-ins only: nothing for the bundler to miss', () => {
  const source = fs.readFileSync(path.join(OVERLAY_DIR, 'brand', 'app-update.mjs'), 'utf8')
  const imports = [...source.matchAll(/^import .* from '([^']+)'$/gm)].map(match => match[1])

  assert.deepEqual(imports, ['node:crypto', 'node:fs', 'node:path'])
  // No environment variable or setting changes the origin or the key.
  assert.doesNotMatch(source, /process\.env/)
})

test('every patched file still transpiles', () => {
  for (const patch of APP_UPDATE_PATCHES) {
    const result = checkTranspiles(text(patch.file), patch.file, APP_DIR)

    assert.notEqual(result.ok, false, `${patch.file}: ${result.error}`)
  }
})

test('the check at startup also asks about the app, and the cache is tied to the app version', () => {
  const main = text('electron/main.ts')

  assert.match(main, /janitorUpdater\.cacheMatchesApp\(cached\) && cacheIsFresh\(/)
  assert.match(main, /const janitorResult = await janitorUpdater\.augmentStatus\(result\)/)
  assert.match(main, /status: janitorResult \}\)\n\n  return janitorResult/)
})

test('the hand-off verifies and downloads before the relay is spawned, and a refusal returns first', () => {
  const main = text('electron/main.ts')
  const prepare = main.indexOf('await janitorUpdater.prepareHandoff(')
  const refusal = main.indexOf('return janitorDelivery.failure')
  const spawnRelay = main.indexOf('const child = spawnUpdaterProcess(handoff.command, args, {', prepare)
  const quit = main.indexOf('isQuittingForHandoff = true', prepare)

  assert.ok(prepare > 0 && prepare < refusal && refusal < spawnRelay && spawnRelay < quit)
  assert.match(main, /String\(process\.pid\), \.\.\.janitorDelivery\.args\]/)
})

test('the public key is baked from brand/update-key.pem; without it the app never updates itself', t => {
  assert.match(appUpdateGlueSource(null), /JANITOR_UPDATE_PUBLIC_KEY: string \| null = null\n/)

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-key-'))

  t.after(() => fs.rmSync(dir, { recursive: true, force: true }))

  assert.equal(readUpdatePublicKey(path.join(dir, 'missing.pem')), null)

  const pem = crypto.generateKeyPairSync('ed25519').publicKey.export({ type: 'spki', format: 'pem' })
  const file = path.join(dir, 'update-key.pem')

  fs.writeFileSync(file, pem)
  assert.equal(readUpdatePublicKey(file), pem)
  assert.ok(appUpdateGlueSource(pem).includes(JSON.stringify(pem)))
  assert.equal(appUpdatePatches(pem).length, APP_UPDATE_PATCHES.length)

  fs.writeFileSync(file, crypto.generateKeyPairSync('rsa', { modulusLength: 2048 }).publicKey.export({ type: 'spki', format: 'pem' }))
  assert.throws(() => readUpdatePublicKey(file), /Ed25519/)

  // A private key must never be what gets committed and baked.
  fs.writeFileSync(file, crypto.generateKeyPairSync('ed25519').privateKey.export({ type: 'pkcs8', format: 'pem' }))
  assert.doesNotMatch(readUpdatePublicKey(file), /PRIVATE/)
})

test('no private key is committed anywhere in the overlay', () => {
  const walk = dir =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
      if (entry.name === 'node_modules') return []

      const full = path.join(dir, entry.name)

      return entry.isDirectory() ? walk(full) : [full]
    })

  const marker = ['BEGIN', 'PRIVATE KEY'].join(' ')

  for (const file of walk(OVERLAY_DIR).filter(name => /\.(pem|key|mjs|json|sh|in|policy)$/.test(name) || !path.extname(name))) {
    assert.ok(!fs.readFileSync(file, 'utf8').includes(marker), `${file} holds a private key`)
  }
})

test('one notice for engine and app: «Actualizar ahora» / «Más tarde», in Spanish', () => {
  const store = text('src/store/updates.ts')

  for (const phrase of [NOTICE.title, NOTICE.now, NOTICE.later]) {
    assert.ok(store.includes(JSON.stringify(phrase)), phrase)
  }

  // «Actualizar ahora» starts the update; «Más tarde» only postpones the notice.
  assert.match(store, /label: "Actualizar ahora",\n      onClick: \(\) => \{\n        snoozeUpdateToast\(\)\n        startActiveUpdate\(target\)/)
  assert.match(store, /label: "Más tarde",\n      onClick: \(\) => snoozeUpdateToast\(\)/)
  assert.ok(!upstream('src/store/updates.ts').includes('startActiveUpdate(target)\n      }\n    },\n    secondaryAction'))
})

test('«Actualizar siempre sin preguntar» is off by default, lives in Ajustes and starts at most once per run', () => {
  const store = text('src/store/updates.ts')
  const settings = text('src/app/settings/about-settings.tsx')

  assert.match(store, /atom<boolean>\(storedString\(JANITOR_AUTO_UPDATE_KEY\) === '1'\)/)
  assert.match(store, /\$janitorAutoUpdate\.get\(\) && !janitorAutoUpdateStarted\) \{\n    janitorAutoUpdateStarted = true\n    startActiveUpdate\('client'\)/)
  // The unattended start sits before the «Más tarde» snooze: a postponed notice does not disable it.
  assert.ok(store.indexOf('janitorAutoUpdateStarted = true') < store.indexOf('if (isUpdateToastSnoozed()) {\n    return\n  }\n\n  notify({'))
  assert.ok(settings.includes(`title=${JSON.stringify(NOTICE.autoTitle)}`))
  assert.match(settings, /onCheckedChange=\{value => void setJanitorAutoUpdate\(value\)\}/)
})

test('the relay no longer tells anyone to reinstall «AppImage/deb/rpm» by hand', () => {
  for (const name of ['posix.sh', 'janitor-app.sh']) {
    const script = fs.readFileSync(path.join(REPO_ROOT, 'scripts', 'desktop-update', name), 'utf8')

    assert.doesNotMatch(script, /AppImage\/deb\/rpm/, name)
    // `sudo` only ever appears in the command the user is told to run by hand.
    const sudoLines = script.split('\n').filter(line => /\bsudo\b/.test(line) && !line.trimStart().startsWith('#'))

    assert.ok(sudoLines.every(line => line.includes('manual="Para instalarla a mano: sudo pacman -U')), `${name} must never run sudo`)
  }
})
