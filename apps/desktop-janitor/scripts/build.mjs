// Build Janitor Desktop from the untouched upstream apps/desktop.
//
//   node apps/desktop-janitor/scripts/build.mjs [--skip-build] [electron-builder args...]
//   e.g. node apps/desktop-janitor/scripts/build.mjs --linux AppImage
//
// apps/desktop stays byte-identical to upstream. For the duration of the build
// this script copies the Janitor assets over it, runs upstream's own build and
// electron-builder with upstream's `build` config deep-merged with
// electron-builder.janitor.json, then restores every file it touched.
//
// extraMetadata.productName stays equal to upstream's productName on purpose:
// Electron derives the userData directory from it, and pre-1.0 Janitor desktop
// builds used upstream's metadata, so changing it would orphan their settings.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

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

export function applyOverlay(appDir = APP_DIR, overlayDir = OVERLAY_DIR) {
  const saved = new Map()

  for (const [, target] of OVERLAY_FILES) {
    const dest = path.join(appDir, target)

    if (!saved.has(dest)) {
      saved.set(dest, fs.existsSync(dest) ? fs.readFileSync(dest) : null)
    }
  }

  for (const [source, target] of OVERLAY_FILES) {
    fs.copyFileSync(path.join(overlayDir, source), path.join(appDir, target))
  }

  return () => {
    for (const [dest, content] of saved) {
      if (content === null) {
        fs.rmSync(dest, { force: true })
      } else {
        fs.writeFileSync(dest, content)
      }
    }
  }
}

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' })

  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} exited with ${result.status}`)
  }
}

function main(argv) {
  const skipBuild = argv.includes('--skip-build')
  const builderArgs = argv.filter(arg => arg !== '--skip-build')
  const configPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-desktop-')), 'electron-builder.json')

  fs.writeFileSync(configPath, JSON.stringify(janitorBuilderConfig(), null, 2))

  const restore = applyOverlay()

  try {
    if (!skipBuild) {
      run('npm', ['run', 'build'], APP_DIR)
    }

    run('npm', ['run', 'prebuilder'], APP_DIR)
    run(process.execPath, ['scripts/run-electron-builder.mjs', '--config', configPath, ...builderArgs], APP_DIR)
  } finally {
    restore()
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main(process.argv.slice(2))
  } catch (error) {
    console.error(`[janitor-desktop] ${error.message}`)
    process.exit(1)
  }
}
