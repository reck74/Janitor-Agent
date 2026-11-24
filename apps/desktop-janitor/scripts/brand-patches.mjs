// The full, ordered list of build patches applied to apps/desktop:
// P1-P5 structural, P10 Spanish catalog overrides (before P6 so the brand
// guard sees them), P6 catalog brand rules, P7/P8 exact literals, P9 first-run
// (F1-08), P11 plugin Spanish bundles (F1-10), P12 Janitor theme by default
// (F1-13), P18 Hermes' embedded Skills Hub and plugin catalog hidden (F1-30),
// P19 updates follow the release channel, not main (F1-28).

import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { CATALOG_FILES } from '../brand/catalog-rules.mjs'
import { FIRST_RUN_PATCHES } from '../brand/first-run.mjs'
import { HIDDEN_SURFACE_PATCHES } from '../brand/hidden-surfaces.mjs'
import { LITERALS } from '../brand/literals.mjs'
import { STRUCTURAL_PATCHES } from '../brand/patches.mjs'
import { RELEASE_CHANNEL_PATCHES } from '../brand/release-channel.mjs'
import { THEME_PATCHES } from '../brand/theme.mjs'

import { catalogTransform } from './catalog-brand.mjs'
import { catalogOverridesTransform } from './catalog-overrides.mjs'
import { pluginLocalePatches } from './plugin-locales.mjs'

const DEFAULT_APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'desktop')

export function literalPatches(map = LITERALS) {
  const patches = []

  for (const [file, entries] of Object.entries(map)) {
    const group = file.startsWith('electron/') ? 'P7' : 'P8'

    entries.forEach(([find, replace, count = 1], index) => {
      patches.push({ id: `${group}-${file}#${index + 1}`, purpose: `literal → ${replace}`, file, find, replace, count })
    })
  }

  return patches
}

export function catalogPatches(files = CATALOG_FILES) {
  return files.map(file => ({
    id: `P6-catalog:${file}`,
    purpose: 'Brand rules over catalog values + guard',
    file,
    transform: catalogTransform(file)
  }))
}

export function catalogOverridePatches(appDir = DEFAULT_APP_DIR) {
  return [
    {
      id: 'P10-catalog-overrides:src/i18n/es.ts',
      purpose: 'Spanish for es.ts leaves upstream left in English (brand/catalog-overrides.mjs)',
      file: 'src/i18n/es.ts',
      transform: catalogOverridesTransform(appDir)
    }
  ]
}

export function allPatches(appDir = DEFAULT_APP_DIR) {
  return [
    ...STRUCTURAL_PATCHES,
    ...catalogOverridePatches(appDir),
    ...catalogPatches(),
    ...literalPatches(),
    ...FIRST_RUN_PATCHES,
    ...pluginLocalePatches(),
    ...THEME_PATCHES,
    ...HIDDEN_SURFACE_PATCHES,
    ...RELEASE_CHANNEL_PATCHES
  ]
}
