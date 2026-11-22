// F1-10 "Spanish everywhere": catalog overrides (P10), the enforced
// untranslated check, and the plugin Spanish bundles (P11). Read-only on
// apps/desktop.

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { ES_OVERRIDES, IDENTICAL_TO_ENGLISH } from '../brand/catalog-overrides.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { applyCatalogOverrides, spanishCoverage } from './catalog-overrides.mjs'
import { computePatchedFiles } from './patch-engine.mjs'
import {
  bundleLiteral,
  bundlePath,
  evaluateLiteral,
  objectLiteralAfter,
  PLUGIN_LOCALES,
  renderedStrings,
  shapeDifferences
} from './plugin-locales.mjs'
import { checkTranspiles } from './transpile-check.mjs'
import { classifyLiterals, literalText } from './ts-literals.mjs'

const read = file => fs.readFileSync(path.join(APP_DIR, file), 'utf8')
const patched = computePatchedFiles(APP_DIR, allPatches())
const finalText = file => patched.get(file).toString('utf8')
const EN = read('src/i18n/en.ts')

// ---- es.ts ------------------------------------------------------------------

test('every es.ts leaf is Spanish: none missing, none identical to English outside the reasoned allowlist', () => {
  const { missing, identical, stale } = spanishCoverage(finalText('src/i18n/es.ts'), EN)

  assert.deepEqual(missing, [], `keys en.ts has and es.ts lacks (they render in English) — add them to brand/catalog-overrides.mjs:\n${missing.join('\n')}`)
  assert.deepEqual(
    identical.map(i => `${i.path} = ${JSON.stringify(i.value)}`),
    [],
    'es.ts values identical to English — translate them in brand/catalog-overrides.mjs or allowlist them with a reason'
  )
  assert.deepEqual(stale, [], 'IDENTICAL_TO_ENGLISH entries that are no longer identical — remove them')
})

test('a new untranslated upstream string fails the check with its key path', () => {
  const es = finalText('src/i18n/es.ts')
  const en = EN.replace("  connectors: {\n", "  connectors: {\n    plantedNew: 'Brand new upstream text',\n    plantedSame: 'Copied text',\n")
  const esPlanted = es.replace('connectors: {\n', "connectors: {\n    plantedSame: 'Copied text',\n")

  assert.notEqual(en, EN, 'plant anchor moved in en.ts')
  assert.notEqual(esPlanted, es, 'plant anchor moved in es.ts')

  const { missing, identical } = spanishCoverage(esPlanted, en)

  assert.deepEqual(missing, ['connectors.plantedNew'])
  assert.deepEqual(identical.map(i => i.path), ['connectors.plantedSame'])
})

test('overrides insert missing keys into the right object and replace untranslated values', () => {
  const es = applyCatalogOverrides(read('src/i18n/es.ts'), EN)
  const values = new Map(classifyLiterals(es).values.map(v => [v.path, literalText(es, v)]))

  for (const override of ES_OVERRIDES) {
    assert.equal(values.get(override.path), override.es.replace(/'/g, "\\'"), override.path)
  }

  // A key with a dot ('composer.dictate') lands in keybinds.actions, quoted.
  assert.match(es, /actions: \{\n\s+'composer\.dictate': 'Iniciar \/ detener dictado',/)
})

test('an override fails loudly when upstream changes or removes its English, or translates it', () => {
  const es = read('src/i18n/es.ts')
  const [first] = ES_OVERRIDES

  assert.throws(() => applyCatalogOverrides(es, EN, [{ ...first, en: 'Something else' }]), new RegExp(`${first.path.replace(/\./g, '\\.')}: en\\.ts now reads`))
  assert.throws(() => applyCatalogOverrides(es, EN, [{ path: 'nope.gone', en: 'x', es: 'y' }]), /nope\.gone: en\.ts no longer has this key/)
  assert.throws(
    () => applyCatalogOverrides(es, EN, [{ path: 'common.error', en: 'Error', from: 'Fallo', es: 'Error' }]),
    /common\.error: es\.ts now reads "Error"/
  )
})

test('every IDENTICAL_TO_ENGLISH group gives a reason and lists each path once', () => {
  const all = IDENTICAL_TO_ENGLISH.flatMap(g => g.paths)

  assert.equal(new Set(all).size, all.length)

  for (const group of IDENTICAL_TO_ENGLISH) assert.ok(group.reason.length > 10)
})

// ---- plugin bundles ---------------------------------------------------------

for (const entry of PLUGIN_LOCALES) {
  test(`plugin ${entry.plugin}: the injected es bundle has the English key set, value kinds and arguments`, async () => {
    const english = evaluateLiteral(objectLiteralAfter(read(entry.file), entry.english))
    const injected = evaluateLiteral(objectLiteralAfter(finalText(entry.file), entry.spanish))
    const authored = (await import(bundlePath(entry.plugin))).default

    assert.deepEqual(shapeDifferences(english, injected), [])
    // What gets injected is exactly the authored module.
    assert.deepEqual(renderedStrings(injected), renderedStrings(authored))
    assert.deepEqual(renderedStrings(evaluateLiteral(bundleLiteral(entry.plugin))), renderedStrings(authored))
  })

  test(`plugin ${entry.plugin}: Spanish text never says Hermes and keeps the Janitor command`, async () => {
    const authored = (await import(bundlePath(entry.plugin))).default

    for (const [at, value] of renderedStrings(authored)) {
      assert.doesNotMatch(value, /hermes/i, at)
    }
  })

  test(`plugin ${entry.plugin}: the patched file still parses`, t => {
    const source = finalText(entry.file)

    if (entry.file.endsWith('.js')) {
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-plugin-js-'))

      try {
        const tmp = path.join(dir, 'plugin.mjs')
        fs.writeFileSync(tmp, source)
        const result = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' })

        assert.equal(result.status, 0, result.stderr)
      } finally {
        fs.rmSync(dir, { recursive: true, force: true })
      }

      return
    }

    const result = checkTranspiles(source, entry.file, APP_DIR)

    if (result.ok === null) return t.skip(result.reason)
    assert.equal(result.ok, true, result.error)
  })
}

test('the shape check catches a dropped key, a wrong kind and a dropped argument', () => {
  const english = { a: 'x', b: { c: n => `${n} left` }, d: 'y' }
  const broken = { a: 'x', b: { c: () => 'quedan' }, d: () => 'y', e: 'extra' }

  assert.deepEqual(shapeDifferences(english, broken).sort(), [
    'b.c: drops argument ⟦0⟧',
    'b.c: takes 0 argument(s), English takes 1',
    'd: function where English has string',
    'e: not in English'
  ])
})
