// Build Janitor Desktop from the untouched upstream apps/desktop.
//
//   node apps/desktop-janitor/scripts/build.mjs [--skip-build] [electron-builder args...]
//   node apps/desktop-janitor/scripts/build.mjs --check            # verify every patch, write nothing
//   node apps/desktop-janitor/scripts/build.mjs --restore [--force] # undo an interrupted build
//   e.g. node apps/desktop-janitor/scripts/build.mjs --linux AppImage
//
// apps/desktop stays byte-identical to upstream. For the duration of the build
// this script copies the Janitor assets over it and applies the brand patches
// (brand/: P1-P8, directive #17) inside one journaled transaction
// (scripts/patch-engine.mjs), runs upstream's own build and electron-builder
// with upstream's `build` config deep-merged with electron-builder.janitor.json,
// then restores every file it touched — in `finally`, or on the next run /
// `--restore` if the process was killed.
//
// extraMetadata.productName is "Janitor" (plan 4.3/4.4): Electron derives the
// userData directory from it, so the app keeps its state in ~/.config/Janitor
// and never shares single-instance lock, window state or connection settings
// with a real Hermes Desktop install. Pre-1.0 Janitor desktop builds used
// ~/.config/Hermes; their window/connection settings are not carried over.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { allPatches } from './brand-patches.mjs'
import { beginTransaction, checkPatches, computePatchedFiles, recoverInterrupted, restoreJournal } from './patch-engine.mjs'
import { checkTranspiles } from './transpile-check.mjs'

export const OVERLAY_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const APP_DIR = path.resolve(OVERLAY_DIR, '..', 'desktop')

// [overlay source, apps/desktop target]
export const OVERLAY_FILES = [
  ['assets/janitor-mark.png', 'assets/janitor-icon.png'],
  ['assets/janitor-mark.png', 'public/apple-touch-icon.png'],
  ['assets/janitor-mark.png', 'public/nous-girl.jpg'],
  ['assets/filler-bg0.jpg', 'public/ds-assets/filler-bg0.jpg']
]

const isPlainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)

export function mergeBuilderConfig(base, overrides) {
  const merged = { ...base }

  for (const [key, value] of Object.entries(overrides)) {
    merged[key] = isPlainObject(value) && isPlainObject(base[key]) ? mergeBuilderConfig(base[key], value) : value
  }

  return merged
}

export function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

export function janitorBuilderConfig(appDir = APP_DIR, overlayDir = OVERLAY_DIR) {
  const upstream = readJson(path.join(appDir, 'package.json')).build
  const overrides = readJson(path.join(overlayDir, 'electron-builder.janitor.json'))

  return mergeBuilderConfig(upstream, overrides)
}

/**
 * Copy the overlay assets and apply `patches` to appDir in one journaled
 * transaction. Every anchor is verified before anything is written. Returns
 * restore(), which puts every touched file back.
 */
export function applyOverlay(appDir = APP_DIR, overlayDir = OVERLAY_DIR, { patches = [], journalDir, log } = {}) {
  recoverInterrupted(appDir, { journalDir, log })
  const writes = computePatchedFiles(appDir, patches)

  for (const [source, target] of OVERLAY_FILES) {
    writes.set(target, fs.readFileSync(path.join(overlayDir, source)))
  }

  return beginTransaction(appDir, writes, { journalDir, log })
}

/** --check: anchors, transforms (catalog guard) and transpilation; never writes. */
export function runCheck(appDir = APP_DIR, patches = allPatches(), out = console.log) {
  const { ok, results } = checkPatches(appDir, patches)

  for (const result of results) {
    out(`${result.ok ? 'ok  ' : 'FAIL'} ${result.id}${result.ok ? '' : `\n     ${result.error.replace(/\n/g, '\n     ')}`}`)
  }

  let transpileOk = true

  if (ok) {
    for (const [file, content] of computePatchedFiles(appDir, patches)) {
      const result = checkTranspiles(content.toString('utf8'), file, appDir)

      if (result.ok === false) {
        transpileOk = false
        out(`FAIL transpile ${file} (${result.via}): ${result.error}`)
      } else if (result.ok === null && !file.endsWith('.html')) {
        out(`skip transpile ${file}: ${result.reason}`)
      }
    }
  }

  const failed = results.filter(r => !r.ok).length
  out(`${results.length - failed}/${results.length} patches resolve against ${appDir}${transpileOk ? '' : '; transpile FAILED'}`)

  return ok && transpileOk
}

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' })

  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} exited with ${result.status}`)
  }
}

function main(argv) {
  const log = message => console.log(`[janitor-desktop] ${message}`)

  if (argv.includes('--check')) {
    return runCheck() ? 0 : 1
  }

  if (argv.includes('--restore')) {
    const restored = restoreJournal(APP_DIR, { force: argv.includes('--force') })
    log(restored ? `restored ${restored.length} file(s)` : 'no interrupted build to restore')

    return 0
  }

  const skipBuild = argv.includes('--skip-build')
  const builderArgs = argv.filter(arg => arg !== '--skip-build')
  const configPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-desktop-')), 'electron-builder.json')

  fs.writeFileSync(configPath, JSON.stringify(janitorBuilderConfig(), null, 2))

  const restore = applyOverlay(APP_DIR, OVERLAY_DIR, { patches: allPatches(), log })

  try {
    if (!skipBuild) {
      run('npm', ['run', 'build'], APP_DIR)
    }

    run('npm', ['run', 'prebuilder'], APP_DIR)
    run(process.execPath, ['scripts/run-electron-builder.mjs', '--config', configPath, ...builderArgs], APP_DIR)
  } finally {
    restore()
  }

  return 0
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main(process.argv.slice(2))
  } catch (error) {
    console.error(`[janitor-desktop] ${error.message}`)
    process.exit(1)
  }
}
