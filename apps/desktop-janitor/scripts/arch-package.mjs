// Arch Linux package for the Janitor desktop app (janitor-desktop-bin).
//
// Renders packaging/arch/PKGBUILD.in into a ready-to-build makepkg directory:
// the PKGBUILD with the release tag, pkgver and real sha256sums, the local
// sources (launcher, .desktop entry, the repo's LICENSE) and the published
// AppImage under its versioned local name, so `makepkg` finds every source
// without downloading anything.
//
//   node apps/desktop-janitor/scripts/arch-package.mjs --appimage <file> --tag <vX.Y.Z-janitor.N> --out <dir>

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url))

export const ARCH_DIR = path.resolve(SCRIPTS_DIR, '..', 'packaging', 'arch')
export const REPO_ROOT = path.resolve(SCRIPTS_DIR, '..', '..', '..')
export const APP_NAME = 'janitor-desktop'

const TAG_RE = /^v(\d+)\.(\d+)\.(\d+)-janitor\.(\d+)$/

/** `v0.21.5-janitor.1` → `0.21.5.janitor.1`; throws on anything else. */
export function pkgverFromTag(tag) {
  if (typeof tag !== 'string' || !TAG_RE.test(tag)) {
    throw new Error(`release tag must look like v<n>.<n>.<n>-janitor.<n>, got ${JSON.stringify(tag)}`)
  }

  return tag.slice(1).replaceAll('-', '.')
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

function copy(from, to, mode) {
  fs.copyFileSync(from, to, fs.constants.COPYFILE_FICLONE)
  fs.chmodSync(to, mode)
}

/**
 * Writes PKGBUILD + sources into outDir. Returns { pkgver, pkgbuild, appimage }.
 */
export function renderArchPackage({ appimage, tag, outDir, repoRoot = REPO_ROOT }) {
  const pkgver = pkgverFromTag(tag)

  if (!appimage || !fs.statSync(appimage).isFile()) {
    throw new Error(`AppImage not found: ${appimage}`)
  }

  fs.mkdirSync(outDir, { recursive: true })

  const localAppimage = path.join(outDir, `${APP_NAME}-${pkgver}.AppImage`)
  const launcher = path.join(outDir, 'janitor-desktop.sh')
  const desktop = path.join(outDir, 'Janitor.desktop')
  const license = path.join(outDir, 'LICENSE')

  if (path.resolve(appimage) !== path.resolve(localAppimage)) {
    copy(appimage, localAppimage, 0o755)
  }

  copy(path.join(ARCH_DIR, 'janitor-desktop.sh'), launcher, 0o755)
  copy(path.join(ARCH_DIR, 'Janitor.desktop'), desktop, 0o644)
  copy(path.join(repoRoot, 'LICENSE'), license, 0o644)

  const values = {
    TAG: tag,
    PKGVER: pkgver,
    SHA_APPIMAGE: sha256(localAppimage),
    SHA_LAUNCHER: sha256(launcher),
    SHA_DESKTOP: sha256(desktop),
    SHA_LICENSE: sha256(license)
  }

  const template = fs.readFileSync(path.join(ARCH_DIR, 'PKGBUILD.in'), 'utf8')

  const rendered = template.replace(/@([A-Z_]+)@/g, (match, key) => {
    if (!(key in values)) throw new Error(`unknown PKGBUILD.in placeholder ${match}`)

    return values[key]
  })

  const pkgbuild = path.join(outDir, 'PKGBUILD')
  fs.writeFileSync(pkgbuild, rendered)

  return { pkgver, pkgbuild, appimage: localAppimage }
}

function parseArgs(argv) {
  const out = {}

  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i]
    const value = argv[i + 1]

    if (!['--appimage', '--tag', '--out'].includes(key) || value === undefined) {
      throw new Error('usage: arch-package.mjs --appimage <file> --tag <vX.Y.Z-janitor.N> --out <dir>')
    }

    out[key.slice(2)] = value
  }

  for (const key of ['appimage', 'tag', 'out']) {
    if (!out[key]) throw new Error(`missing --${key}`)
  }

  return out
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = parseArgs(process.argv.slice(2))

    const result = renderArchPackage({
      appimage: path.resolve(args.appimage),
      tag: args.tag,
      outDir: path.resolve(args.out)
    })

    console.log(`PKGBUILD ${result.pkgver} → ${result.pkgbuild}`)
  } catch (error) {
    console.error(error.message)
    process.exit(1)
  }
}
