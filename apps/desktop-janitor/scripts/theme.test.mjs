// F1-13 theme patches (P12): the Janitor skin is the desktop's default theme.
// Behaviour of the patched sources, evaluated against temp copies / in memory;
// read-only on apps/desktop.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import module from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import vm from 'node:vm'

import { JANITOR_THEME_LABEL, THEME_PATCHES, parseSkinYaml, readJanitorSkin } from '../brand/theme.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'

const SHARED_SRC = path.resolve(APP_DIR, '..', 'shared', 'src')
const skin = readJanitorSkin()
const patched = computePatchedFiles(APP_DIR, allPatches())
const text = file => {
  assert.ok(patched.has(file), `${file} is not patched`)

  return patched.get(file).toString('utf8')
}

// Load the desktop's theme modules as Node type-stripped TS: map the Vite/tsconfig
// aliases the theme modules use and the extensionless (or `.js`) relative imports.
let hooksRegistered = false

function registerTsHooks() {
  if (hooksRegistered) return
  hooksRegistered = true
  module.registerHooks({
    resolve(specifier, context, next) {
      if (context.parentURL?.endsWith('.ts')) {
        if (specifier === '@hermes/shared') {
          specifier = pathToFileURL(path.join(SHARED_SRC, 'index.ts')).href
        } else if (specifier.startsWith('@hermes/shared/')) {
          specifier = pathToFileURL(path.join(SHARED_SRC, `${specifier.slice('@hermes/shared/'.length)}.ts`)).href
        } else if (specifier.startsWith('./') || specifier.startsWith('../')) {
          const base = fileURLToPath(new URL(specifier, context.parentURL))
          const candidates = [base, `${base.replace(/\.js$/, '')}.ts`, `${base}.ts`, path.join(base, 'index.ts')]
          const found = candidates.find(c => fs.existsSync(c) && fs.statSync(c).isFile())

          if (found) specifier = pathToFileURL(found).href
        }
      }

      return next(specifier, context)
    }
  })
}

/** Patched src/themes as importable modules, from a temp copy. */
async function loadPatchedThemes() {
  registerTsHooks()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-theme-'))
  const themes = path.join(dir, 'src', 'themes')
  fs.mkdirSync(themes, { recursive: true })

  for (const name of ['presets.ts', 'skin.ts', 'color.ts', 'types.ts']) {
    fs.copyFileSync(path.join(APP_DIR, 'src', 'themes', name), path.join(themes, name))
  }

  fs.writeFileSync(path.join(themes, 'presets.ts'), text('src/themes/presets.ts'))

  try {
    return {
      presets: await import(pathToFileURL(path.join(themes, 'presets.ts')).href),
      // Upstream's converter, straight from apps/desktop (unpatched).
      skinModule: await import(pathToFileURL(path.join(APP_DIR, 'src', 'themes', 'skin.ts')).href),
      color: await import(pathToFileURL(path.join(SHARED_SRC, 'color.ts')).href)
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
}

/** Slice of `source` from `start` to the end of `end` (both exact, unique). */
function between(source, start, end) {
  const from = source.indexOf(start)
  const to = source.indexOf(end, from)

  assert.ok(from >= 0 && to >= 0, `anchors not found: ${start} … ${end}`)

  return source.slice(from, to + end.length)
}

test('P12 patches are exact literals, write no "Hermes" and are registered in allPatches()', () => {
  const ids = new Set(allPatches().map(p => p.id))

  for (const patch of THEME_PATCHES) {
    assert.ok(patch.id.startsWith('P12-'), patch.id)
    assert.equal(typeof patch.find, 'string', patch.id)
    assert.doesNotMatch(patch.replace, /Hermes/, patch.id)
    assert.ok(ids.has(patch.id), `${patch.id} missing from allPatches()`)
  }
})

test('the skin parser reads name + colors and refuses a colour line it does not understand', () => {
  const parsed = parseSkinYaml(
    'name: demo\ndescription: "x"\n\ncolors:\n  # comment\n  background: "#101010"  # note\n  ui_text: \'#eeeeee\'\n  ui_accent: red\nspinner:\n  waiting_faces: ["a"]\n'
  )

  assert.deepEqual(parsed, { name: 'demo', colors: { background: '#101010', ui_text: '#eeeeee', ui_accent: 'red' } })
  assert.throws(() => parseSkinYaml('name: demo\ncolors:\n  ui_text: [1, 2]\n'), /unparseable colour/)
  // Unquoted `#hex` is a YAML comment (a null colour), not a colour.
  assert.throws(() => parseSkinYaml('name: demo\ncolors:\n  ui_text: #abcdef\n'), /unparseable colour/)
  assert.throws(() => parseSkinYaml('name: demo\ncolors:\n  a: "#000"\n  a: "#111"\n'), /duplicate colour a/)
  assert.throws(() => parseSkinYaml('colors:\n  a: "#000"\n'), /no name/)
})

test('the shipped default theme IS skinToDesktopTheme(sentry-janitor.yaml)', async () => {
  const { presets, skinModule } = await loadPatchedThemes()
  const expected = skinModule.skinToDesktopTheme(skin)
  const shipped = presets.BUILTIN_THEMES[skin.name]

  assert.ok(expected, 'upstream converter rejected the skin')
  assert.ok(shipped, `no built-in theme named ${skin.name}`)
  assert.equal(presets.DEFAULT_SKIN_NAME, skin.name)
  assert.deepEqual(shipped.colors, expected.colors)
  assert.deepEqual(shipped.darkColors, expected.darkColors)
  assert.equal(shipped.name, expected.name)
  assert.equal(shipped.label, JANITOR_THEME_LABEL)
  assert.doesNotMatch(shipped.description, /Hermes/)

  // A skin edit that changes a converted colour must change the shipped theme.
  const drifted = skinModule.skinToDesktopTheme({ ...skin, colors: { ...skin.colors, ui_accent: '#ff0000' } })
  assert.notDeepEqual(drifted.colors, shipped.colors)
})

test('Janitor is first in the picker and every upstream theme is still offered', async () => {
  const { presets } = await loadPatchedThemes()
  const upstream = fs.readFileSync(path.join(APP_DIR, 'src', 'themes', 'presets.ts'), 'utf8')
  const upstreamNames = [...between(upstream, 'export const BUILTIN_THEMES', '\n}\n').matchAll(/^\s+'?([\w-]+)'?: \w+Theme,?$/gm)].map(m => m[1])

  assert.equal(presets.BUILTIN_THEME_LIST[0].name, skin.name)
  assert.ok(upstreamNames.length > 1)

  for (const name of upstreamNames) assert.ok(presets.BUILTIN_THEMES[name], `upstream theme ${name} dropped`)
})

test('the Janitor palette is dark and keeps the converter\'s AA accent on the sidebar', async () => {
  const { presets, color } = await loadPatchedThemes()
  const c = presets.BUILTIN_THEMES[skin.name].colors

  assert.ok(color.relativeLuminance(c.background) < 0.05, `background ${c.background} is not dark`)
  assert.ok(color.contrastRatio(c.foreground, c.background) >= 7, 'foreground below AAA on background')
  assert.ok(color.contrastRatio(c.primary, c.sidebarBackground) >= 4.5, 'accent below AA on the sidebar')
  assert.equal(c.destructive, skin.colors.ui_error.toLowerCase())
})

test('mode: dark when the user has not chosen; a stored pick wins, per profile', () => {
  const source = text('src/themes/context.tsx')
  const snippet = between(source, 'const normalizeMode = ', 'export const modePref = profilePref(PROFILE_MODES_KEY, MODE_KEY, normalizeMode)\n')
  const js = module.stripTypeScriptTypes(snippet).replace(/^export /gm, '')
  const storage = { record: {}, global: null }
  const sandbox = {
    PROFILE_MODES_KEY: 'modes',
    MODE_KEY: 'mode',
    PROFILE_SKINS_KEY: 'skins',
    SKIN_KEY: 'skin',
    normalizeSkin: v => v,
    storedStringRecord: key => (key === 'modes' ? storage.record : {}),
    storedString: key => (key === 'mode' ? storage.global : null),
    persistString: (key, value) => {
      if (key === 'mode') storage.global = value
    },
    persistStringRecord: (key, value) => {
      if (key === 'modes') storage.record = value
    }
  }
  const { modePref } = vm.runInNewContext(`${js}\n;({ modePref })`, sandbox)

  assert.equal(modePref.resolve('default'), 'dark')
  assert.equal(modePref.resolve('work'), 'dark')

  modePref.assign('default', 'light')
  assert.equal(modePref.resolve('default'), 'light')
  assert.equal(modePref.resolve('work'), 'light', 'unassigned profiles inherit the global pick')

  modePref.assign('work', 'system')
  assert.equal(modePref.resolve('work'), 'system')
  assert.equal(modePref.resolve('default'), 'light')

  storage.global = 'dusk'
  assert.equal(modePref.resolve('default'), 'dark', 'junk falls back to the Janitor default')
})

test('native appearance: dark on a fresh install, the persisted renderer pick otherwise', () => {
  const source = text('electron/main.ts')
  const fn = between(source, 'function readPersistedThemeSource() {', "\n  return 'dark' // Janitor build: the renderer defaults to dark too\n}\n")
  const run = file =>
    vm.runInNewContext(`${fn}\n;readPersistedThemeSource()`, {
      JSON,
      NATIVE_THEME_CONFIG_PATH: '/x/native-theme.json',
      THEME_SOURCES: new Set(['dark', 'light', 'system']),
      fs: {
        readFileSync: () => {
          if (file === null) throw new Error('ENOENT')

          return file
        }
      }
    })

  assert.equal(run(null), 'dark')
  assert.equal(run('{oops'), 'dark')
  assert.equal(run(JSON.stringify({ themeSource: 'light' })), 'light')
  assert.equal(run(JSON.stringify({ themeSource: 'system' })), 'system')
})

test('the first-run featured row has no hardcoded arc colours: it follows the theme', () => {
  const source = text('src/components/onboarding/index.tsx')
  const row = between(source, '{/* Janitor build: MiniMax is the recommended provider (plan 2.2). */}', '</button>')

  assert.doesNotMatch(row, /arc-nous/)
  assert.match(row, /\[--arc-c1:var\(--dt-primary\)\]!/)
  assert.doesNotMatch(row, /#[0-9a-f]{3,8}\b/i)
})
