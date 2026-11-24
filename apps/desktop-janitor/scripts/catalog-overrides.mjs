// P10: set Spanish catalog values by key path (brand/catalog-overrides.mjs),
// plus the enforced "Spanish everywhere" check over the final es.ts. Pure
// functions over source text; the patch engine decides when to write.

import fs from 'node:fs'
import path from 'node:path'

import { ES_OVERRIDES, IDENTICAL_PATHS } from '../brand/catalog-overrides.mjs'

import { identicalToEnglish } from './catalog-brand.mjs'
import { classifyLiterals, literalText } from './ts-literals.mjs'

const IDENT = /^[A-Za-z_$][\w$]*$/

export function quoteTs(value) {
  return `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`
}

function englishValues(englishSource) {
  return new Map(classifyLiterals(englishSource).values.map(v => [v.path, literalText(englishSource, v)]))
}

/**
 * Apply `overrides` to `source` (es.ts). `englishSource` is en.ts. Throws one
 * error listing every override whose anchor no longer holds.
 */
export function applyCatalogOverrides(source, englishSource, overrides = ES_OVERRIDES) {
  const english = englishValues(englishSource)
  const problems = []
  const edits = []
  const { keys, values, tokens } = classifyLiterals(source)

  for (const override of overrides) {
    const currentEnglish = english.get(override.path)

    if (currentEnglish !== override.en) {
      problems.push(
        currentEnglish === undefined
          ? `${override.path}: en.ts no longer has this key`
          : `${override.path}: en.ts now reads ${JSON.stringify(currentEnglish)} (override pinned ${JSON.stringify(override.en)}) — review the Spanish`
      )
      continue
    }

    const value = values.find(v => v.path === override.path)

    if (value) {
      const expected = override.from ?? override.en
      const current = literalText(source, value)

      if (value.kind !== 'string' || current !== expected) {
        problems.push(
          `${override.path}: es.ts now reads ${JSON.stringify(current)} (override expected ${JSON.stringify(expected)}) — upstream changed or translated it; drop or revise the override`
        )
        continue
      }

      edits.push([value.start, value.end, quoteTs(override.es)])
      continue
    }

    if (keys.some(k => k.path === override.path)) {
      problems.push(`${override.path}: es.ts holds a non-string value here; overrides only set strings`)
      continue
    }

    // Missing leaf: insert it right after its parent's opening brace.
    const parent = findParent(keys, override.path)
    const at = parent ? tokens.findIndex(t => t.start === parent.key.start) : -1

    if (at < 0 || tokens[at + 1]?.value !== ':' || tokens[at + 2]?.value !== '{') {
      problems.push(`${override.path}: no parent object for it in es.ts`)
      continue
    }

    const brace = tokens[at + 2]
    const indent = (source.slice(brace.end).match(/^\n([ \t]*)/) ?? [null, '  '])[1]
    const key = IDENT.test(parent.leaf) ? parent.leaf : quoteTs(parent.leaf)

    edits.push([brace.end, brace.end, `\n${indent}${key}: ${quoteTs(override.es)},`])
  }

  if (problems.length > 0) {
    throw new Error(`catalog override(s) no longer apply (apps/desktop-janitor/brand/catalog-overrides.mjs):\n${problems.map(p => `  ${p}`).join('\n')}`)
  }

  edits.sort((a, b) => b[0] - a[0])
  let out = source

  for (const [s, e, text] of edits) out = out.slice(0, s) + text + out.slice(e)

  return out
}

// A quoted key with dots ('composer.dictate') makes the path ambiguous: try
// every split, longest parent first.
function findParent(keys, full) {
  for (let cut = full.lastIndexOf('.'); cut > 0; cut = full.lastIndexOf('.', cut - 1)) {
    const key = keys.find(k => k.path === full.slice(0, cut))

    if (key) return { key, leaf: full.slice(cut + 1) }
  }

  return null
}

/** Patch-engine transform for es.ts; reads en.ts from the same app dir. */
export function catalogOverridesTransform(appDir) {
  return source => applyCatalogOverrides(source, fs.readFileSync(path.join(appDir, 'src', 'i18n', 'en.ts'), 'utf8'))
}

const leafKeys = source =>
  new Set(
    classifyLiterals(source)
      .keys.map(k => k.path)
      .filter(p => !p.startsWith('intro.') && p !== 'intro')
  )

/**
 * The enforced check over the FINAL es.ts (overrides + brand rules applied):
 *   missing   — key paths en.ts has and es.ts lacks (they render in English)
 *   identical — values identical to en.ts and not in IDENTICAL_TO_ENGLISH
 *   stale     — IDENTICAL_TO_ENGLISH entries that are no longer identical
 */
export function spanishCoverage(finalSpanish, englishSource, allowed = IDENTICAL_PATHS) {
  const esKeys = leafKeys(finalSpanish)
  const missing = [...leafKeys(englishSource)].filter(p => !esKeys.has(p))
  const same = identicalToEnglish(finalSpanish, englishSource)
  const samePaths = new Set(same.map(s => s.path))

  return {
    missing,
    identical: same.filter(s => !allowed.has(s.path)),
    stale: [...allowed].filter(p => !samePaths.has(p))
  }
}
