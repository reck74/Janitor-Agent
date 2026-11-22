// The full, ordered list of build patches applied to apps/desktop:
// P1-P5 structural, P6 catalog brand rules, P7/P8 exact literals.

import { CATALOG_FILES } from '../brand/catalog-rules.mjs'
import { LITERALS } from '../brand/literals.mjs'
import { STRUCTURAL_PATCHES } from '../brand/patches.mjs'

import { catalogTransform } from './catalog-brand.mjs'

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

export function allPatches() {
  return [...STRUCTURAL_PATCHES, ...catalogPatches(), ...literalPatches()]
}
