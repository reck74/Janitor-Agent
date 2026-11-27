// node --test apps/desktop-janitor/scripts/app-update.test.mjs
//
// Signed app updates (plan Fase 9): the manifest script (F9-01), verification
// (F9-02), install kind (F9-03) and download-before-closing (F9-05), against a
// local server and throwaway keys generated here. No real key is ever involved.

import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { after, before, test } from 'node:test'

import {
  APPIMAGE_NAME,
  JanitorUpdateError,
  MANIFEST_NAME,
  SIGNATURE_NAME,
  UPDATE_ORIGIN,
  checkAppUpdate,
  createDesktopUpdater,
  decideUpdate,
  detectInstallKind,
  installerFor,
  prepareUpdate,
  readAcceptedSequence,
  releaseAssetUrl,
  sequenceForVersion,
  verifyManifest
} from '../brand/app-update.mjs'

import { buildManifest, generateTestKeyPair, renderManifest, signManifest, verifyRelease } from './update-manifest.mjs'

const N = '0.21.5-janitor.4'
const N1 = '0.21.5-janitor.5'
const COMMIT = 'a'.repeat(40)
const ARCH_PKG = 'janitor-desktop-bin-0.21.5.janitor.5-1-x86_64.pkg.tar.zst'
const RELAY = 'posix.sh … --app-installer … --target-commit …'

const keys = generateTestKeyPair()
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-app-update-'))

after(() => fs.rmSync(tmp, { recursive: true, force: true }))

/** A release directory for `version` with an AppImage and an Arch package, signed with `signer`. */
async function makeRelease(name, { version = N1, commit = COMMIT, signer = keys } = {}) {
  const dir = path.join(tmp, name)

  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, APPIMAGE_NAME), `appimage ${version} ${name}`)
  fs.writeFileSync(path.join(dir, ARCH_PKG), `paquete ${version} ${name}`)

  const manifestPath = await buildManifest({
    version,
    commit,
    paths: [path.join(dir, APPIMAGE_NAME), path.join(dir, ARCH_PKG)],
    outDir: dir
  })

  signManifest({ manifestPath, privateKeyPem: signer.privateKeyPem })

  return dir
}

const read = (dir, name) => fs.readFileSync(path.join(dir, name))
const signed = dir => ({ bytes: read(dir, MANIFEST_NAME), signatureText: read(dir, SIGNATURE_NAME).toString('utf8') })

const rejects = (fn, code) =>
  assert.throws(fn, error => error instanceof JanitorUpdateError && error.code === code && /[a-záéíóúñ]/.test(error.message))

const rejectsAsync = (promise, code) =>
  assert.rejects(promise, error => error instanceof JanitorUpdateError && error.code === code)

// ---- F9-01: the manifest ------------------------------------------------------

test('the manifest has one file entry per line, in the layout the Arch updater reads', () => {
  const text = renderManifest({
    version: N1,
    commit: COMMIT,
    files: [
      { name: 'b.AppImage', size: 2, sha256: 'b'.repeat(64) },
      { name: 'a.pkg.tar.zst', size: 1, sha256: 'a'.repeat(64) }
    ]
  })

  assert.deepEqual(
    text.split('\n').filter(line => line.includes('"name"')),
    [
      `    {"name": "a.pkg.tar.zst", "size": 1, "sha256": "${'a'.repeat(64)}"},`,
      `    {"name": "b.AppImage", "size": 2, "sha256": "${'b'.repeat(64)}"}`
    ]
  )
  assert.equal(JSON.parse(text).sequence, sequenceForVersion(N1))
  assert.equal(JSON.parse(text).tag, `v${N1}`)
})

test('a file name that could break the line layout is refused when the manifest is built', () => {
  for (const name of ['a"b', 'a b', 'a\nb', '../x', '']) {
    assert.throws(() => renderManifest({ version: N1, commit: COMMIT, files: [{ name, size: 1, sha256: 'a'.repeat(64) }] }))
  }
})

test('the delivery number grows with every part of the version', () => {
  const order = ['0.21.5-janitor.4', '0.21.5-janitor.5', '0.21.5-janitor.10', '0.21.6-janitor.1', '0.22.0-janitor.1', '1.0.0-janitor.1']
  const numbers = order.map(sequenceForVersion)

  assert.deepEqual([...numbers].sort((a, b) => a - b), numbers)
  assert.equal(new Set(numbers).size, numbers.length)
  assert.equal(sequenceForVersion('0.21.5+janitor.4'), null)
})

test('what the release job publishes verifies with the public key, file by file', async () => {
  const dir = await makeRelease('publicado')
  const manifest = await verifyRelease({
    manifestPath: path.join(dir, MANIFEST_NAME),
    signaturePath: path.join(dir, SIGNATURE_NAME),
    publicKeyPem: keys.publicKeyPem,
    dir
  })

  assert.equal(manifest.version, N1)

  fs.appendFileSync(path.join(dir, APPIMAGE_NAME), 'x')
  await assert.rejects(
    verifyRelease({ manifestPath: path.join(dir, MANIFEST_NAME), signaturePath: path.join(dir, SIGNATURE_NAME), publicKeyPem: keys.publicKeyPem, dir }),
    /does not match the signed manifest/
  )
})

// ---- F9-02: verification -------------------------------------------------------

test('a manifest signed with the release key is accepted', async () => {
  const manifest = verifyManifest({ ...signed(await makeRelease('valido')), publicKeyPem: keys.publicKeyPem })

  assert.equal(manifest.commit, COMMIT)
  assert.equal(manifest.files.length, 2)
})

test('one changed byte of the manifest invalidates the signature', async () => {
  const { bytes, signatureText } = signed(await makeRelease('alterado'))
  const altered = Buffer.from(bytes.toString('utf8').replace(COMMIT, 'b'.repeat(40)))

  rejects(() => verifyManifest({ bytes: altered, signatureText, publicKeyPem: keys.publicKeyPem }), 'firma')
})

test('a manifest signed with another key is refused', async () => {
  const forged = signed(await makeRelease('otra-clave', { signer: generateTestKeyPair() }))

  rejects(() => verifyManifest({ ...forged, publicKeyPem: keys.publicKeyPem }), 'firma')
})

test('a missing, truncated or non-Ed25519 key or signature is refused', async () => {
  const good = signed(await makeRelease('sin-clave'))
  const rsa = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 }).publicKey.export({ type: 'spki', format: 'pem' })

  rejects(() => verifyManifest({ ...good, publicKeyPem: null }), 'sin-clave')
  rejects(() => verifyManifest({ ...good, publicKeyPem: rsa }), 'sin-clave')
  rejects(() => verifyManifest({ ...good, publicKeyPem: keys.publicKeyPem, signatureText: '' }), 'firma')
  rejects(() => verifyManifest({ ...good, publicKeyPem: keys.publicKeyPem, signatureText: good.signatureText.slice(4) }), 'firma')
})

test('a correctly signed manifest with contents the app does not accept is refused', () => {
  const sign = object => {
    const bytes = Buffer.from(JSON.stringify(object))

    return { bytes, signatureText: crypto.sign(null, bytes, crypto.createPrivateKey(keys.privateKeyPem)).toString('base64'), publicKeyPem: keys.publicKeyPem }
  }

  const base = { schema: 1, version: N1, tag: `v${N1}`, commit: COMMIT, sequence: sequenceForVersion(N1), files: [{ name: APPIMAGE_NAME, size: 1, sha256: 'a'.repeat(64) }] }

  assert.equal(verifyManifest(sign(base)).version, N1)

  for (const change of [
    { schema: 2 },
    { sequence: sequenceForVersion(N1) + 1 },
    { tag: 'v9.9.9-janitor.9' },
    { commit: 'main' },
    { files: [] },
    { files: [{ name: '../../etc/passwd', size: 1, sha256: 'a'.repeat(64) }] },
    { files: [base.files[0], base.files[0]] },
    { files: [{ ...base.files[0], size: -1 }] }
  ]) {
    rejects(() => verifyManifest(sign({ ...base, ...change })), 'manifiesto')
  }
})

test('never an older delivery; the same one can be repeated; a newer one is installed', async () => {
  const manifest = verifyManifest({ ...signed(await makeRelease('entregas')), publicKeyPem: keys.publicKeyPem })
  const decide = extra => decideUpdate({ manifest, targetCommit: COMMIT, appVersion: N, kind: 'appimage', ...extra })

  assert.equal(decide({}).action, 'app-and-engine')
  assert.equal(decide({}).installer.name, APPIMAGE_NAME)
  // Same delivery again (the app is already N+1, the engine is not): finish it.
  assert.deepEqual(decide({ appVersion: N1, acceptedSequence: manifest.sequence }), { action: 'engine-only', installer: null })
  // The app is newer than what is offered.
  rejects(() => decide({ appVersion: '0.21.5-janitor.6' }), 'mas-vieja')
  // A newer delivery was accepted before (a replayed old manifest).
  rejects(() => decide({ acceptedSequence: manifest.sequence + 1 }), 'mas-vieja')
  // The channel moved: the manifest is of another commit.
  rejects(() => decide({ targetCommit: 'c'.repeat(40) }), 'otro-commit')
})

test('each install kind gets its own installer, and a release without it says so', async () => {
  const manifest = verifyManifest({ ...signed(await makeRelease('instaladores')), publicKeyPem: keys.publicKeyPem })

  assert.equal(installerFor('appimage', manifest).name, APPIMAGE_NAME)
  assert.equal(installerFor('pacman', manifest).name, ARCH_PKG)
  assert.equal(installerFor('unknown', manifest), null)

  const onlyAppImage = { ...manifest, files: manifest.files.filter(file => file.name === APPIMAGE_NAME) }

  rejects(() => decideUpdate({ manifest: onlyAppImage, targetCommit: COMMIT, appVersion: N, kind: 'pacman' }), 'sin-instalador')
})

test('download URLs only ever point into the fork on github.com', () => {
  assert.equal(releaseAssetUrl(N1, APPIMAGE_NAME), `https://github.com/reck74/Janitor-Agent/releases/download/v${N1}/${APPIMAGE_NAME}`)
  rejects(() => releaseAssetUrl(N1, '../../../evil/repo/x'), 'nombre')
  rejects(() => releaseAssetUrl('1.0.0/../../evil', APPIMAGE_NAME), 'version')
})

// ---- F9-03: install kind -------------------------------------------------------

const APPIMAGE = { path: '/home/u/Apps/Janitor.AppImage', isFile: true, executable: true, dirWritable: true }
const HELPER = { present: true, keyPresent: true, pkexec: true }

test('install kind: one answer per way the app was installed, with the platform as data', () => {
  const kind = facts => {
    const { kind, selfUpdate } = detectInstallKind({ platform: 'linux', arch: 'x64', ...facts })

    return `${kind}:${selfUpdate}`
  }

  assert.equal(kind({ appImage: APPIMAGE }), 'appimage:true')
  assert.equal(kind({ packageOwner: 'janitor-desktop-bin', helper: HELPER }), 'pacman:true')
  assert.equal(kind({}), 'unknown:false')
  assert.equal(kind({ packageOwner: 'electron' }), 'unknown:false')
  // An AppImage wins over a package owner: $APPIMAGE is what is running.
  assert.equal(kind({ appImage: APPIMAGE, packageOwner: 'janitor-desktop-bin', helper: HELPER }), 'appimage:true')
  // Windows and macOS are the second delivery: unknown, today's behaviour.
  assert.equal(kind({ platform: 'win32', appImage: APPIMAGE }), 'unknown:false')
  assert.equal(kind({ platform: 'darwin', appImage: APPIMAGE }), 'unknown:false')
  assert.equal(kind({ arch: 'arm64', appImage: APPIMAGE }), 'unknown:false')
})

test('install kind: an $APPIMAGE that is not a usable file is not an AppImage install', () => {
  for (const appImage of [
    { ...APPIMAGE, path: 'relative/Janitor.AppImage' },
    { ...APPIMAGE, isFile: false },
    { ...APPIMAGE, executable: false },
    null
  ]) {
    assert.equal(detectInstallKind({ platform: 'linux', arch: 'x64', appImage }).kind, 'unknown')
  }
})

test('install kind: known but unable to update itself explains why, in Spanish', () => {
  const readOnly = detectInstallKind({ platform: 'linux', arch: 'x64', appImage: { ...APPIMAGE, dirWritable: false } })

  assert.deepEqual([readOnly.kind, readOnly.selfUpdate], ['appimage', false])
  assert.match(readOnly.reason, /\/home\/u\/Apps/)

  for (const helper of [null, { ...HELPER, present: false }, { ...HELPER, keyPresent: false }, { ...HELPER, pkexec: false }]) {
    const verdict = detectInstallKind({ platform: 'linux', arch: 'x64', packageOwner: 'janitor-desktop-bin', helper })

    assert.deepEqual([verdict.kind, verdict.selfUpdate], ['pacman', false])
    assert.match(verdict.reason, /pacman|pkexec/)
  }
})

// ---- F9-05: download before closing, against a local server ---------------------

let server
let serverUrl
let served = {} // url path → Buffer | () => Buffer
let requests = []

before(async () => {
  server = http.createServer((request, response) => {
    requests.push(request.url)

    const entry = served[request.url]
    const body = typeof entry === 'function' ? entry() : entry

    if (!body) {
      response.writeHead(404).end()

      return
    }

    response.writeHead(200, { 'content-length': body.length }).end(body)
  })

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  serverUrl = `http://127.0.0.1:${server.address().port}`
})

after(() => server.close())

/** Serve a release directory the way GitHub would, for the channel tip `commit`. */
function serve(dir, { version = N1, commit = COMMIT } = {}) {
  served = { [`/raw/${commit}/pyproject.toml`]: Buffer.from(`[project]\nname = "x"\nversion = "${version.replace('-', '+')}"\n`) }

  for (const name of fs.readdirSync(dir)) {
    served[`/releases/download/v${version}/${name}`] = fs.readFileSync(path.join(dir, name))
  }

  requests = []
}

// The only thing a test replaces is the transport: the fixed origin is mapped
// onto the local server. The code under test never sees another origin.
const fetchImpl = (url, init) => {
  assert.ok(url.startsWith(`${UPDATE_ORIGIN}/`), `request outside the fork: ${url}`)

  return fetch(serverUrl + url.slice(UPDATE_ORIGIN.length), init)
}

const stateDir = name => path.join(tmp, 'estado', name)

const prepare = (name, extra = {}) =>
  prepareUpdate({
    install: { kind: 'appimage', selfUpdate: true },
    targetCommit: COMMIT,
    appVersion: N,
    publicKeyPem: keys.publicKeyPem,
    stateDir: stateDir(name),
    relayScriptText: RELAY,
    fetchImpl,
    ...extra
  })

test('N → N+1: the installer is downloaded and verified before anything is handed to the relay', async () => {
  const dir = await makeRelease('n-mas-1')

  serve(dir)

  const progress = []
  const plan = await prepare('n-mas-1', { onProgress: value => progress.push(value) })

  assert.equal(plan.action, 'app-and-engine')
  assert.deepEqual(fs.readFileSync(plan.installerPath), read(dir, APPIMAGE_NAME))
  assert.equal(progress.at(-1), 1)

  const arg = flag => plan.args[plan.args.indexOf(flag) + 1]

  assert.equal(arg('--target-commit'), COMMIT)
  assert.equal(arg('--app-kind'), 'appimage')
  assert.equal(arg('--app-version'), N1)
  assert.equal(arg('--app-installer'), plan.installerPath)
  assert.equal(arg('--app-sha256'), crypto.createHash('sha256').update(read(dir, APPIMAGE_NAME)).digest('hex'))
  // The exact signed bytes travel with the installer: the installer side verifies them again.
  assert.deepEqual(fs.readFileSync(arg('--app-manifest')), read(dir, MANIFEST_NAME))
  assert.deepEqual(fs.readFileSync(arg('--app-manifest-sig')), read(dir, SIGNATURE_NAME))
  assert.equal(readAcceptedSequence(stateDir('n-mas-1')), sequenceForVersion(N1))
})

test('the Arch package is what a pacman install downloads', async () => {
  serve(await makeRelease('arch'))

  const plan = await prepare('arch', { install: { kind: 'pacman', selfUpdate: true } })

  assert.equal(path.basename(plan.installerPath), ARCH_PKG)
  assert.equal(plan.args[plan.args.indexOf('--app-kind') + 1], 'pacman')
})

test('repeating the same delivery reuses the verified download and passes the same pin', async () => {
  serve(await makeRelease('repetir'))

  const first = await prepare('repetir')

  requests = []

  const second = await prepare('repetir')

  assert.deepEqual(second.args, first.args)
  assert.equal(requests.some(url => url.endsWith(APPIMAGE_NAME)), false, 'the installer was downloaded twice')
})

test('app already on the published version: only the engine pin is handed over, nothing is downloaded', async () => {
  serve(await makeRelease('solo-motor'))

  const plan = await prepare('solo-motor', { appVersion: N1 })

  assert.equal(plan.action, 'engine-only')
  assert.deepEqual(plan.args, ['--target-commit', COMMIT, '--app-kind', 'appimage', '--app-version', N1])
  assert.equal(requests.some(url => url.endsWith(APPIMAGE_NAME)), false)
})

test('an installer that does not match the signed manifest is never left where the relay would find it', async () => {
  const dir = await makeRelease('sustituido')

  serve(dir)
  served[`/releases/download/v${N1}/${APPIMAGE_NAME}`] = Buffer.from(read(dir, APPIMAGE_NAME).toString('utf8').replace('appimage', 'APPIMAGE'))
  await rejectsAsync(prepare('sustituido'), 'suma')

  served[`/releases/download/v${N1}/${APPIMAGE_NAME}`] = Buffer.concat([read(dir, APPIMAGE_NAME), Buffer.from('de más')])
  await rejectsAsync(prepare('sustituido'), 'descarga')

  served[`/releases/download/v${N1}/${APPIMAGE_NAME}`] = read(dir, APPIMAGE_NAME).subarray(0, 5)
  await rejectsAsync(prepare('sustituido'), 'descarga')

  const left = fs.existsSync(stateDir('sustituido')) ? fs.readdirSync(stateDir('sustituido'), { recursive: true }) : []

  assert.deepEqual(left.filter(name => String(name).includes('AppImage')), [])
  assert.equal(readAcceptedSequence(stateDir('sustituido')), 0)
})

test('the channel moves during the download: a manifest of another commit is refused, nothing changes', async () => {
  // The app saw COMMIT as the tip; by the time it asks, the channel is on N+2 at another commit.
  const moved = 'b'.repeat(40)
  const dir = await makeRelease('canal-movido', { version: '0.21.5-janitor.6', commit: moved })

  serve(dir, { version: '0.21.5-janitor.6', commit: COMMIT })
  await rejectsAsync(prepare('canal-movido'), 'otro-commit')
  assert.equal(readAcceptedSequence(stateDir('canal-movido')), 0)
})

test('a release that is not complete yet (no manifest) starts nothing', async () => {
  const dir = await makeRelease('incompleto')

  serve(dir)
  delete served[`/releases/download/v${N1}/${MANIFEST_NAME}`]
  await rejectsAsync(prepare('incompleto'), 'no-publicado')
})

test('a replayed older release is refused once a newer one was accepted', async () => {
  serve(await makeRelease('nueva'))
  await prepare('repeticion')

  const old = 'd'.repeat(40)

  serve(await makeRelease('vieja', { version: '0.21.5-janitor.3', commit: old }), { version: '0.21.5-janitor.3', commit: old })
  await rejectsAsync(prepare('repeticion', { targetCommit: old, appVersion: '0.21.5-janitor.2' }), 'mas-vieja')
})

test('an unknown install, a build without key or an older engine keep the old hand-off untouched', async () => {
  serve(await makeRelease('legado'))

  for (const extra of [
    { install: { kind: 'unknown', selfUpdate: false, reason: 'x' } },
    { publicKeyPem: null },
    { relayScriptText: '#!/bin/bash\n# the relay of an engine older than the app updater\n' }
  ]) {
    requests = []

    const plan = await prepare('legado', extra)

    assert.equal(plan.action, 'legacy')
    assert.equal(plan.args, undefined)
    assert.deepEqual(requests, [], 'a legacy hand-off must not download anything')
  }
})

test('the check at startup reports «engine current, app old» and never throws', async () => {
  serve(await makeRelease('comprobar'))

  const check = extra =>
    checkAppUpdate({
      install: { kind: 'pacman', selfUpdate: true },
      targetCommit: COMMIT,
      appVersion: N,
      publicKeyPem: keys.publicKeyPem,
      stateDir: stateDir('comprobar'),
      fetchImpl,
      ...extra
    })

  assert.deepEqual(await check({}), { appVersion: N, kind: 'pacman', selfUpdate: true, reason: '', publishedVersion: N1, needsApp: true, error: null })
  assert.equal((await check({ appVersion: N1 })).needsApp, false)
  assert.equal((await check({ install: { kind: 'unknown', selfUpdate: false } })).needsApp, false)

  served = {}

  const failed = await check({})

  assert.equal(failed.needsApp, false)
  assert.match(failed.error, /no está publicado/)
})

// ---- F9-04 / F9-05: the wiring the Electron main process uses -------------------

function updater(name, extra = {}) {
  const logs = []
  const progress = []
  const owners = []

  const instance = createDesktopUpdater({
    appVersion: N,
    platform: 'linux',
    arch: 'x64',
    env: {},
    execPath: '/opt/janitor-desktop/Janitor',
    hermesHome: path.join(tmp, 'home', name),
    publicKeyPem: keys.publicKeyPem,
    fetchImpl,
    packageOwner: async file => {
      owners.push(file)

      return 'janitor-desktop-bin'
    },
    pathLookup: () => '/usr/bin/pkexec',
    log: message => logs.push(message),
    progress: payload => progress.push(payload),
    ...extra
  })

  return { instance, logs, progress, owners }
}

/** An AppImage install: a real executable file in a folder the test owns. */
function appImageEnv(name) {
  const file = path.join(tmp, 'apps', name, 'Janitor.AppImage')

  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, '#!/bin/sh\n', { mode: 0o755 })

  return { APPIMAGE: file }
}

const ENGINE_CURRENT = { supported: true, updateAvailable: false, behind: 0, targetSha: COMMIT, currentSha: COMMIT }

test('startup check: engine current but app old is an update, and says which version is published', async () => {
  serve(await makeRelease('arranque'))

  const { instance } = updater('arranque', { env: appImageEnv('arranque') })
  const status = await instance.augmentStatus(ENGINE_CURRENT)

  assert.equal(status.updateAvailable, true)
  assert.equal(status.behind, 0)
  assert.deepEqual(
    [status.janitorApp.kind, status.janitorApp.needsApp, status.janitorApp.publishedVersion, status.janitorApp.appVersion],
    ['appimage', true, N1, N]
  )
})

test('startup check: an app already on the published version adds nothing, and a failed check never hides the engine', async () => {
  serve(await makeRelease('al-dia'))

  const current = updater('al-dia', { env: appImageEnv('al-dia'), appVersion: N1 })

  assert.equal((await current.instance.augmentStatus(ENGINE_CURRENT)).updateAvailable, false)

  served = {}

  const offline = updater('sin-red', { env: appImageEnv('sin-red') })
  const behind = await offline.instance.augmentStatus({ ...ENGINE_CURRENT, updateAvailable: true, behind: 3 })

  assert.equal(behind.updateAvailable, true)
  assert.equal(behind.behind, 3)
  assert.equal(behind.janitorApp.needsApp, false)
  assert.ok(offline.logs.some(line => line.includes('app check')))
})

test('a cached status is only reused by the app version that produced it', () => {
  const { instance } = updater('cache')

  assert.equal(instance.cacheMatchesApp({ status: { janitorApp: { appVersion: N } } }), true)
  // The app was just replaced by N+1: yesterday's «update available» must not survive.
  assert.equal(instance.cacheMatchesApp({ status: { janitorApp: { appVersion: '0.21.5-janitor.3' } } }), false)
  assert.equal(instance.cacheMatchesApp({ status: {} }), false)
  assert.equal(instance.cacheMatchesApp(null), false)
})

test('before closing: the delivery is verified and downloaded, with progress, and handed over as arguments', async () => {
  serve(await makeRelease('entrega'))

  const { instance, progress } = updater('entrega', { env: appImageEnv('entrega') })
  const delivery = await instance.prepareHandoff({ freshStatus: async () => ENGINE_CURRENT, relayScriptText: RELAY })

  assert.equal(delivery.failure, undefined)
  assert.ok(delivery.args.includes('--app-installer') && delivery.args.includes(COMMIT))
  assert.deepEqual(progress.at(-1), { stage: 'fetch', message: 'Descargando la app nueva…', percent: 100 })
})

test('before closing: a refusal returns a result for the user and no arguments — nothing is spawned', async () => {
  const dir = await makeRelease('rechazo')

  serve(dir)
  served[`/releases/download/v${N1}/${SIGNATURE_NAME}`] = Buffer.from(crypto.randomBytes(64).toString('base64'))

  const { instance, progress } = updater('rechazo', { env: appImageEnv('rechazo') })
  const delivery = await instance.prepareHandoff({ freshStatus: async () => ENGINE_CURRENT, relayScriptText: RELAY })

  assert.deepEqual(delivery.args, [])
  assert.equal(delivery.failure.ok, false)
  assert.match(delivery.failure.message, /firma.*no es válida.*No se cambió nada\.$/)
  assert.equal(progress.at(-1).stage, 'error')

  const offline = await instance.prepareHandoff({
    freshStatus: async () => ({ supported: true, error: 'fetch-failed', message: 'sin red' }),
    relayScriptText: RELAY
  })

  assert.match(offline.failure.message, /canal de versiones.*sin red/)
})

test('an install the app cannot classify hands over nothing and never asks the network', async () => {
  serve(await makeRelease('desconocido'))

  for (const extra of [
    { packageOwner: async () => null }, // a local build, a deb, a tarball
    { platform: 'darwin' },
    { platform: 'win32' },
    { publicKeyPem: null }
  ]) {
    requests = []

    const { instance } = updater('desconocido', extra)
    const delivery = await instance.prepareHandoff({ freshStatus: async () => assert.fail('must not check'), relayScriptText: RELAY })

    assert.deepEqual(delivery, { args: [] })
    assert.deepEqual(requests, [])
  }
})

test('the Arch package is recognised by who owns the running binary, asked once', async () => {
  serve(await makeRelease('arch-cableado'))

  // On this machine the helper is not installed: a package older than the updater.
  const { instance, owners } = updater('arch-cableado')
  const first = await instance.install()

  await instance.install()
  assert.equal(first.kind, 'pacman')
  assert.deepEqual(owners, ['/opt/janitor-desktop/Janitor'])
})
