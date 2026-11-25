// P21: the version the Janitor app shows and carries is Janitor's, not
// apps/desktop/package.json's (upstream's desktop version, e.g. 0.17.6).
//
// Two sources reach the screen (sidebar «v…», Ajustes → Acerca de, the macOS
// About panel), both through main.ts resolveHermesVersion():
//   - with an engine installed, its hermes_cli/__init__.py __version__, which in
//     this fork is PEP 440 (`0.21.5+janitor.1`): P21-version-display turns it
//     into the display form (`0.21.5-janitor.1`, janitor/version.py);
//   - without one (first launch, install screen), app.getVersion(): the build
//     sets extraMetadata.version (scripts/build.mjs) to the display form of
//     pyproject.toml's [project].version, which electron-builder also stamps on
//     the Windows installer/.exe and the macOS Info.plist.
// The app↔engine contract (brand/compat.mjs, P13) compares integers from
// janitor/desktop-compat.json, never this version.
//
// janitorDisplayVersion is injected into main.ts as its own source text
// (Function#toString): it must stay self-contained.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')

/** janitor/version.py display_version: the FIRST `+` becomes `-`. */
export function janitorDisplayVersion(raw) {
  return typeof raw === 'string' ? raw.replace('+', '-') : raw
}

/** `version` of the [project] table of a pyproject.toml text (basic or literal string). */
export function pyprojectVersion(text) {
  let inProject = false

  for (const line of text.split(/\r?\n/)) {
    const header = line.match(/^\s*\[\s*([^\]]+?)\s*\]\s*(#.*)?$/)

    if (header) {
      inProject = header[1] === 'project'
      continue
    }

    if (!inProject) continue

    const entry = line.match(/^\s*version\s*=\s*(?:"([^"\\]*)"|'([^']*)')\s*(#.*)?$/)

    if (entry) return entry[1] ?? entry[2]
  }

  throw new Error('pyproject.toml: no version = "..." in the [project] table')
}

// semver 2.0.0 (electron-builder rejects anything else as `version`).
const SEMVER_RE =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$/

/** The version this build gives the app: display form of pyproject.toml's, semver-checked. */
export function janitorAppVersion(repoRoot = REPO_ROOT) {
  const file = path.join(repoRoot, 'pyproject.toml')
  const version = janitorDisplayVersion(pyprojectVersion(fs.readFileSync(file, 'utf8')))

  if (!SEMVER_RE.test(version)) {
    throw new Error(`${file}: version ${JSON.stringify(version)} is not semver in its display form`)
  }

  return version
}

export const APP_VERSION_PATCHES = [
  {
    id: 'P21-version-display-fn',
    purpose: 'Define janitorDisplayVersion (janitor/version.py display_version) next to resolveHermesVersion',
    file: 'electron/main.ts',
    find: 'function resolveHermesVersion() {\n',
    replace:
      '// Janitor build (P21): the engine\'s PEP 440 version in its display form (janitor/version.py).\n' +
      `${janitorDisplayVersion.toString()}\n\nfunction resolveHermesVersion() {\n`,
    count: 1
  },
  {
    id: 'P21-version-display',
    purpose: 'Sidebar / About: the engine version as the user reads it (0.21.5-janitor.1, not 0.21.5+janitor.1)',
    file: 'electron/main.ts',
    find: '      if (match) {\n        return match[1]\n      }\n',
    replace: '      if (match) {\n        return janitorDisplayVersion(match[1])\n      }\n',
    count: 1
  }
]
