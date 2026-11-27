// Signed updates of the Janitor app (plan docs/janitor/plans/actualizacion-automatica.md,
// Fase 9: F9-02 verification, F9-03 install kind, F9-05 download).
//
// This file is BOTH what the tests import and what ships: the build copies it,
// byte for byte, to apps/desktop/electron/janitor-app-update.mjs (scripts/build.mjs
// OVERLAY_FILES) and electron/main.ts imports it (brand/app-update-patches.mjs,
// P22). It uses Node built-ins only and takes everything else as data or as an
// injected dependency, so the same functions run under `node --test`.
//
// Rules it enforces (plan 4.3):
//   - one origin, https://github.com/reck74/Janitor-Agent. No environment
//     variable, setting or argument changes it, or the public key;
//   - the app installs only what an Ed25519-signed manifest describes: version,
//     engine commit, delivery number and, per installer, name, size and SHA-256;
//   - never an older delivery than the app or than the newest one accepted
//     before; the same delivery can be repeated to finish one cut halfway;
//   - download and verify first, change things afterwards.
//
// Every message a user can read is Spanish (directive #18).

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

export const UPDATE_ORIGIN = 'https://github.com/reck74/Janitor-Agent'
export const MANIFEST_NAME = 'janitor-update.json'
export const SIGNATURE_NAME = 'janitor-update.json.sig'
export const MANIFEST_SCHEMA = 1
export const MANIFEST_MAX_BYTES = 256 * 1024
export const SIGNATURE_MAX_BYTES = 1024
export const INSTALLER_MAX_BYTES = 1024 * 1024 * 1024
export const APPIMAGE_NAME = 'Janitor-linux-x86_64.AppImage'
export const ARCH_PACKAGE_NAME = 'janitor-desktop-bin'
// The Arch package installs these; the app only looks at whether they exist.
export const ARCH_HELPER_PATH = '/usr/lib/janitor-desktop/janitor-update-helper'
export const ARCH_HELPER_KEY_PATH = '/usr/lib/janitor-desktop/update-key.pem'

const VERSION_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})-janitor\.(\d{1,3})$/
const COMMIT_RE = /^[0-9a-f]{40}$/
const SHA256_RE = /^[0-9a-f]{64}$/
const FILE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const ARCH_PACKAGE_RE = /^janitor-desktop-bin-(\d[0-9a-z.]*)-(\d+)-x86_64\.pkg\.tar\.zst$/

/** An update refused or failed, with the reason the user reads. */
export class JanitorUpdateError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'JanitorUpdateError'
    this.code = code
  }
}

const fail = (code, message) => {
  throw new JanitorUpdateError(code, message)
}

/** `0.21.5-janitor.4` → its four numbers, or null. */
export function parseVersion(version) {
  const match = typeof version === 'string' ? VERSION_RE.exec(version) : null

  return match ? match.slice(1).map(Number) : null
}

/**
 * The delivery number of a version: a total order over releases that both the
 * release workflow and a build compute without git history. A release is found
 * by its tag and the tag is the version (janitor/release_channel.py), so two
 * releases never share one. Returns null for anything that is not a version.
 */
export function sequenceForVersion(version) {
  const parts = parseVersion(version)

  return parts ? ((parts[0] * 1000 + parts[1]) * 1000 + parts[2]) * 1000 + parts[3] : null
}

/** The release tag of a version: the same rule as janitor/release_channel.py expected_tag. */
export function tagForVersion(version) {
  if (!parseVersion(version)) fail('version', `La versión publicada no tiene la forma esperada: ${JSON.stringify(version)}.`)

  return `v${version}`
}

/** `0.21.5-janitor.4` → `0.21.5.janitor.4`, the Arch pkgver (scripts/arch-package.mjs pkgverFromTag). */
export function archPkgverForVersion(version) {
  tagForVersion(version)

  return version.replaceAll('-', '.')
}

/** URL of one file of a release. Tag and name are validated: nothing else reaches the URL. */
export function releaseAssetUrl(version, name) {
  const tag = tagForVersion(version)

  if (typeof name !== 'string' || !FILE_NAME_RE.test(name)) fail('nombre', `Nombre de archivo no válido en la versión publicada: ${JSON.stringify(name)}.`)

  return `${UPDATE_ORIGIN}/releases/download/${tag}/${name}`
}

/** URL of pyproject.toml at a commit: where the app learns which version a commit of the channel is. */
export function pyprojectUrl(commit) {
  if (typeof commit !== 'string' || !COMMIT_RE.test(commit)) fail('commit', 'El canal de versiones devolvió un commit que no es válido.')

  return `${UPDATE_ORIGIN}/raw/${commit}/pyproject.toml`
}

/** `version` of the [project] table, in its display form (janitor/version.py). */
export function versionFromPyproject(text) {
  let inProject = false

  for (const line of String(text).split(/\r?\n/)) {
    const header = line.match(/^\s*\[\s*([^\]]+?)\s*\]\s*(#.*)?$/)

    if (header) {
      inProject = header[1] === 'project'
      continue
    }

    if (!inProject) continue

    const entry = line.match(/^\s*version\s*=\s*(?:"([^"\\]*)"|'([^']*)')\s*(#.*)?$/)

    if (entry) return (entry[1] ?? entry[2]).replace('+', '-')
  }

  return null
}

/**
 * The one decision of how this copy of the app was installed. Pure: every fact
 * is data.
 *   platform, arch   process.platform / process.arch
 *   appImage         null, or { path, isFile, executable, dirWritable } for $APPIMAGE
 *   packageOwner     null, or the pacman package that owns the running binary
 *   helper           { present, keyPresent, pkexec } for the Arch updater
 * Returns { kind: 'appimage' | 'pacman' | 'unknown', selfUpdate, reason }.
 * `selfUpdate` false means "keep today's behaviour": the reason says why.
 */
export function detectInstallKind({ platform, arch, appImage = null, packageOwner = null, helper = null } = {}) {
  if (platform !== 'linux') {
    return { kind: 'unknown', selfUpdate: false, reason: 'Esta versión solo actualiza la app sola en Linux.' }
  }

  if (arch !== 'x64') {
    return { kind: 'unknown', selfUpdate: false, reason: 'Solo se publican instaladores para Linux de 64 bits (x86_64).' }
  }

  if (appImage && typeof appImage.path === 'string' && path.posix.isAbsolute(appImage.path) && appImage.isFile && appImage.executable) {
    return appImage.dirWritable
      ? { kind: 'appimage', selfUpdate: true, reason: '' }
      : {
          kind: 'appimage',
          selfUpdate: false,
          reason: `No tienes permiso de escritura en la carpeta del AppImage (${path.posix.dirname(appImage.path)}). Muévelo a una carpeta tuya o reemplázalo a mano.`
        }
  }

  if (packageOwner === ARCH_PACKAGE_NAME) {
    if (!helper?.present || !helper?.keyPresent) {
      return {
        kind: 'pacman',
        selfUpdate: false,
        reason: 'El paquete instalado es anterior al actualizador: instala la versión nueva una vez a mano con pacman -U.'
      }
    }

    if (!helper.pkexec) {
      return { kind: 'pacman', selfUpdate: false, reason: 'Falta pkexec (paquete polkit): sin él no se puede pedir la contraseña del sistema.' }
    }

    return { kind: 'pacman', selfUpdate: true, reason: '' }
  }

  return { kind: 'unknown', selfUpdate: false, reason: 'Esta copia de la app no viene de un AppImage ni del paquete de Arch.' }
}

function parseManifestObject(data) {
  const bad = what => fail('manifiesto', `El manifiesto de la versión publicada no es válido (${what}).`)

  if (!data || typeof data !== 'object' || Array.isArray(data)) bad('no es un objeto')
  if (data.schema !== MANIFEST_SCHEMA) bad(`esquema ${JSON.stringify(data.schema)}; esta app entiende el ${MANIFEST_SCHEMA}`)
  if (!parseVersion(data.version)) bad('versión')
  if (data.tag !== `v${data.version}`) bad('la etiqueta no corresponde a la versión')
  if (typeof data.commit !== 'string' || !COMMIT_RE.test(data.commit)) bad('commit')
  if (data.sequence !== sequenceForVersion(data.version)) bad('el número de entrega no corresponde a la versión')
  if (!Array.isArray(data.files) || data.files.length === 0 || data.files.length > 64) bad('lista de archivos')

  const names = new Set()

  const files = data.files.map(file => {
    if (!file || typeof file !== 'object' || Array.isArray(file)) bad('archivo')
    if (typeof file.name !== 'string' || !FILE_NAME_RE.test(file.name)) bad('nombre de archivo')
    if (names.has(file.name)) bad(`archivo repetido: ${file.name}`)
    if (!Number.isSafeInteger(file.size) || file.size <= 0 || file.size > INSTALLER_MAX_BYTES) bad(`tamaño de ${file.name}`)
    if (typeof file.sha256 !== 'string' || !SHA256_RE.test(file.sha256)) bad(`suma de ${file.name}`)

    names.add(file.name)

    return { name: file.name, size: file.size, sha256: file.sha256 }
  })

  return { schema: data.schema, version: data.version, tag: data.tag, commit: data.commit, sequence: data.sequence, files }
}

/**
 * Check the Ed25519 signature over the manifest's exact bytes and only then
 * read it. `signatureText` is the .sig file (base64 of the 64 raw bytes).
 * Returns the manifest; throws JanitorUpdateError otherwise.
 */
export function verifyManifest({ bytes, signatureText, publicKeyPem }) {
  if (typeof publicKeyPem !== 'string' || !publicKeyPem.includes('BEGIN PUBLIC KEY')) {
    fail('sin-clave', 'Esta copia de la app no lleva clave de verificación: no puede actualizarse sola.')
  }

  if (!Buffer.isBuffer(bytes) || bytes.length === 0 || bytes.length > MANIFEST_MAX_BYTES) {
    fail('manifiesto', 'El manifiesto de la versión publicada está vacío o es demasiado grande.')
  }

  const signature = Buffer.from(String(signatureText ?? '').trim(), 'base64')

  if (signature.length !== 64) fail('firma', 'La firma de la versión publicada no tiene el formato esperado.')

  let key

  try {
    key = crypto.createPublicKey(publicKeyPem)
  } catch {
    fail('sin-clave', 'La clave de verificación de esta app no se puede leer.')
  }

  if (key.asymmetricKeyType !== 'ed25519') fail('sin-clave', 'La clave de verificación de esta app no es Ed25519.')

  if (!crypto.verify(null, bytes, key, signature)) {
    fail('firma', 'La firma de la versión publicada no es válida: no se instala nada.')
  }

  let data

  try {
    data = JSON.parse(bytes.toString('utf8'))
  } catch {
    fail('manifiesto', 'El manifiesto de la versión publicada no se puede leer.')
  }

  return parseManifestObject(data)
}

/** The installer of `manifest` for an install kind, or null when the release has none. */
export function installerFor(kind, manifest) {
  if (kind === 'appimage') return manifest.files.find(file => file.name === APPIMAGE_NAME) ?? null

  if (kind === 'pacman') {
    const pkgver = archPkgverForVersion(manifest.version)
    const matches = manifest.files.filter(file => ARCH_PACKAGE_RE.exec(file.name)?.[1] === pkgver)

    return matches.length === 1 ? matches[0] : null
  }

  return null
}

/**
 * What to do with a verified manifest. Pure.
 *   targetCommit   the channel's tip the app saw: the manifest must name it
 *   appVersion     app.getVersion()
 *   acceptedSequence  the newest delivery this install accepted before (0 = none)
 * Returns { action: 'app-and-engine' | 'engine-only', installer }; throws when
 * the manifest must not be used.
 */
export function decideUpdate({ manifest, targetCommit, appVersion, acceptedSequence = 0, kind }) {
  if (manifest.commit !== targetCommit) {
    fail('otro-commit', 'El manifiesto publicado no corresponde a la versión del canal: no se instala nada. Vuelve a intentarlo en unos minutos.')
  }

  const floor = Math.max(Number(acceptedSequence) || 0, sequenceForVersion(appVersion) ?? 0)

  if (manifest.sequence < floor) {
    fail('mas-vieja', `La versión publicada (${manifest.version}) es más vieja que la que ya tienes: no se baja de versión.`)
  }

  if (manifest.version === appVersion) return { action: 'engine-only', installer: null }

  const installer = installerFor(kind, manifest)

  if (!installer) {
    fail('sin-instalador', `La versión ${manifest.version} no publica instalador para tu tipo de instalación. No se cambió nada.`)
  }

  return { action: 'app-and-engine', installer }
}

async function readCapped(response, maxBytes, what) {
  const chunks = []
  let total = 0

  for await (const chunk of response.body) {
    total += chunk.length

    if (total > maxBytes) fail('descarga', `${what} pesa más de lo esperado: descarga cancelada.`)

    chunks.push(Buffer.from(chunk))
  }

  return Buffer.concat(chunks)
}

async function get(fetchImpl, url, what, signal) {
  if (!url.startsWith(`${UPDATE_ORIGIN}/`)) fail('origen', 'Se intentó descargar desde un origen que no es el de Janitor.')

  let response

  try {
    response = await fetchImpl(url, { redirect: 'follow', signal })
  } catch (error) {
    fail('red', `No se pudo descargar ${what}: sin conexión o el servidor no responde (${error?.message ?? error}).`)
  }

  if (response.status === 404) fail('no-publicado', `${what} no está publicado todavía. Vuelve a intentarlo en unos minutos.`)
  if (!response.ok || !response.body) fail('red', `No se pudo descargar ${what} (respuesta ${response.status}).`)

  return response
}

/**
 * Find and verify the release the channel's tip `commit` belongs to:
 * pyproject.toml at that commit gives the version (so the tag), the release
 * gives the manifest and its signature. Nothing here is trusted until the
 * signature holds and the manifest names `commit`.
 */
export async function fetchVerifiedManifest({ commit, publicKeyPem, fetchImpl, signal }) {
  const pyproject = await readCapped(await get(fetchImpl, pyprojectUrl(commit), 'la versión del canal', signal), MANIFEST_MAX_BYTES, 'La descripción de la versión')
  const version = versionFromPyproject(pyproject.toString('utf8'))

  if (!parseVersion(version)) fail('version', 'No se pudo leer qué versión es la publicada en el canal.')

  const bytes = await readCapped(await get(fetchImpl, releaseAssetUrl(version, MANIFEST_NAME), 'el manifiesto de la versión', signal), MANIFEST_MAX_BYTES, 'El manifiesto')
  const signatureBytes = await readCapped(await get(fetchImpl, releaseAssetUrl(version, SIGNATURE_NAME), 'la firma de la versión', signal), SIGNATURE_MAX_BYTES, 'La firma')
  const signatureText = signatureBytes.toString('utf8')
  const manifest = verifyManifest({ bytes, signatureText, publicKeyPem })

  if (manifest.version !== version || manifest.commit !== commit) {
    fail('otro-commit', 'El manifiesto publicado no corresponde a la versión del canal: no se instala nada. Vuelve a intentarlo en unos minutos.')
  }

  return { manifest, bytes, signatureText }
}

/** SHA-256 and size of a file, streamed. */
export async function hashFile(file) {
  const hash = crypto.createHash('sha256')
  let size = 0

  for await (const chunk of fs.createReadStream(file)) {
    hash.update(chunk)
    size += chunk.length
  }

  return { sha256: hash.digest('hex'), size }
}

/**
 * Download one installer of a verified manifest into `dir` and check its size
 * and SHA-256. A complete, matching file left by an earlier attempt is reused.
 * The file is written under a temporary name and renamed once it verifies, so
 * `dest` never holds anything unverified. Returns the path.
 */
export async function downloadInstaller({ manifest, installer, dir, fetchImpl, onProgress = () => {}, signal }) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })

  const dest = path.join(dir, installer.name)
  const matches = async file => {
    try {
      const got = await hashFile(file)

      return got.size === installer.size && got.sha256 === installer.sha256
    } catch {
      return false
    }
  }

  if (await matches(dest)) {
    onProgress(1)

    return dest
  }

  const partial = `${dest}.descarga`
  const response = await get(fetchImpl, releaseAssetUrl(manifest.version, installer.name), 'el instalador', signal)
  const out = fs.createWriteStream(partial, { mode: 0o600 })
  const hash = crypto.createHash('sha256')
  let size = 0

  try {
    for await (const chunk of response.body) {
      size += chunk.length

      if (size > installer.size) fail('descarga', 'El instalador pesa más de lo que dice el manifiesto firmado: descarga cancelada.')

      hash.update(chunk)

      if (!out.write(chunk)) await new Promise(resolve => out.once('drain', resolve))

      onProgress(size / installer.size)
    }

    await new Promise((resolve, reject) => out.end(error => (error ? reject(error) : resolve())))

    if (size !== installer.size) fail('descarga', 'La descarga del instalador quedó incompleta. Vuelve a intentarlo.')
    if (hash.digest('hex') !== installer.sha256) fail('suma', 'El instalador descargado no coincide con el manifiesto firmado: no se instala.')

    fs.renameSync(partial, dest)
  } catch (error) {
    out.destroy()
    fs.rmSync(partial, { force: true })

    if (error instanceof JanitorUpdateError) throw error

    fail('descarga', `No se pudo guardar el instalador (${error?.message ?? error}). Revisa el espacio en disco.`)
  }

  return dest
}

const STATE_FILE = 'estado.json'

/** The newest delivery this install accepted (0 when none, or the file is unreadable). */
export function readAcceptedSequence(dir) {
  try {
    const value = JSON.parse(fs.readFileSync(path.join(dir, STATE_FILE), 'utf8'))?.maxSequence

    return Number.isSafeInteger(value) && value > 0 ? value : 0
  } catch {
    return 0
  }
}

/** Remember an accepted delivery; never lowers the stored number. */
export function rememberAcceptedSequence(dir, sequence) {
  const next = Math.max(readAcceptedSequence(dir), sequence)

  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  fs.writeFileSync(path.join(dir, `${STATE_FILE}.tmp`), JSON.stringify({ maxSequence: next }))
  fs.renameSync(path.join(dir, `${STATE_FILE}.tmp`), path.join(dir, STATE_FILE))

  return next
}

/** Drop installers of other deliveries left in `dir` (each one is 120-150 MB). */
export function pruneDownloads(dir, keep) {
  let entries = []

  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return
  }

  for (const entry of entries) {
    if (entry.isDirectory() && entry.name !== keep && /^\d+$/.test(entry.name)) {
      fs.rmSync(path.join(dir, entry.name), { recursive: true, force: true })
    }
  }
}

/**
 * Whether the relay script of the installed engine knows how to install the
 * app (an engine older than this feature does not): the app then falls back to
 * the engine-only update it always did.
 */
export function relaySupportsAppInstall(scriptText) {
  return typeof scriptText === 'string' && scriptText.includes('--app-installer') && scriptText.includes('--target-commit')
}

/**
 * Everything the app does before it closes. Returns
 *   { action: 'legacy', reason }                       keep today's hand-off, nothing verified
 *   { action: 'engine-only' | 'app-and-engine', args, manifest, installerPath }
 * `args` are appended to the relay script's command line. Throws
 * JanitorUpdateError when the update must not start; nothing was changed then.
 */
export async function prepareUpdate({
  install,
  targetCommit,
  appVersion,
  publicKeyPem,
  stateDir,
  relayScriptText,
  fetchImpl,
  onProgress = () => {},
  signal
}) {
  if (!install?.selfUpdate) return { action: 'legacy', reason: install?.reason ?? '' }
  if (!publicKeyPem) return { action: 'legacy', reason: 'Esta copia de la app no lleva clave de verificación.' }
  if (!relaySupportsAppInstall(relayScriptText)) return { action: 'legacy', reason: 'El motor instalado es anterior al actualizador de la app.' }

  const { manifest, bytes, signatureText } = await fetchVerifiedManifest({ commit: targetCommit, publicKeyPem, fetchImpl, signal })

  const decision = decideUpdate({
    manifest,
    targetCommit,
    appVersion,
    acceptedSequence: readAcceptedSequence(stateDir),
    kind: install.kind
  })

  const args = ['--target-commit', manifest.commit, '--app-kind', install.kind, '--app-version', manifest.version]

  if (decision.action === 'engine-only') {
    rememberAcceptedSequence(stateDir, manifest.sequence)

    return { action: 'engine-only', args, manifest, installerPath: null }
  }

  const dir = path.join(stateDir, String(manifest.sequence))

  pruneDownloads(stateDir, String(manifest.sequence))

  const installerPath = await downloadInstaller({ manifest, installer: decision.installer, dir, fetchImpl, onProgress, signal })
  const manifestPath = path.join(dir, MANIFEST_NAME)
  const signaturePath = path.join(dir, SIGNATURE_NAME)

  // The exact signed bytes: whoever installs with more rights verifies them again (plan 8, finding 1).
  fs.writeFileSync(manifestPath, bytes, { mode: 0o600 })
  fs.writeFileSync(signaturePath, signatureText, { mode: 0o600 })
  rememberAcceptedSequence(stateDir, manifest.sequence)

  args.push(
    '--app-installer', installerPath,
    '--app-sha256', decision.installer.sha256,
    '--app-size', String(decision.installer.size),
    '--app-manifest', manifestPath,
    '--app-manifest-sig', signaturePath
  )

  return { action: 'app-and-engine', args, manifest, installerPath }
}

/**
 * What the check at startup adds to the engine's update status. Never throws:
 * a failure here must not hide an engine update, it is reported in `error`.
 * Returns { appVersion, kind, selfUpdate, reason, publishedVersion, needsApp, error }.
 */
export async function checkAppUpdate({ install, targetCommit, appVersion, publicKeyPem, stateDir, fetchImpl, signal }) {
  const base = {
    appVersion,
    kind: install?.kind ?? 'unknown',
    selfUpdate: Boolean(install?.selfUpdate && publicKeyPem),
    reason: install?.reason ?? '',
    publishedVersion: null,
    needsApp: false,
    error: null
  }

  if (!publicKeyPem || !targetCommit || (install?.kind ?? 'unknown') === 'unknown') return base

  try {
    const { manifest } = await fetchVerifiedManifest({ commit: targetCommit, publicKeyPem, fetchImpl, signal })
    const floor = Math.max(readAcceptedSequence(stateDir), sequenceForVersion(appVersion) ?? 0)

    return { ...base, publishedVersion: manifest.version, needsApp: manifest.version !== appVersion && manifest.sequence >= floor }
  } catch (error) {
    return { ...base, error: error instanceof JanitorUpdateError ? error.message : String(error?.message ?? error) }
  }
}
