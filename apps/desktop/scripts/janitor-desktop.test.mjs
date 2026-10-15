import { afterEach, describe, expect, it } from 'vitest'
import { createHash } from 'node:crypto'
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync, renameSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { acquireLock, adoptLock, applyPrepared, assertOwnedAppImage, checksumFor, isNewer, prepareUpdate, recoverInterruptedUpdate, recordPrepared, relaunch, releaseLock, selectRelease } from '../janitor/update.mjs'
import { buildJanitorDesktop, publishPackage, resolveBuildSource, stageDesktop } from '../janitor/build.mjs'

const roots = []
const temp = () => { const root = mkdtempSync(path.join(os.tmpdir(), 'janitor-desktop-test-')); roots.push(root); return root }
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }) })
const bytes = Buffer.from('new appimage')
const digest = createHash('sha256').update(bytes).digest('hex')
const assetName = 'janitor-desktop-1.0.1-linux-x86_64.AppImage'
const url = name => `https://github.com/reck74/Janitor-Agent/releases/download/v1.0.1/${name}`
const release = () => ({ tag_name: 'v1.0.1', draft: false, prerelease: false, assets: [
  { name: assetName, browser_download_url: url(assetName) },
  { name: `${assetName}.sha256`, browser_download_url: url(`${assetName}.sha256`) }
] })
function fixture() {
  const root = temp(), target = path.join(root, 'janitor-desktop.AppImage')
  writeFileSync(target, 'old appimage', { mode: 0o755 })
  const runtimeRoot = path.join(root, 'runtime'); mkdirSync(path.join(runtimeRoot, 'scripts'), { recursive: true })
  writeFileSync(path.join(runtimeRoot, 'janitor_cli.py'), '# fixture')
  writeFileSync(path.join(runtimeRoot, 'scripts/janitor'), '#!/bin/sh\nexit 0\n', { mode: 0o755 })
  return { root, target, runtimeRoot, home: path.join(root, 'home') }
}
const fetcher = async resource => new Response(resource.endsWith('.sha256') ? `${digest}  ${assetName}\n` : bytes)
async function preparedFixture() {
  const fixtureData = fixture()
  const prepared = await prepareUpdate({ selection: selectRelease(release(), 'x64'), target: fixtureData.target }, fetcher)
  return { ...fixtureData, ...prepared, lock: acquireLock(fixtureData.home) }
}

describe('Janitor release ownership', () => {
  it('selects only the stable fork artifact and checksum for this architecture', () => {
    expect(selectRelease(release(), 'x64').version).toBe('1.0.1')
    const foreign = release(); foreign.assets[0].browser_download_url = 'https://github.com/NousResearch/hermes-agent/a.AppImage'
    expect(() => selectRelease(foreign, 'x64')).toThrow(/outside/)
    expect(() => selectRelease({ ...release(), prerelease: true }, 'x64')).toThrow(/stable/)
    expect(() => selectRelease(release(), 'arm64')).toThrow(/exactly one/)
  })
  it('orders stable numeric versions and rejects prerelease branding', () => {
    expect(isNewer('1.0.10', '1.0.2')).toBe(true)
    expect(isNewer('1.0.2', '1.0.2')).toBe(false)
    expect(() => isNewer('1.0.2-janitor.1', '1.0.1')).toThrow(/stable/)
  })
  it('never takes over an external package or symlink', () => {
    expect(() => assertOwnedAppImage('/usr/bin/janitor-desktop')).toThrow(/outside/)
    const { root, target } = fixture(), alias = path.join(root, 'alias.AppImage')
    symlinkSync(target, alias)
    expect(() => assertOwnedAppImage(alias)).toThrow(/regular file/)
  })
  it('binds a multi-file checksum list to the exact selected filename', () => {
    expect(checksumFor(`${'0'.repeat(64)}  other.AppImage\n${digest} *${assetName}`, assetName)).toBe(digest)
    expect(() => checksumFor(`${digest}  other.AppImage`, assetName)).toThrow(/identify/)
  })
})

describe('Janitor AppImage transaction', () => {
  it('verifies before touching the running package', async () => {
    const plan = await preparedFixture()
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
    const calls = []
    const result = await applyPrepared(plan, { runRuntime: async launcher => calls.push(launcher), relaunch: async () => calls.push('relaunch') })
    expect(result).toMatchObject({ ok: true, runtimeUpdated: true, desktopUpdated: true })
    expect(calls).toEqual([path.join(plan.runtimeRoot, 'scripts/janitor'), 'relaunch'])
    expect(readFileSync(plan.target)).toEqual(bytes)
    expect(readFileSync(result.backup, 'utf8')).toBe('old appimage')
    expect(existsSync(plan.lock.directory)).toBe(false)
  })
  it('propagates remote gateway ownership to the runtime update', async () => {
    const plan = { ...await preparedFixture(), noGatewayRestart: true }
    let runtimeArgs
    const result = await applyPrepared(plan, {
      runRuntime: async (...args) => { runtimeArgs = args }, relaunch: async () => {}
    })
    expect(result.ok).toBe(true)
    expect(runtimeArgs).toEqual([path.join(plan.runtimeRoot, 'scripts/janitor'), plan.home, plan.version, true])
  })
  it('runs the Janitor command with an exact release and without rebuilding Desktop', async () => {
    const plan = { ...await preparedFixture(), noGatewayRestart: true }
    const observation = path.join(plan.root, 'runtime-command.json')
    writeFileSync(path.join(plan.runtimeRoot, 'scripts/janitor'), `#!/usr/bin/env node
require('fs').writeFileSync(${JSON.stringify(observation)}, JSON.stringify({args:process.argv.slice(2),tag:process.env._JANITOR_UPDATE_TARGET_TAG,skip:process.env._JANITOR_SKIP_DESKTOP_BUILD,home:process.env.JANITOR_HOME}));
`, { mode: 0o755 })
    const result = await applyPrepared(plan, { relaunch: async () => {} })
    expect(result.ok).toBe(true)
    expect(JSON.parse(readFileSync(observation, 'utf8'))).toEqual({ args: ['update', '--yes', '--no-gateway-restart'], tag: 'v1.0.1', skip: '1', home: plan.home })
  })
  it('restores the old AppImage if the prepared file disappears during runtime update', async () => {
    const plan = await preparedFixture()
    const result = await applyPrepared(plan, {
      runRuntime: async () => rmSync(plan.file), relaunch: async () => { throw new Error('must not relaunch') }
    })
    expect(result).toMatchObject({ ok: false, runtimeUpdated: true, desktopUpdated: false })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
  it('leaves the original package on download failure and cleans staging', async () => {
    const data = fixture()
    await expect(prepareUpdate({ selection: selectRelease(release(), 'x64'), target: data.target }, async () => new Response('', { status: 503 }))).rejects.toThrow(/503/)
    expect(readdirSync(data.root).filter(name => name.startsWith('.janitor-update-'))).toEqual([])
    expect(readFileSync(data.target, 'utf8')).toBe('old appimage')
  })
  it('rejects a bad hash before runtime execution', async () => {
    const data = fixture()
    await expect(prepareUpdate({ selection: selectRelease(release(), 'x64'), target: data.target }, async resource =>
      new Response(resource.endsWith('.sha256') ? `${'0'.repeat(64)}  ${assetName}` : bytes))).rejects.toThrow(/checksum/)
    expect(readFileSync(data.target, 'utf8')).toBe('old appimage')
  })
  it('rejects tampering between download and apply', async () => {
    const plan = await preparedFixture(); writeFileSync(plan.file, 'tampered')
    const result = await applyPrepared(plan, { runRuntime: async () => { throw new Error('must not run') } })
    expect(result).toMatchObject({ ok: false, runtimeUpdated: false, desktopUpdated: false })
    expect(result.error).toMatch(/changed/)
  })
  it('does not replace or relaunch after runtime failure', async () => {
    const plan = await preparedFixture()
    const result = await applyPrepared(plan, { runRuntime: async () => { throw new Error('runtime failed') }, relaunch: async () => { throw new Error('must not run') } })
    expect(result).toMatchObject({ ok: false, runtimeUpdated: false, desktopUpdated: false })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
  it('rolls the AppImage back and reports partial runtime success on failed relaunch', async () => {
    const plan = await preparedFixture()
    const result = await applyPrepared(plan, { runRuntime: async () => {}, relaunch: async () => { throw new Error('cannot launch') } })
    expect(result).toMatchObject({ ok: false, runtimeUpdated: true, desktopUpdated: false })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
  it('never persists arbitrary runtime stderr in the update result', async () => {
    const plan = await preparedFixture()
    const secret = 'MINIMAX_API_KEY=must-never-appear'
    writeFileSync(path.join(plan.runtimeRoot, 'scripts/janitor'), `#!/bin/sh\nprintf '%s' '${secret}' >&2\nexit 19\n`, { mode: 0o755 })
    const result = await applyPrepared(plan)
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/exit 19/)
    expect(result.error).not.toContain(secret)
    expect(readFileSync(path.join(plan.home, '.janitor-desktop-update-result.json'), 'utf8')).not.toContain(secret)
  })
  it('recovers a dead owner, restores an interrupted swap, and preserves the receipt outcome', async () => {
    const plan = await preparedFixture()
    recordPrepared(plan.lock, plan)
    const ownerFile = path.join(plan.lock.directory, 'owner.json')
    const owner = JSON.parse(readFileSync(ownerFile, 'utf8'))
    writeFileSync(ownerFile, JSON.stringify({ ...owner, bootId: 'previous-boot' }))
    renameSync(plan.target, `${plan.target}.janitor-previous-${plan.lock.token}`)
    renameSync(plan.file, plan.target)
    writeFileSync(path.join(plan.lock.directory, 'transaction.json'), JSON.stringify({ token: plan.lock.token,
      phase: 'swapping', runtimeUpdated: true, desktopUpdated: false, target: plan.target, downloadDirectory: plan.directory }))
    const result = recoverInterruptedUpdate(plan.home)
    expect(result).toMatchObject({ ok: false, interrupted: true, runtimeUpdated: true, desktopUpdated: false })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
    expect(existsSync(plan.lock.directory)).toBe(false)
    expect(existsSync(plan.directory)).toBe(false)
    const next = acquireLock(plan.home); expect(next.token).not.toBe(plan.lock.token); releaseLock(next)
  })
  it('marks runtime state unknown after interruption and refuses to recover a live owner', async () => {
    const plan = await preparedFixture()
    recordPrepared(plan.lock, plan)
    expect(recoverInterruptedUpdate(plan.home)).toBe(null)
    const ownerFile = path.join(plan.lock.directory, 'owner.json'), owner = JSON.parse(readFileSync(ownerFile, 'utf8'))
    writeFileSync(ownerFile, JSON.stringify({ ...owner, bootId: 'previous-boot' }))
    writeFileSync(path.join(plan.lock.directory, 'transaction.json'), JSON.stringify({ token: plan.lock.token, phase: 'runtime', target: plan.target }))
    expect(recoverInterruptedUpdate(plan.home)).toMatchObject({ runtimeUpdateUnknown: true, interrupted: true })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
  it('transfers ownership before readiness and refuses a foreign handoff token', () => {
    const lock = acquireLock(path.join(temp(), 'home'))
    expect(() => adoptLock({ ...lock, token: 'foreign' }, process.pid)).toThrow(/another process/)
    expect(existsSync(path.join(lock.directory, 'ready'))).toBe(false)
    adoptLock(lock, process.pid)
    expect(existsSync(path.join(lock.directory, 'ready'))).toBe(true)
    expect(() => acquireLock(path.dirname(lock.directory))).toThrow(/owns/)
    releaseLock(lock)
  })
  it('protects a distinct live worker and recovers its token after a process crash', async () => {
    const lock = acquireLock(path.join(temp(), 'home'))
    const moduleUrl = new URL('../janitor/update.mjs', import.meta.url).href
    const code = `import {adoptLock} from ${JSON.stringify(moduleUrl)};adoptLock(JSON.parse(process.argv[1]),Number(process.argv[2]));console.log('ready');setInterval(()=>{},1000);`
    const child = spawn(process.execPath, ['--input-type=module', '-e', code, JSON.stringify(lock), String(process.pid)], { stdio: ['ignore', 'pipe', 'pipe'] })
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Worker did not adopt its lock')), 10000)
        child.stdout.once('data', () => { clearTimeout(timer); resolve() })
        child.once('error', error => { clearTimeout(timer); reject(error) })
      })
      expect(JSON.parse(readFileSync(path.join(lock.directory, 'owner.json'), 'utf8')).pid).toBe(child.pid)
      expect(() => acquireLock(path.dirname(lock.directory))).toThrow(/owns/)
      const exited = new Promise(resolve => child.once('exit', resolve))
      child.kill('SIGKILL'); await exited
      const next = acquireLock(path.dirname(lock.directory))
      expect(next.recovered).toBe(true)
      expect(next.token).not.toBe(lock.token)
      releaseLock(next)
    } finally { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL') }
  })
  it('refuses concurrent owners and never releases another token', () => {
    const home = path.join(temp(), 'home'), lock = acquireLock(home)
    expect(() => acquireLock(home)).toThrow(/owns/)
    releaseLock({ ...lock, token: 'foreign' }); expect(existsSync(lock.directory)).toBe(true)
    releaseLock(lock); expect(existsSync(lock.directory)).toBe(false)
  })
})

it('launcher diagnostics reject a non-executable artifact without changing it', () => {
  const root = temp(), desktop = path.join(root, 'desktop'), releaseRoot = path.join(desktop, 'release')
  mkdirSync(releaseRoot, { recursive: true })
  const binary = path.join(releaseRoot, assetName); writeFileSync(binary, 'fixture', { mode: 0o644 })
  writeFileSync(path.join(releaseRoot, 'janitor-release.json'), JSON.stringify({ janitorVersion: '1.0.1', upstreamVersion: '0.22.2' }))
  const launcher = path.resolve(import.meta.dirname, '../../../skills/janitor-desktop-launcher/scripts/launch.sh')
  const env = { ...process.env, JANITOR_DESKTOP_DIR: desktop, JANITOR_HOME: path.join(root, 'not-created') }
  expect(() => execFileSync('bash', [launcher, '--print-path'], { env, stdio: 'pipe' })).toThrow()
  expect(() => execFileSync('bash', [launcher, '--version'], { env, stdio: 'pipe' })).toThrow()
  expect(statSync(binary).mode & 0o777).toBe(0o644)
  expect(existsSync(env.JANITOR_HOME)).toBe(false)
})


it('stages one Janitor identity without changing the upstream sources', () => {
  const root = temp(), source = path.join(root, 'source'), stage = path.join(root, 'stage')
  const files = {
    'apps/desktop/src/components/desktop-install-overlay.tsx': "import { useI18n } from '@/i18n'",
    'apps/desktop/janitor/renderer/install-i18n.ts': '// fork copy',
    'apps/desktop/electron/entry.ts': '// upstream entry',
    'apps/desktop/electron/bootstrap-runner.ts': '// upstream bootstrap',
    'apps/desktop/electron/source-backend.ts': '// upstream backend',
    'apps/desktop/electron/updater/checkout.ts': '// upstream update',
    'apps/desktop/electron/main.ts': "const ACTIVE_HERMES_ROOT = path.join(HERMES_HOME, 'hermes-agent')",
    'apps/desktop/electron-builder.config.cjs': 'module.exports = {}',
    'apps/desktop/package.json': JSON.stringify({ name: 'hermes', version: '0.0.0' }),
    'apps/desktop/tsconfig.electron.json': JSON.stringify({ include: ['electron'] }),
    'janitor_ext/release.json': JSON.stringify({ janitorVersion: '1.0.0', upstreamVersion: '0.22.2' }),
    'assets/janitor/janitor_avatar.png': 'image fixture',
    'apps/desktop/janitor/product-identity.cjs': 'module.exports = {displayName:"Janitor Agent"}',
    'apps/desktop/janitor/entry.ts': '// Janitor entry',
    'apps/desktop/janitor/bootstrap-runner.ts': '// Janitor bootstrap',
    'apps/desktop/janitor/source-backend.ts': '// Janitor backend',
    'apps/desktop/public/keep.txt': 'public fixture',
    'apps/desktop/assets/keep.txt': 'assets fixture'
  }
  for (const [file, text] of Object.entries(files)) {
    const target = path.join(source, file); mkdirSync(path.dirname(target), { recursive: true }); writeFileSync(target, text)
  }
  stageDesktop(source, stage)
  expect(readFileSync(path.join(source, 'apps/desktop/electron/main.ts'), 'utf8')).toContain("'hermes-agent'")
  expect(readFileSync(path.join(stage, 'apps/desktop/electron/main.ts'), 'utf8')).toContain("'janitor-core'")
  expect(readFileSync(path.join(stage, 'apps/desktop/electron/entry.upstream.ts'), 'utf8')).toBe('// upstream entry')
  expect(readFileSync(path.join(stage, 'apps/desktop/electron/entry.ts'), 'utf8')).toBe('// Janitor entry')
  expect(JSON.parse(readFileSync(path.join(stage, 'apps/desktop/package.json'), 'utf8')).version).toBe('1.0.0')
  expect(JSON.parse(readFileSync(path.join(source, 'apps/desktop/package.json'), 'utf8')).version).toBe('0.0.0')
})

it('publishes a completed package atomically while retaining unrelated versions', () => {
  const root = temp(), prepared = path.join(root, 'prepared'), destination = path.join(root, 'release')
  mkdirSync(path.join(prepared, 'linux-unpacked'), { recursive: true })
  mkdirSync(path.join(destination, 'linux-unpacked'), { recursive: true })
  writeFileSync(path.join(prepared, assetName), 'complete new appimage')
  writeFileSync(path.join(prepared, 'linux-unpacked/janitor-desktop'), 'new native app')
  writeFileSync(path.join(destination, 'linux-unpacked/janitor-desktop'), 'previous native app')
  writeFileSync(path.join(destination, 'janitor-desktop-1.0.0-linux-x86_64.AppImage'), 'previous version')
  publishPackage(prepared, destination)
  expect(readFileSync(path.join(destination, assetName), 'utf8')).toBe('complete new appimage')
  expect(readFileSync(path.join(destination, 'linux-unpacked/janitor-desktop'), 'utf8')).toBe('new native app')
  expect(readFileSync(path.join(destination, 'janitor-desktop-1.0.0-linux-x86_64.AppImage'), 'utf8')).toBe('previous version')
  expect(readdirSync(destination).some(name => name.startsWith('.janitor-package-'))).toBe(false)
})


describe('Janitor recovery audit regressions', () => {
  it('rejects a dirty release source before staging or compiling', () => {
    const source = temp()
    const git = args => execFileSync('git', args, { cwd: source, stdio: 'pipe' })
    git(['init', '-q']); git(['config', 'user.email', 'fixture@example.invalid']); git(['config', 'user.name', 'Fixture'])
    writeFileSync(path.join(source, 'source'), 'committed'); git(['add', '.']); git(['commit', '-qm', 'fixture'])
    writeFileSync(path.join(source, 'source'), 'uncommitted')
    expect(() => buildJanitorDesktop({ source })).toThrow(/clean|dirty/i)
  })
  it('rolls back when the new executable spawns and immediately exits with 42', async () => {
    const plan = await preparedFixture()
    const crash = Buffer.from('#!/bin/sh\nexit 42\n')
    writeFileSync(plan.file, crash, { mode: 0o755 }); plan.expectedHash = createHash('sha256').update(crash).digest('hex')
    const result = await applyPrepared(plan, { runRuntime: async () => {} })
    expect(result).toMatchObject({ ok: false, runtimeUpdated: true, desktopUpdated: false })
    expect(result.error).toMatch(/42/)
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
  it('skips a partial newer artifact and launches the complete older candidate', () => {
    const root = temp(), desktop = path.join(root, 'desktop'), releaseRoot = path.join(desktop, 'release')
    mkdirSync(releaseRoot, { recursive: true })
    const valid = path.join(releaseRoot, 'janitor-desktop-1.0.0-linux-x86_64.AppImage')
    writeFileSync(valid, '#!/bin/sh\nprintf valid\n', { mode: 0o755 })
    writeFileSync(`${valid}.json`, JSON.stringify({ janitorVersion: '1.0.0', upstreamVersion: '0.22.2', artifact: path.basename(valid) }))
    writeFileSync(path.join(releaseRoot, assetName), 'partial', { mode: 0o644 })
    const launcher = path.resolve(import.meta.dirname, '../../../skills/janitor-desktop-launcher/scripts/launch.sh')
    const env = { ...process.env, JANITOR_DESKTOP_DIR: desktop }
    expect(execFileSync('bash', [launcher, '--print-path'], { env, encoding: 'utf8' }).trim()).toBe(valid)
    expect(execFileSync('bash', [launcher], { env, encoding: 'utf8' })).toBe('valid')
  })
})

function gitSource() {
  const source = temp()
  const git = args => execFileSync('git', args, { cwd: source, stdio: 'pipe' })
  git(['init', '-q']); git(['config', 'user.email', 'fixture@example.invalid']); git(['config', 'user.name', 'Fixture'])
  mkdirSync(path.join(source, 'scripts')); writeFileSync(path.join(source, 'scripts/bootstrap.sh'), '#!/bin/sh\nexit 0\n')
  git(['add', '.']); git(['commit', '-qm', 'fixture'])
  return { source, git }
}
describe('release source provenance', () => {
  it('refuses unfinished merges even with a resolved clean index', () => {
    const { source, git } = gitSource()
    writeFileSync(path.join(source, '.git/MERGE_HEAD'), git(['rev-parse', 'HEAD']))
    expect(() => resolveBuildSource(source)).toThrow(/completed merge/)
  })
  it('requires the exact bootstrap bytes from the public immutable fork commit', () => {
    const { source, git } = gitSource(), commit = git(['rev-parse', 'HEAD']).toString().trim()
    let requested
    const run = (command, args, options) => {
      if (command !== 'curl') return execFileSync(command, args, options)
      requested = args.at(-1)
      return readFileSync(path.join(source, 'scripts/bootstrap.sh'))
    }
    const identity = resolveBuildSource(source, { run })
    expect(requested).toBe(`https://raw.githubusercontent.com/reck74/Janitor-Agent/${commit}/scripts/bootstrap.sh`)
    expect(identity).toMatchObject({ commit, buildKind: 'release', dirty: false, merging: false })
    expect(identity.trackedFiles.has('scripts/bootstrap.sh')).toBe(true)
    expect(() => resolveBuildSource(source, { run: (command, args, options) => command === 'curl' ? Buffer.from('old installer') : execFileSync(command, args, options) })).toThrow(/differs/)
  })
  it('allows dirty development builds only with explicit development identity and no remote check', () => {
    const { source } = gitSource()
    writeFileSync(path.join(source, 'untracked'), 'local')
    const identity = resolveBuildSource(source, { development: true })
    expect(identity).toMatchObject({ buildKind: 'development', dirty: true })
    expect(() => resolveBuildSource(source)).toThrow(/clean/)
  })
})

describe('native readiness handshake', () => {
  function executable(code) {
    const root = temp(), file = path.join(root, 'native.AppImage')
    writeFileSync(file, `#!/usr/bin/env node\n${code}`, { mode: 0o755 })
    return { root, file }
  }
  const confirm = version => `require('fs').writeFileSync(process.env.JANITOR_UPDATE_READY_PATH,JSON.stringify({token:process.env.JANITOR_UPDATE_READY_TOKEN,product:'Janitor Agent',version:${JSON.stringify(version)},pid:process.pid}));`
  it('rejects a wrong version even after the executable starts successfully', async () => {
    const { root, file } = executable(confirm('0.9.0') + 'setInterval(()=>{},1000);')
    await expect(relaunch(file, [], root, '1.0.1', root, { timeoutMs: 1000, stableMs: 100 })).rejects.toThrow(/identity/)
  })
  it('rejects a process that reports readiness and then crashes', async () => {
    const { root, file } = executable(confirm('1.0.1') + 'setTimeout(()=>process.exit(42),100);')
    await expect(relaunch(file, [], root, '1.0.1', root, { timeoutMs: 1000, stableMs: 300 })).rejects.toThrow(/42/)
  })
  it('requires readiness, rather than only a long-lived process', async () => {
    const { root, file } = executable('setInterval(()=>{},1000);')
    await expect(relaunch(file, [], root, '1.0.1', root, { timeoutMs: 150, stableMs: 100 })).rejects.toThrow(/readiness/)
  })
  it('accepts the matching version only after the readiness stability interval', async () => {
    const { root, file } = executable(confirm('1.0.1') + 'setInterval(()=>{},1000);')
    try {
      await relaunch(file, [], root, '1.0.1', root, { timeoutMs: 1000, stableMs: 100 })
      const ready = JSON.parse(readFileSync(path.join(root, 'application-ready.json'), 'utf8'))
      expect(ready.version).toBe('1.0.1')
    } finally {
      const ready = JSON.parse(readFileSync(path.join(root, 'application-ready.json'), 'utf8'))
      try { process.kill(-ready.pid, 'SIGTERM') } catch { /* already exited */ }
    }
  })
  it('restores the previous AppImage after an updater crash during unconfirmed relaunch', async () => {
    const plan = await preparedFixture()
    const ownerFile = path.join(plan.lock.directory, 'owner.json'), owner = JSON.parse(readFileSync(ownerFile, 'utf8'))
    writeFileSync(ownerFile, JSON.stringify({ ...owner, bootId: 'previous-boot' }))
    renameSync(plan.target, `${plan.target}.janitor-previous-${plan.lock.token}`); renameSync(plan.file, plan.target)
    writeFileSync(path.join(plan.lock.directory, 'transaction.json'), JSON.stringify({ token: plan.lock.token, phase: 'relaunch', runtimeUpdated: true, desktopUpdated: true, target: plan.target }))
    expect(recoverInterruptedUpdate(plan.home)).toMatchObject({ runtimeUpdated: true, desktopUpdated: false, interrupted: true })
    expect(readFileSync(plan.target, 'utf8')).toBe('old appimage')
  })
})

it('verifies binary checksums and commit provenance as one publishable release unit', async () => {
  const { verifyArtifacts } = await import('./janitor-artifacts.mjs')
  const directory = temp(), commit = 'a'.repeat(40)
  const artifact = 'janitor-desktop-1.0.1-linux-x86_64.AppImage', file = path.join(directory, artifact)
  const metadata = { commit, repository: 'reck74/Janitor-Agent', buildKind: 'release', sourceDirty: false, janitorVersion: '1.0.1', upstreamRef: 'b'.repeat(40) }
  writeFileSync(file, bytes, { mode: 0o755 })
  writeFileSync(`${file}.sha256`, `${digest}  ${artifact}\n`)
  writeFileSync(`${file}.json`, JSON.stringify({ ...metadata, artifact }))
  writeFileSync(path.join(directory, 'janitor-release.json'), JSON.stringify(metadata))
  expect(verifyArtifacts({ directory, commit })).toMatchObject({ commit, artifact, sha256: digest })
  expect(() => verifyArtifacts({ directory, commit: 'c'.repeat(40) })).toThrow(/commit/)
  writeFileSync(file, 'tampered')
  expect(() => verifyArtifacts({ directory, commit })).toThrow(/checksum/)
})
