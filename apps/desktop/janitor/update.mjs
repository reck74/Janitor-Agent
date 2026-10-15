// Janitor's Linux package owner: verified AppImage + Janitor runtime update.
import { accessSync, closeSync, constants, createReadStream, createWriteStream, existsSync, lstatSync, mkdirSync, mkdtempSync, openSync,
  readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'
import { spawn, spawnSync } from 'node:child_process'
import path from 'node:path'
import { Readable, Transform } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'

export const RELEASE_API = 'https://api.github.com/repos/reck74/Janitor-Agent/releases/latest'
export function releaseVersion(tag) {
  const version = String(tag || '').replace(/^v/, '')
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) throw new Error('Janitor release has no stable semantic version')
  return version
}
export function isNewer(next, current) {
  const a = releaseVersion(next).split('.').map(value => BigInt(value)), b = releaseVersion(current).split('.').map(value => BigInt(value))
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i]
  return false
}
function trustedAsset(url) {
  const parsed = new URL(url)
  if (parsed.protocol !== 'https:' || parsed.origin !== 'https://github.com' || parsed.username || parsed.password || parsed.search || parsed.hash ||
    !parsed.pathname.startsWith('/reck74/Janitor-Agent/releases/download/')) throw new Error('Release asset is outside the Janitor repository')
  return parsed.href
}
export function selectRelease(release, arch = process.arch) {
  if (release.draft || release.prerelease) throw new Error('Only published stable Janitor releases can be installed')
  const version = releaseVersion(release.tag_name)
  const architectures = arch === 'x64' ? ['x64', 'x86_64'] : arch === 'arm64' ? ['arm64', 'aarch64'] : []
  if (!architectures.length) throw new Error(`Unsupported AppImage architecture: ${arch}`)
  const names = architectures.map(value => `janitor-desktop-${version}-linux-${value}.AppImage`)
  const matches = (release.assets || []).filter(asset => names.includes(asset.name))
  if (matches.length !== 1) throw new Error('The release must contain exactly one AppImage for this architecture')
  const asset = matches[0]
  const checksum = release.assets.find(value => value.name === `${asset.name}.sha256`) ||
    release.assets.find(value => ['SHA256SUMS', 'checksums.txt'].includes(value.name))
  if (!checksum) throw new Error('The Janitor release has no checksum asset')
  return { version, name: asset.name, url: trustedAsset(asset.browser_download_url),
    checksumUrl: trustedAsset(checksum.browser_download_url) }
}
export async function fetchRelease(fetcher = fetch) {
  const response = await fetcher(RELEASE_API, { headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'Janitor-Desktop' },
    signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error(`Janitor release check failed: HTTP ${response.status}`)
  return response.json()
}
export function checksumFor(text, name) {
  for (const line of text.split(/\r?\n/)) {
    const match = /^([a-fA-F0-9]{64})(?:\s+\*?(.+))?$/.exec(line.trim())
    if (match && (match[2] === name || (!match[2] && text.trim().split(/\r?\n/).length === 1))) return match[1].toLowerCase()
  }
  throw new Error('Release checksum does not identify the selected AppImage')
}
export function assertOwnedAppImage(target) {
  if (!target || !path.isAbsolute(target) || !target.endsWith('.AppImage')) throw new Error('This installation is managed outside the Janitor AppImage updater')
  const stat = lstatSync(target)
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('AppImage update target must be a regular file')
  accessSync(target, constants.W_OK)
  accessSync(path.dirname(target), constants.W_OK)
}
export async function hashFile(file) {
  const hash = createHash('sha256')
  for await (const bytes of createReadStream(file)) hash.update(bytes)
  return hash.digest('hex')
}
export async function prepareUpdate({ selection, target, onDirectory }, fetcher = fetch) {
  assertOwnedAppImage(target)
  const directory = mkdtempSync(path.join(path.dirname(target), '.janitor-update-'))
  try {
    onDirectory?.({ directory, target, version: selection.version })
    const response = await fetcher(selection.checksumUrl, { signal: AbortSignal.timeout(30000) })
    if (!response.ok) throw new Error(`Checksum download failed: HTTP ${response.status}`)
    const expectedHash = checksumFor(await response.text(), selection.name)
    const download = await fetcher(selection.url, { signal: AbortSignal.timeout(600000) })
    if (!download.ok || !download.body) throw new Error(`AppImage download failed: HTTP ${download.status}`)
    const file = path.join(directory, selection.name)
    const hash = createHash('sha256'); let count = 0
    const meter = new Transform({ transform(bytes, _, callback) {
      count += bytes.length
      if (count > 1024 * 1024 * 1024) return callback(new Error('AppImage exceeds the 1 GiB download limit'))
      hash.update(bytes); callback(null, bytes)
    } })
    await pipeline(Readable.fromWeb(download.body), meter, createWriteStream(file, { flags: 'wx', mode: 0o755 }))
    if (hash.digest('hex') !== expectedHash) throw new Error('AppImage checksum verification failed')
    return { directory, file, expectedHash, target, version: selection.version }
  } catch (error) { rmSync(directory, { recursive: true, force: true }); throw error }
}
function bootId() {
  try { return readFileSync('/proc/sys/kernel/random/boot_id', 'utf8').trim() } catch { return null }
}
function ownerAlive(owner) {
  if (!Number.isInteger(owner?.pid) || owner.pid <= 0) throw new Error('Janitor update lock has invalid owner metadata; inspect it before retrying')
  const boot = bootId()
  if (boot && owner.bootId && owner.bootId !== boot) return false
  try { process.kill(owner.pid, 0); return true } catch (error) { return error.code !== 'ESRCH' }
}
function atomicJson(file, value) {
  const temporary = `${file}.${randomUUID()}.tmp`
  writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 })
  renameSync(temporary, file)
}
function withGuard(home, operation) {
  mkdirSync(home, { recursive: true, mode: 0o700 })
  // flock locks the inherited open-file description. The parent's descriptor
  // retains it after the helper exits; crash/reboot releases it in the kernel.
  // Keep this inode across transactions; removing it would split ownership.
  const descriptor = openSync(path.join(home, '.janitor-desktop-update.guard'), 'a', 0o600)
  try {
    const result = spawnSync('flock', ['--exclusive', '--wait', '5', '3'],
      { stdio: ['ignore', 'ignore', 'ignore', descriptor], timeout: 6000 })
    if (result.error || result.status !== 0) throw new Error('Cannot serialize Janitor updates; util-linux flock must be available')
    return operation()
  } finally { closeSync(descriptor) }
}
function recoverLocked(home, directory) {
  if (!existsSync(directory)) return null
  const owner = JSON.parse(readFileSync(path.join(directory, 'owner.json'), 'utf8'))
  if (!/^[a-f0-9-]{36}$/.test(owner.token || '')) throw new Error('Janitor update lock has an invalid token')
  if (ownerAlive(owner)) return null
  let receipt = {}
  try { receipt = JSON.parse(readFileSync(path.join(directory, 'transaction.json'), 'utf8')) } catch { /* Interrupted before apply. */ }
  const result = { ok: false, interrupted: true, runtimeUpdated: false, desktopUpdated: false,
    error: 'A previous Janitor update was interrupted. The update lock was recovered; retry from Settings.' }
  if (receipt.token === owner.token) {
    result.runtimeUpdated = Boolean(receipt.runtimeUpdated)
    result.desktopUpdated = Boolean(receipt.desktopUpdated)
    result.runtimeUpdateUnknown = receipt.phase === 'runtime'
    if (result.runtimeUpdateUnknown) result.error = 'The previous update stopped during the runtime step. Its final state is unknown; inspect the Janitor PM update receipt before retrying.'
    if (['swapping', 'relaunch'].includes(receipt.phase) && path.isAbsolute(receipt.target || '') && receipt.target.endsWith('.AppImage')) {
      const backup = `${receipt.target}.janitor-previous-${owner.token}`
      if (existsSync(backup) && lstatSync(backup).isFile() && !lstatSync(backup).isSymbolicLink()) {
        renameSync(backup, receipt.target)
        result.desktopUpdated = false
        result.error = 'The update stopped during the Desktop swap. The previous AppImage was restored; the runtime had updated.'
      }
    }
  }
  if (receipt.token === owner.token && path.isAbsolute(receipt.downloadDirectory || '') &&
    path.dirname(receipt.downloadDirectory) === path.dirname(receipt.target || '') &&
    path.basename(receipt.downloadDirectory).startsWith('.janitor-update-') && existsSync(receipt.downloadDirectory)) {
    const stat = lstatSync(receipt.downloadDirectory)
    if (stat.isDirectory() && !stat.isSymbolicLink()) rmSync(receipt.downloadDirectory, { recursive: true, force: true })
  }
  atomicJson(path.join(home, '.janitor-desktop-update-result.json'), result)
  rmSync(directory, { recursive: true, force: true })
  return result
}
export function recoverInterruptedUpdate(home) {
  const directory = path.join(home, '.janitor-desktop-update.lock')
  if (!existsSync(directory)) return null
  return withGuard(home, () => recoverLocked(home, directory))
}
export function acquireLock(home) {
  return withGuard(home, () => {
    const directory = path.join(home, '.janitor-desktop-update.lock')
    const recovered = recoverLocked(home, directory)
    if (existsSync(directory)) throw new Error('Another Janitor Desktop update owns the update lock')
    mkdirSync(directory, { mode: 0o700 })
    const token = randomUUID()
    atomicJson(path.join(directory, 'owner.json'), { token, pid: process.pid, bootId: bootId() })
    return { directory, token, recovered: Boolean(recovered) }
  })
}
export function adoptLock(lock, parentPid) {
  return withGuard(path.dirname(lock.directory), () => {
    const owner = JSON.parse(readFileSync(path.join(lock.directory, 'owner.json'), 'utf8'))
    if (owner.token !== lock.token || owner.pid !== parentPid) throw new Error('Desktop update lock belongs to another process')
    atomicJson(path.join(lock.directory, 'owner.json'), { token: lock.token, pid: process.pid, bootId: bootId() })
    writeFileSync(path.join(lock.directory, 'ready'), 'ready\n')
  })
}
export function releaseLock(lock) {
  withGuard(path.dirname(lock.directory), () => {
    if (!existsSync(lock.directory)) return
    const owner = JSON.parse(readFileSync(path.join(lock.directory, 'owner.json'), 'utf8'))
    if (owner.token === lock.token) rmSync(lock.directory, { recursive: true, force: true })
  })
}
function writeTransaction(plan, phase, runtimeUpdated, desktopUpdated) {
  const owner = JSON.parse(readFileSync(path.join(plan.lock.directory, 'owner.json'), 'utf8'))
  if (owner.token !== plan.lock.token || owner.pid !== process.pid) throw new Error('Janitor update ownership changed before apply')
  atomicJson(path.join(plan.lock.directory, 'transaction.json'), { token: plan.lock.token, target: plan.target,
    version: plan.version, downloadDirectory: plan.directory, phase, runtimeUpdated, desktopUpdated })
}
export function recordPrepared(lock, prepared, phase = 'prepared') {
  writeTransaction({ ...prepared, lock }, phase, false, false)
}
function runRuntime(launcher, home, version, noGatewayRestart = false) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env, HERMES_HOME: home, JANITOR_HOME: home, _JANITOR_UPDATE_TARGET_TAG: `v${releaseVersion(version)}`, _JANITOR_SKIP_DESKTOP_BUILD: '1' }
    delete env.ELECTRON_RUN_AS_NODE
    const child = spawn(launcher, ['update', '--yes', ...(noGatewayRestart ? ['--no-gateway-restart'] : [])], { env, stdio: ['ignore', 'ignore', 'pipe'] })
    // Drain errors without persisting arbitrary subprocess text or credentials.
    child.stderr.resume()
    const timeout = setTimeout(() => { child.kill('SIGTERM'); reject(new Error('Janitor runtime update exceeded 30 minutes')) }, 1800000)
    child.once('error', error => { clearTimeout(timeout); reject(error) })
    child.once('exit', code => { clearTimeout(timeout); code === 0 ? resolve() : reject(new Error(`Janitor runtime update failed (exit ${code}). Inspect its PM update receipt and logs.`)) })
  })
}
export function relaunch(target, args, home, version, directory, { timeoutMs = 60000, stableMs = 1500 } = {}) {
  return new Promise((resolve, reject) => {
    const token = randomUUID(), readyPath = path.join(directory, 'application-ready.json')
    const env = { ...process.env, HERMES_HOME: home, JANITOR_HOME: home,
      JANITOR_UPDATE_READY_PATH: readyPath, JANITOR_UPDATE_READY_TOKEN: token }
    for (const key of ['ELECTRON_RUN_AS_NODE', 'APPIMAGE', 'APPDIR', 'OWD']) delete env[key]
    const child = spawn(target, args, { detached: true, stdio: 'ignore', env })
    let finished = false, confirmedAt = null
    const finish = error => {
      if (finished) return
      finished = true
      clearInterval(poll); clearTimeout(deadline)
      if (error) {
        // Only terminate this newly launched process group before restoring the
        // old executable. A detached messaging gateway owns a separate group.
        try { process.kill(-child.pid, 'SIGTERM') } catch { /* Already exited. */ }
        reject(error)
      } else { child.unref(); resolve() }
    }
    child.once('error', () => finish(new Error('Updated Janitor Desktop could not start')))
    child.once('exit', (code, signal) => finish(new Error(`Updated Janitor Desktop exited before readiness (exit ${code}, signal ${signal || 'none'})`)))
    const deadline = setTimeout(() => finish(new Error('Updated Janitor Desktop did not confirm its version and renderer readiness')), timeoutMs)
    const poll = setInterval(() => {
      if (!existsSync(readyPath)) return
      try {
        const ready = JSON.parse(readFileSync(readyPath, 'utf8'))
        if (ready.token !== token || ready.version !== version || ready.product !== 'Janitor Agent' || !Number.isInteger(ready.pid)) {
          finish(new Error('Updated Janitor Desktop readiness identity does not match the selected release')); return
        }
        process.kill(ready.pid, 0)
        confirmedAt ??= Date.now()
        if (Date.now() - confirmedAt >= stableMs) finish()
      } catch { finish(new Error('Updated Janitor Desktop readiness confirmation is invalid')) }
    }, 50)
  })
}
export async function applyPrepared(plan, operations = {}) {
  let runtimeUpdated = false, desktopUpdated = false
  const backup = `${plan.target}.janitor-previous-${plan.lock.token}`
  try {
    assertOwnedAppImage(plan.target)
    if (!plan.file.startsWith(plan.directory + path.sep) || await hashFile(plan.file) !== plan.expectedHash) throw new Error('Prepared AppImage changed before apply')
    const launcher = path.join(plan.runtimeRoot, 'scripts/janitor')
    if (!existsSync(path.join(plan.runtimeRoot, 'janitor_cli.py')) || !existsSync(launcher)) throw new Error('The Janitor runtime launcher is missing')
    writeTransaction(plan, 'runtime', false, false)
    await (operations.runRuntime || runRuntime)(launcher, plan.home, plan.version, plan.noGatewayRestart)
    runtimeUpdated = true
    writeTransaction(plan, 'swapping', true, false)
    renameSync(plan.target, backup)
    try { renameSync(plan.file, plan.target); desktopUpdated = true }
    catch (error) { renameSync(backup, plan.target); throw error }
    writeTransaction(plan, 'relaunch', true, true)
    try { await (operations.relaunch || relaunch)(plan.target, plan.args || [], plan.home, plan.version, plan.directory) }
    catch (error) {
      rmSync(plan.target); renameSync(backup, plan.target); desktopUpdated = false; throw error
    }
    writeTransaction(plan, 'complete', true, true)
    const result = { ok: true, runtimeUpdated, desktopUpdated, version: plan.version, backup }
    atomicJson(path.join(plan.home, '.janitor-desktop-update-result.json'), result)
    return result
  } catch (error) {
    const result = { ok: false, runtimeUpdated, desktopUpdated, error: error.message }
    atomicJson(path.join(plan.home, '.janitor-desktop-update-result.json'), result)
    return result
  }
  finally { rmSync(plan.directory, { recursive: true, force: true }); releaseLock(plan.lock) }
}
async function worker(file) {
  const plan = JSON.parse(readFileSync(file, 'utf8'))
  adoptLock(plan.lock, plan.parentPid)
  let exited = false
  for (let attempt = 0; attempt < 600; attempt++) {
    try { process.kill(plan.parentPid, 0) } catch (error) { if (error.code === 'ESRCH') { exited = true; break } }
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  const result = exited ? await applyPrepared(plan) : { ok: false, error: 'Desktop did not exit before the update deadline' }
  writeFileSync(path.join(plan.home, '.janitor-desktop-update-result.json'), JSON.stringify(result, null, 2) + '\n', { mode: 0o600 })
  if (!exited) { rmSync(plan.directory, { recursive: true, force: true }); releaseLock(plan.lock) }
  rmSync(file, { force: true })
  if (!result.ok) {
    process.exitCode = 1
    // Failure must be visible even though the updating Desktop already closed.
    const notification = spawn('notify-send', ['-a', 'janitor-desktop', '-u', 'critical',
      'Janitor update failed', result.runtimeUpdated ? 'The runtime updated, but Desktop was preserved. Reopen Janitor for details.' : 'The previous Desktop was preserved. Reopen Janitor for details.'],
      { stdio: 'ignore' })
    notification.on('error', () => {})
  }
}
if (path.resolve(process.argv[1] || '') === fileURLToPath(import.meta.url) && process.argv[2] === '--apply') {
  worker(process.argv[3]).catch(error => { console.error(error.message); process.exitCode = 1 })
}
