#!/usr/bin/env node
// Build a fork-owned source overlay without modifying the Hermes checkout.
import { constants, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const defaultSource = path.resolve(import.meta.dirname, '../../..')
export function stageDesktop(source, stage, { copyDependencies = false, trackedFiles } = {}) {
  source = path.resolve(source)
  const skip = new Set(['.git', '.cache', '.build', 'node_modules', '__pycache__', '.venv', 'venv', '.pytest_cache', '.hermes', '.ruff_cache', '.codebase-memory'])
  cpSync(source, stage, { recursive: true, filter: file => {
    const relative = path.relative(source, file)
    if (!relative) return true
    const parts = relative.split(path.sep)
    if (parts.some(part => skip.has(part))) return false
    if (trackedFiles && !trackedFiles.has(relative)) return false
    return !/^(apps\/desktop\/(?:build|dist|release)|hermes_cli\/web_dist|ui-tui\/dist)(\/|$)/.test(relative)
  } })
  const desktop = path.join(stage, 'apps/desktop')
  for (const name of ['electron/entry.ts', 'electron/bootstrap-runner.ts', 'electron/source-backend.ts', 'electron/updater/checkout.ts']) {
    const original = path.join(desktop, name)
    renameSync(original, original.replace(/\.ts$/, '.upstream.ts'))
    if (name === 'electron/updater/checkout.ts') {
      writeFileSync(original, "export * from './checkout.upstream'\nexport { createCheckoutStrategy } from '../../janitor/checkout'\n")
    } else cpSync(path.join(desktop, 'janitor', path.basename(name)), original)
  }
  renameSync(path.join(desktop, 'electron-builder.config.cjs'), path.join(desktop, 'electron-builder.upstream.cjs'))
  writeFileSync(path.join(desktop, 'electron-builder.config.cjs'), "module.exports = require('./janitor/packaging.cjs')\n")
  cpSync(path.join(desktop, 'janitor/product-identity.cjs'), path.join(desktop, 'product-identity.cjs'))
  const main = path.join(desktop, 'electron/main.ts')
  const text = readFileSync(main, 'utf8')
  const expected = "const ACTIVE_HERMES_ROOT = path.join(HERMES_HOME, 'hermes-agent')"
  if (text.split(expected).length !== 2) throw new Error('Desktop runtime-root contract changed; review the Janitor overlay')
  writeFileSync(main, text.replace(expected, "const ACTIVE_HERMES_ROOT = path.join(HERMES_HOME, 'janitor-core')"))
  const electronConfig = path.join(desktop, 'tsconfig.electron.json')
  const tsconfig = JSON.parse(readFileSync(electronConfig, 'utf8'))
  writeFileSync(electronConfig, JSON.stringify({ ...tsconfig, include: [...tsconfig.include, 'janitor', '../../janitor_ext/release.json'], exclude: [...(tsconfig.exclude || []), 'janitor/renderer'] }, null, 2) + '\n')
  const metadata = JSON.parse(readFileSync(path.join(source, 'janitor_ext/release.json'), 'utf8'))
  const pkgFile = path.join(desktop, 'package.json')
  const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'))
  writeFileSync(pkgFile, JSON.stringify({ ...pkg, productName: 'Janitor Agent', version: metadata.janitorVersion }, null, 2) + '\n')
  cpSync(path.join(source, 'assets/janitor/janitor_avatar.png'), path.join(desktop, 'assets/janitor-icon.png'))
  cpSync(path.join(source, 'assets/janitor/janitor_avatar.png'), path.join(desktop, 'assets/icon.png'))
  cpSync(path.join(source, 'assets/janitor/janitor_avatar.png'), path.join(desktop, 'public/apple-touch-icon.png'))
  for (const name of ['nous-girl.png', 'nous-girl-dark.png']) cpSync(path.join(source, 'assets/janitor/janitor_avatar.png'), path.join(desktop, 'public', name))
  mkdirSync(path.join(desktop, 'src/janitor'), { recursive: true })
  cpSync(path.join(desktop, 'janitor/renderer/install-i18n.ts'), path.join(desktop, 'src/janitor/install-i18n.ts'))
  const installOverlay = path.join(desktop, 'src/components/desktop-install-overlay.tsx')
  const overlaySource = readFileSync(installOverlay, 'utf8')
  const i18nImport = "import { useI18n } from '@/i18n'"
  if (overlaySource.split(i18nImport).length !== 2) throw new Error('Desktop install-selector contract changed; review the Janitor overlay')
  writeFileSync(installOverlay, overlaySource.replace(i18nImport, "import { useJanitorInstallI18n as useI18n } from '@/janitor/install-i18n'"))
  for (const workspace of ['', 'apps/desktop', 'apps/shared']) {
    const modules = path.join(source, workspace, 'node_modules')
    if (existsSync(modules)) {
      const target = path.join(stage, workspace, 'node_modules')
      // Packaging validates real dependency paths against this stage's lockfile.
      // Copy rather than weakening that check or exposing the developer's tree to rebuilds.
      if (copyDependencies) cpSync(modules, target, { recursive: true, verbatimSymlinks: true, mode: constants.COPYFILE_FICLONE })
      else symlinkSync(modules, target, 'dir')
    }
  }
  return { desktop, metadata }
}

// The packager may delete/recreate its unpacked output. It only sees a private
// stage; a failed compilation/package cannot erase the currently usable app.
export function publishPackage(prepared, destination) {
  mkdirSync(destination, { recursive: true })
  const pending = mkdtempSync(path.join(destination, '.janitor-package-'))
  try {
    for (const name of readdirSync(prepared)) cpSync(path.join(prepared, name), path.join(pending, name),
      { recursive: true, verbatimSymlinks: true, mode: constants.COPYFILE_FICLONE })
    for (const name of readdirSync(pending)) {
      const source = path.join(pending, name), target = path.join(destination, name)
      if (name.startsWith('linux-') && name.endsWith('-unpacked') && existsSync(target)) {
        const previous = `${target}.janitor-previous-${randomUUID()}`
        renameSync(target, previous)
        try { renameSync(source, target) } catch (error) { renameSync(previous, target); throw error }
        rmSync(previous, { recursive: true, force: true })
      } else renameSync(source, target)
    }
  } finally { rmSync(pending, { recursive: true, force: true }) }
}

export function resolveBuildSource(source, { development = false, run = execFileSync } = {}) {
  const git = args => run('git', args, { cwd: source, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  const commit = git(['rev-parse', 'HEAD'])
  const merging = existsSync(path.resolve(source, git(['rev-parse', '--git-path', 'MERGE_HEAD'])))
  const dirty = git(['status', '--porcelain', '--untracked-files=normal']) !== ''
  if (!development && (merging || dirty)) throw new Error('Release builds require a clean source tree and a completed merge; use --development for a non-distributable local build')
  const trackedFiles = new Set()
  for (const file of git(['ls-files', '-z']).split('\0').filter(Boolean)) {
    trackedFiles.add(file)
    let directory = path.dirname(file)
    while (directory !== '.') { trackedFiles.add(directory); directory = path.dirname(directory) }
  }
  if (!development) {
    // A reachable content-addressed bootstrap prevents a new UI shipping an old
    // installer. Compare bytes, not just HTTP 200 or an arbitrary branch name.
    const url = `https://raw.githubusercontent.com/reck74/Janitor-Agent/${commit}/scripts/bootstrap.sh`
    const remote = run('curl', ['--fail', '--location', '--silent', '--show-error', '--connect-timeout', '15', '--max-time', '60', url], { encoding: 'buffer', stdio: ['ignore', 'pipe', 'pipe'] })
    if (!Buffer.from(remote).equals(readFileSync(path.join(source, 'scripts/bootstrap.sh')))) throw new Error('The published commit bootstrap differs from this source tree')
  }
  return { commit, dirty, merging, buildKind: development ? 'development' : 'release', trackedFiles,
    releaseEpoch: git(['show', '-s', '--format=%ct', commit]) }
}

export function buildJanitorDesktop({ source = defaultSource, output, packageApp = true, keepStage = false, development = false, run = execFileSync } = {}) {
  if (process.platform !== 'linux') throw new Error('Janitor Desktop releases currently target Linux')
  const identity = resolveBuildSource(source, { development, run })
  const stage = mkdtempSync(path.join(os.tmpdir(), 'janitor-desktop-build-'))
  try {
    console.log('[Janitor Desktop] Preparing an isolated source and dependency stage…')
    const { desktop, metadata: sourceMetadata } = stageDesktop(source, stage, { copyDependencies: packageApp, trackedFiles: development ? undefined : identity.trackedFiles })
    const metadata = { ...sourceMetadata, buildKind: identity.buildKind, sourceDirty: identity.dirty, commit: identity.commit }
    if (development) metadata.janitorVersion += `-dev.${identity.commit.slice(0, 12)}`
    writeFileSync(path.join(stage, 'janitor_ext/release.json'), JSON.stringify(metadata, null, 2) + '\n')
    const packageFile = path.join(desktop, 'package.json')
    writeFileSync(packageFile, JSON.stringify({ ...JSON.parse(readFileSync(packageFile, 'utf8')), version: metadata.janitorVersion }, null, 2) + '\n')
    console.log('[Janitor Desktop] Validating renderer and Electron TypeScript…')
    const { commit, releaseEpoch } = identity
    const destination = path.resolve(output || path.join(source, development ? 'apps/desktop/release-development' : 'apps/desktop/release'))
    const env = { ...process.env, HERMES_RELEASE_EPOCH: releaseEpoch, GITHUB_SHA: commit, GITHUB_REF_NAME: 'main',
      HERMES_DESKTOP_VARIANT: '', HERMES_PAYLOAD_TAG: `v${metadata.janitorVersion}`,
      HERMES_PAYLOAD_VERSION: metadata.janitorVersion,
      JANITOR_DESKTOP_OUTPUT: path.join(stage, 'package-output') }
    // Do not inherit a foreign product/channel identity from a developer's shell.
    for (const key of ['HERMES_BUILD_COMMIT', '_HERMES_CHANNEL_REQUEST_JSON', 'HERMES_BUNDLE_ENV_JSON']) delete env[key]
    // A development AppImage is not a release tag. In particular, upstream's
    // Windows release-manifest hook only accepts its stable/canary tag grammar.
    if (development) delete env.HERMES_PAYLOAD_TAG
    run(process.execPath, [path.join(stage, 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.json', '--noEmit'], { cwd: desktop, env, stdio: 'inherit' })
    run(process.execPath, [path.join(stage, 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.electron.json', '--noEmit'], { cwd: desktop, env, stdio: 'inherit' })
    run(process.execPath, ['scripts/build.mjs'], { cwd: desktop, env, stdio: 'inherit' })
    if (packageApp) run(process.execPath, ['scripts/run-electron-builder.mjs', '--linux', 'AppImage', '--publish', 'never'],
      { cwd: desktop, env, stdio: 'inherit' })
    if (packageApp) {
      if (!development) {
        const finalSource = resolveBuildSource(source, { run })
        if (finalSource.commit !== commit) throw new Error('Source commit changed during the build; package was not published')
      }
      for (const name of readdirSync(env.JANITOR_DESKTOP_OUTPUT).filter(name => name.startsWith(`janitor-desktop-${metadata.janitorVersion}-linux-`) && name.endsWith('.AppImage'))) {
        const file = path.join(env.JANITOR_DESKTOP_OUTPUT, name)
        const hash = createHash('sha256').update(readFileSync(file)).digest('hex')
        writeFileSync(`${file}.sha256`, `${hash}  ${name}\n`)
        writeFileSync(`${file}.json`, JSON.stringify({ ...metadata, commit, artifact: name }, null, 2) + '\n')
      }
      writeFileSync(path.join(env.JANITOR_DESKTOP_OUTPUT, 'janitor-release.json'), JSON.stringify({ ...metadata, commit }, null, 2) + '\n')
      publishPackage(env.JANITOR_DESKTOP_OUTPUT, destination)
    }
    return { stage, output: packageApp ? destination : path.join(desktop, 'dist') }
  } finally { if (!keepStage && packageApp) rmSync(stage, { recursive: true, force: true }) }
}

if (path.resolve(process.argv[1] || '') === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { source: { type: 'string' }, output: { type: 'string' },
    'build-only': { type: 'boolean' }, 'keep-stage': { type: 'boolean' }, development: { type: 'boolean' } } })
  console.log(buildJanitorDesktop({ ...values, packageApp: !values['build-only'], keepStage: values['keep-stage'] }))
}
