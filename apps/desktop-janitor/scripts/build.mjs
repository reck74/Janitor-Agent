// Build Janitor Desktop from the untouched upstream apps/desktop.
//
//   node apps/desktop-janitor/scripts/build.mjs [--skip-build] [electron-builder args...]
//   e.g. node apps/desktop-janitor/scripts/build.mjs --linux AppImage
//
// apps/desktop stays byte-identical to upstream. For the duration of the build
// this script copies the Janitor assets over it, swaps upstream's
// electron-builder.config.cjs for a wrapper that deep-merges
// electron-builder.janitor.json into it, runs upstream's own build and
// packaging scripts, then restores every file it touched.
//
// extraMetadata.productName stays equal to upstream's productName on purpose:
// Electron derives the userData directory from it, and pre-1.0 Janitor desktop
// builds used upstream's metadata, so changing it would orphan their settings.

import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { janitorConfig, mergeBuilderConfig } = require('./builder-config.cjs')

export { mergeBuilderConfig }

export const OVERLAY_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const APP_DIR = path.resolve(OVERLAY_DIR, '..', 'desktop')

// upstream's run-electron-builder.mjs always packages with this file.
export const BUILDER_CONFIG = 'electron-builder.config.cjs'
export const UPSTREAM_BUILDER_CONFIG = 'electron-builder.upstream.cjs'

// [overlay source, apps/desktop target]
export const OVERLAY_FILES = [
  ['assets/janitor-mark.png', 'assets/janitor-icon.png'],
  ['assets/janitor-mark.png', 'public/apple-touch-icon.png'],
  ['assets/janitor-mark.png', 'public/nous-girl.png'],
  ['assets/janitor-mark.png', 'public/nous-girl-dark.png'],
  ['assets/filler-bg0.jpg', 'public/ds-assets/filler-bg0.jpg']
]

export function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

export function upstreamBuilderConfig(appDir = APP_DIR) {
  return createRequire(path.join(appDir, 'package.json'))(path.join(appDir, BUILDER_CONFIG))
}

export function janitorBuilderConfig(appDir = APP_DIR) {
  return janitorConfig(upstreamBuilderConfig(appDir))
}

function builderConfigWrapper() {
  const helper = JSON.stringify(path.join(OVERLAY_DIR, 'scripts', 'builder-config.cjs'))

  return [
    '// Written by apps/desktop-janitor/scripts/build.mjs for one build; restored afterwards.',
    `module.exports = require(${helper}).janitorConfig(require('./${UPSTREAM_BUILDER_CONFIG}'))`,
    ''
  ].join('\n')
}

export function applyOverlay(appDir = APP_DIR, overlayDir = OVERLAY_DIR) {
  const config = path.join(appDir, BUILDER_CONFIG)
  const upstreamCopy = path.join(appDir, UPSTREAM_BUILDER_CONFIG)
  const saved = new Map([
    [config, fs.readFileSync(config)],
    [upstreamCopy, null]
  ])

  for (const [, target] of OVERLAY_FILES) {
    const dest = path.join(appDir, target)

    if (!saved.has(dest)) {
      saved.set(dest, fs.existsSync(dest) ? fs.readFileSync(dest) : null)
    }
  }

  for (const [source, target] of OVERLAY_FILES) {
    fs.copyFileSync(path.join(overlayDir, source), path.join(appDir, target))
  }

  fs.writeFileSync(upstreamCopy, saved.get(config))
  fs.writeFileSync(config, builderConfigWrapper())

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
  const restore = applyOverlay()

  try {
    if (!skipBuild) {
      run('npm', ['run', 'build'], APP_DIR)
    }

    run('npm', ['run', 'builder', '--', ...builderArgs], APP_DIR)
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
