// P6: brand rules for the desktop i18n catalogs, plus the guard and the
// "untranslated" report. Pure functions over source text; the patch engine
// (scripts/patch-engine.mjs) decides when to write.

import { ALLOWLIST, FORBIDDEN, RULES } from '../brand/catalog-rules.mjs'

import { classifyLiterals, literalText, rewriteLiterals, skeleton } from './ts-literals.mjs'

const MASK_OPEN = '\u0000'
const MASK_CLOSE = '\u0001'

function freshRegex(pattern) {
  return new RegExp(pattern.source, pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`)
}

function mask(text, allowlist, stats) {
  const saved = []
  let out = text

  for (const entry of allowlist) {
    out = out.replace(freshRegex(entry.pattern), match => {
      stats.allowlisted[entry.id] = (stats.allowlisted[entry.id] ?? 0) + 1
      saved.push(match)

      return `${MASK_OPEN}${saved.length - 1}${MASK_CLOSE}`
    })
  }

  return { masked: out, saved }
}

function unmask(text, saved) {
  return text.replace(new RegExp(`${MASK_OPEN}(\\d+)${MASK_CLOSE}`, 'g'), (_, n) => saved[Number(n)])
}

/**
 * Apply the brand rules to every value literal of a catalog.
 * Returns { output, stats } where stats = { matchesBefore, replaced: {rule: n}, allowlisted: {entry: n} }.
 */
export function brandCatalog(source, { rules = RULES, allowlist = ALLOWLIST } = {}) {
  const { values } = classifyLiterals(source)
  const stats = { matchesBefore: 0, replaced: {}, allowlisted: {} }

  for (const rule of rules) stats.replaced[rule.id] = 0

  for (const literal of values) {
    for (const [s, e] of literal.segments) {
      stats.matchesBefore += (source.slice(s, e).match(/hermes/gi) || []).length
    }
  }

  const output = rewriteLiterals(source, values, text => {
    const { masked, saved } = mask(text, allowlist, stats)
    let out = masked

    for (const rule of rules) {
      out = out.replace(freshRegex(rule.pattern), () => {
        stats.replaced[rule.id]++

        return rule.replace
      })
    }

    return unmask(out, saved)
  })

  return { output, stats }
}

/**
 * Guard: every value literal, minus allowlisted substrings, must be free of
 * FORBIDDEN. Returns the violations as [{ path, value }].
 */
export function catalogViolations(source, { allowlist = ALLOWLIST, forbidden = FORBIDDEN } = {}) {
  const violations = []

  for (const literal of classifyLiterals(source).values) {
    const value = literalText(source, literal)
    let stripped = value

    for (const entry of allowlist) stripped = stripped.replace(freshRegex(entry.pattern), '')

    if (forbidden.test(stripped)) violations.push({ path: literal.path, value })
  }

  return violations
}

export function formatViolations(file, violations) {
  return violations.map(v => `  ${file} :: ${v.path} = ${JSON.stringify(v.value)}`).join('\n')
}

/**
 * Structural invariant of the transform: same key paths, and every token
 * outside string/template text is byte-identical.
 */
export function assertOnlyLiteralTextChanged(before, after) {
  const keysBefore = classifyLiterals(before).keys.map(k => k.path)
  const keysAfter = classifyLiterals(after).keys.map(k => k.path)

  if (JSON.stringify(keysBefore) !== JSON.stringify(keysAfter)) {
    throw new Error('catalog transform changed the set of object keys')
  }

  const a = skeleton(before)
  const b = skeleton(after)

  if (a.length !== b.length || a.some((token, n) => token !== b[n])) {
    throw new Error('catalog transform changed code outside string literals')
  }
}

/** Patch-engine transform: brand the catalog, then fail on any leftover. */
export function catalogTransform(file) {
  return source => {
    const { output } = brandCatalog(source)
    assertOnlyLiteralTextChanged(source, output)
    const violations = catalogViolations(output)

    if (violations.length > 0) {
      throw new Error(
        `"Hermes" left in user-visible text of ${file} after the brand rules — add a rule or an allowlist entry in apps/desktop-janitor/brand/catalog-rules.mjs:\n${formatViolations(file, violations)}`
      )
    }

    return output
  }
}

/**
 * Leaves whose localized value is byte-identical to the English one: usually
 * untranslated strings (the upstream completeness test only checks keys).
 */
export function identicalToEnglish(localeSource, englishSource) {
  const english = new Map()

  for (const literal of classifyLiterals(englishSource).values) {
    english.set(literal.path, literalText(englishSource, literal))
  }

  const same = []

  for (const literal of classifyLiterals(localeSource).values) {
    const value = literalText(localeSource, literal)

    if (english.get(literal.path) === value && /[A-Za-z]{3,}/.test(value)) {
      same.push({ path: literal.path, value })
    }
  }

  return same
}
