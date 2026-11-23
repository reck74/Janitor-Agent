// Brand layer tests (P1-P8): drift detector against the CURRENT apps/desktop
// sources, catalog guard, literal-map hygiene, transpilation. Read-only on
// apps/desktop; nothing here writes outside temp dirs.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { ALLOWLIST, RULES } from '../brand/catalog-rules.mjs'
import { LITERALS } from '../brand/literals.mjs'
import { STRUCTURAL_PATCHES } from '../brand/patches.mjs'

import { allPatches, literalPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import {
  assertOnlyLiteralTextChanged,
  brandCatalog,
  catalogTransform,
  catalogViolations,
  identicalToEnglish
} from './catalog-brand.mjs'
import { applyCatalogOverrides } from './catalog-overrides.mjs'
import { checkPatches, computePatchedFiles } from './patch-engine.mjs'
import { checkTranspiles } from './transpile-check.mjs'
import { classifyLiterals, literalText, skeleton } from './ts-literals.mjs'

const read = file => fs.readFileSync(path.join(APP_DIR, file), 'utf8')
const ES = 'src/i18n/es.ts'
// es.ts as P6 sees it in the build: P10 overrides already applied.
const overridden = () => applyCatalogOverrides(read(ES), read('src/i18n/en.ts'))

// ---- drift detector -------------------------------------------------------

test('every build patch resolves against the current apps/desktop with its expected count', () => {
  const { results } = checkPatches(APP_DIR, allPatches())
  const failed = results.filter(r => !r.ok)

  assert.deepEqual(failed, [], `upstream drift:\n${failed.map(f => f.error).join('\n')}`)
})

test('patch ids are unique and every patch declares a positive count or a transform', () => {
  const ids = allPatches().map(p => p.id)

  assert.equal(new Set(ids).size, ids.length)

  for (const patch of allPatches()) {
    assert.ok(patch.transform || (Number.isInteger(patch.count) && patch.count > 0), patch.id)
  }
})

test('structural patches do what the plan contract (4.3) says', () => {
  const writes = computePatchedFiles(APP_DIR, STRUCTURAL_PATCHES)
  const text = file => writes.get(file).toString('utf8')

  assert.match(text('electron/main.ts'), /return path\.join\(app\.getPath\('home'\), '\.janitor'\)\n\}\n\nconst HERMES_HOME/)
  assert.match(text('electron/bootstrap-runner.ts'), /raw\.githubusercontent\.com\/reck74\/Janitor-Agent\//)
  assert.doesNotMatch(text('electron/bootstrap-runner.ts'), /NousResearch\/hermes-agent/)
  assert.doesNotMatch(text('electron/main.ts'), /'-m', 'hermes_cli\.main', \.\.\.backendArgs/)
  assert.doesNotMatch(text('electron/main.ts'), /findOnPath\('hermes'\)/)
  assert.match(text('src/i18n/languages.ts'), /DEFAULT_LOCALE: Locale = 'es'/)
  assert.match(text('index.html'), /<html lang="es">[\s\S]*<title>Janitor<\/title>/)
  // Probes that check the runtime is usable keep looking for hermes_cli.
  assert.match(text('electron/main.ts'), /fileExists\(path\.join\(root, 'hermes_cli', 'main\.py'\)\)/)
})

test('the ownership matcher accepts the Janitor backend command line and still the upstream ones', async () => {
  const source = computePatchedFiles(APP_DIR, STRUCTURAL_PATCHES).get('electron/backend-ownership.ts').toString('utf8')
  const regexLine = source.split('\n').find(line => line.includes('janitor\\.cli'))
  const matcher = new RegExp(regexLine.trim().replace(/^return \//, '').replace(/\/i\.test\($/, ''), 'i')

  assert.ok(matcher.test('/home/u/.janitor/hermes-agent/venv/bin/python -m janitor.cli --profile work serve --host 127.0.0.1 --port 0'))
  assert.ok(matcher.test('/usr/bin/python3 -m hermes_cli.main serve --host 127.0.0.1'))
  assert.ok(!matcher.test('/usr/bin/python3 -m janitor.cli chat'))
})

// ---- P6 catalog -----------------------------------------------------------

test('catalog transform: only literal text changes, keys are untouched', () => {
  const source = read(ES)
  const { output } = brandCatalog(source)

  assertOnlyLiteralTextChanged(source, output)

  const keys = classifyLiterals(output).keys.map(k => k.path)

  assert.deepEqual(keys, classifyLiterals(source).keys.map(k => k.path))
  // the 13 internal keys that contain "Hermes" survive
  assert.ok(keys.filter(k => /hermes/i.test(k.split('.').pop())).length >= 13)
})

test('catalog guard: no Hermes left in Spanish values outside the allowlist', () => {
  const { output, stats } = brandCatalog(overridden())
  const violations = catalogViolations(output)

  assert.deepEqual(violations, [], violations.map(v => `${v.path} = ${v.value}`).join('\n'))

  const replaced = Object.values(stats.replaced).reduce((a, b) => a + b, 0)
  const allowlisted = Object.values(stats.allowlisted).reduce((a, b) => a + b, 0)

  assert.equal(replaced + allowlisted, stats.matchesBefore, 'every Hermes in a value is either rebranded or allowlisted')
  assert.ok(stats.replaced['product-name'] > 0)
})

test('a new upstream "Hermes" string the rules miss fails the guard with its key path', () => {
  const base = overridden()
  const planted = base.replace(
    'connectors: {\n',
    "connectors: {\n    plantedNew: 'Instala HERMES-CLI para continuar',\n    plantedFn: (n: string) => `Hola ${n}, soy HERMES`,\n    plantedUrl: 'Guía: https://hermes-agent.nousresearch.com/docs/nueva',\n"
  )

  assert.notEqual(planted, base, 'plant anchor moved')

  const { output } = brandCatalog(planted)
  const violations = catalogViolations(output)

  // The url allowlist only masks the example URLs es.ts keeps, so a new
  // upstream link with "hermes" in it is named too.
  assert.deepEqual(
    violations.map(v => v.path),
    ['connectors.plantedNew', 'connectors.plantedFn', 'connectors.plantedUrl']
  )
  assert.throws(() => catalogTransform(ES)(planted), /connectors\.plantedNew = "Instala HERMES-CLI para continuar"/)
})

test('brand rules rewrite commands, home and prose but keep allowlisted text', () => {
  const sample = [
    'export const x = {',
    "  a: 'Ejecuta `hermes debug share --local` o hermes curator restore',",
    "  b: 'Edita ~/.hermes/config.yaml; Hermes Desktop y Hermes Agent son Hermes',",
    "  c: 'salir de hermes',",
    "  d: 'Hermes Cloud en https://hermes.example.com/x con HERMES_HOME, hermes://open y .hermes/plans/',",
    "  restartHermes: 'ok'",
    '}'
  ].join('\n')
  const { output } = brandCatalog(sample)

  assert.match(output, /a: 'Ejecuta `janitor debug share --local` o janitor curator restore'/)
  assert.match(output, /b: 'Edita ~\/\.janitor\/config\.yaml; Janitor y Janitor son Janitor'/)
  assert.match(output, /c: 'salir de janitor'/)
  assert.match(output, /d: 'Hermes Cloud en https:\/\/hermes\.example\.com\/x con HERMES_HOME, hermes:\/\/open y \.hermes\/plans\/'/)
  assert.match(output, /restartHermes: 'ok'/)
  assert.deepEqual(catalogViolations(output), [])
})

test('every allowlist entry and rule documents a reason', () => {
  for (const entry of [...ALLOWLIST, ...RULES]) {
    assert.ok(entry.reason && entry.reason.length > 10, entry.id)
    assert.ok(entry.pattern.flags.includes('g'), entry.id)
  }
})

test('the branded catalog still transpiles as a TypeScript module', t => {
  const result = checkTranspiles(brandCatalog(read(ES)).output, ES, APP_DIR)

  if (result.ok === null) return t.skip(result.reason)
  assert.equal(result.ok, true, result.error)
})

test('without node_modules (CI), .ts files are checked with Node type stripping', t => {
  const noDeps = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-no-deps-'))

  try {
    const good = checkTranspiles(brandCatalog(read(ES)).output, ES, noDeps)

    if (good.ok === null) return t.skip(good.reason)
    assert.equal(good.ok, true, good.error)
    assert.equal(checkTranspiles("export const x = { a: 'b' ", ES, noDeps).ok, false)
  } finally {
    fs.rmSync(noDeps, { recursive: true, force: true })
  }
})

test('identicalToEnglish really compares values (the enforced check lives in spanish.test.mjs)', () => {
  // A value only es.ts has never counts.
  assert.deepEqual(identicalToEnglish("export const es = { a: 'Hola', b: 'Same text' }", "export const en = { a: 'Hello', b: 'Same text' }"), [
    { path: 'b', value: 'Same text' }
  ])
})

// ---- P7 / P8 literal map --------------------------------------------------

test('literal patches are exact strings, change something, and introduce no Hermes', () => {
  for (const patch of literalPatches()) {
    assert.equal(typeof patch.find, 'string', `${patch.id}: non-catalog patches are exact literals, never regexes`)
    assert.notEqual(patch.find, patch.replace, patch.id)
    assert.doesNotMatch(patch.replace, /Hermes/, patch.id)
  }

  assert.ok(Object.keys(LITERALS).every(file => fs.existsSync(path.join(APP_DIR, file))))
})

test('every patched TypeScript file still transpiles', t => {
  const skipped = []

  for (const [file, content] of computePatchedFiles(APP_DIR, allPatches())) {
    const result = checkTranspiles(content.toString('utf8'), file, APP_DIR)

    if (result.ok === null) {
      if (/\.tsx?$/.test(file)) skipped.push(file)
      continue
    }

    assert.equal(result.ok, true, `${file}: ${result.error}`)
  }

  if (skipped.length) t.diagnostic(`not transpiled (no tool for these here): ${skipped.join(', ')}`)
})

// ---- lexer ----------------------------------------------------------------

test('lexer separates keys from values (string keys, ternaries, nested templates) and skips imports', () => {
  const source = [
    "import { x } from './hermes'",
    'export const c = {',
    "  '/quit': 'salir de hermes',",
    '  nested: { hermesKey: `a ${n ? `Hermes ${v}` : "b"} c`, list: [\'x\', \'y\'] },',
    "  fn: (a: string, b: number) => (a ? 'si' : 'no'),",
    '  re: /hermes:\\/\\//g, // comment with \'quote',
    '}'
  ].join('\n')
  const { keys, values } = classifyLiterals(source)

  assert.deepEqual(
    keys.map(k => k.path),
    ['/quit', 'nested', 'nested.hermesKey', 'nested.list', 'fn', 're']
  )
  assert.deepEqual(
    values.map(v => [v.path, literalText(source, v)]),
    [
      ['/quit', 'salir de hermes'],
      ['nested.hermesKey', 'a ${…} c'],
      ['nested.hermesKey~2', 'Hermes ${…}'],
      ['nested.hermesKey~3', 'b'],
      ['nested.list[0]', 'x'],
      ['nested.list[1]', 'y'],
      ['fn', 'si'],
      ['fn~2', 'no']
    ]
  )
  assert.ok(skeleton(source).includes('/hermes:\\/\\//g'))
})
