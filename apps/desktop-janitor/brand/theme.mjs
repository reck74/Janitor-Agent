// Theme patches P12 (task F1-13; directives #17 and #18: the desktop inherits
// the skin's COLOURS only).
//
// Upstream theme selection (apps/desktop/src/themes/):
//   - the skin name and the light/dark/system mode are localStorage picks per
//     profile (context.tsx skinPref / modePref); with nothing stored the skin is
//     DEFAULT_SKIN_NAME ('nous', presets.ts) and the mode 'system' (OS);
//   - the backend skin (`gateway.ready`) is only REGISTERED as a selectable
//     theme (backend-sync.ts); it is applied only on an explicit `skin.changed`.
// So a Janitor user saw upstream's Nous look, light on a light OS.
//
// The Janitor palette ships as a BUILT-IN theme named after the skin
// (`sentry-janitor`) and becomes the default. Its colours are the `colors:`
// block of assets/janitor/sentry-janitor.yaml, embedded at build time and run
// through upstream's own skinToDesktopTheme at runtime, so it is the same theme
// the backend pushes: a built-in name is never re-registered from the backend
// (backend-sync.ts), and `skin.changed` to it resolves to this preset. Dark is
// the default mode (renderer + native window) when the user has not chosen.
//
// Línea gráfica (F1-18, owner decision 2026-11-24). Upstream's converter is
// terminal-first: it never reads `ui_primary`, and takes the app background from
// `status_bar_bg`. The preset therefore routes two skin colours by hand — the
// skin's `completion_menu_bg` as the background and `ui_primary` (lime) as the
// primary — and the empty chat shows the J4NITOR-AGENT banner
// (assets/janitor-logo-banner.png) instead of the text wordmark.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const SKIN_FILE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'assets', 'janitor', 'sentry-janitor.yaml')

export const JANITOR_THEME_LABEL = 'Janitor'
export const JANITOR_THEME_DESCRIPTION = 'Paleta del skin sentry-janitor: fondo morado profundo, verde lima, morado Sentry y rosa para errores'

const COLOR_LINE = /^ {2}([a-z][a-z0-9_]*):\s*(?:"([^"]*)"|'([^']*)'|([^\s#]+))\s*(?:#.*)?$/
const TOP_LEVEL = /^([a-z][a-z0-9_]*):\s*(.*?)\s*(?:#.*)?$/

/**
 * `{ name, colors }` of a skin YAML. Only the two keys the desktop converts are
 * read; a colour line this parser does not understand fails instead of being
 * skipped, so the shipped palette can never silently lose a key.
 */
export function parseSkinYaml(text) {
  let name = null
  let colors = null
  let inColors = false

  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line.trim() || line.trim().startsWith('#')) continue

    if (!line.startsWith(' ')) {
      const top = TOP_LEVEL.exec(line)

      if (!top) throw new Error(`skin YAML line ${index + 1}: unexpected top-level line ${JSON.stringify(line)}`)
      inColors = top[1] === 'colors'

      if (inColors) {
        if (colors) throw new Error('skin YAML: duplicate colors block')
        colors = {}
      } else if (top[1] === 'name') {
        name = top[2].replace(/^(["'])(.*)\1$/, '$2')
      }

      continue
    }

    if (!inColors) continue

    const match = COLOR_LINE.exec(line)

    if (!match) throw new Error(`skin YAML line ${index + 1}: unparseable colour ${JSON.stringify(line)}`)
    const value = match[2] ?? match[3] ?? match[4]

    if (match[1] in colors) throw new Error(`skin YAML: duplicate colour ${match[1]}`)
    colors[match[1]] = value
  }

  if (!name) throw new Error('skin YAML: no name')
  if (!colors || Object.keys(colors).length === 0) throw new Error('skin YAML: no colors')

  return { name, colors }
}

export function readJanitorSkin(file = SKIN_FILE) {
  return parseSkinYaml(fs.readFileSync(file, 'utf8'))
}

// Single-quoted TS string literal (the desktop's code style).
const tsString = value => `'${String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`

/** A skin colour the look depends on; a skin without it fails the build. */
function lookColor(skin, key) {
  const value = skin.colors[key]

  if (!value) throw new Error(`skin YAML: the desktop look needs colors.${key}`)

  return value
}

export const BANNER_ASSET = 'janitor-logo-banner.png'

/** TypeScript source of the preset injected into presets.ts. */
export function janitorPresetSource(skin) {
  const colors = Object.entries(skin.colors)
    .map(([key, value]) => `  ${key}: ${tsString(value)}`)
    .join(',\n')

  return (
    '// Janitor build (F1-13): the `colors:` block of assets/janitor/sentry-janitor.yaml,\n' +
    '// embedded at build time and converted by the same skinToDesktopTheme the\n' +
    '// backend skin goes through. A built-in name is never re-registered from the\n' +
    '// backend, so this IS the skin theme, not a look-alike.\n' +
    `const JANITOR_SKIN_COLORS: Record<string, string> = {\n${colors}\n}\n\n` +
    '// Línea gráfica (F1-18). Upstream\'s converter reads neither `ui_primary` nor a\n' +
    '// GUI background from a terminal skin, so two skin colours are routed by hand:\n' +
    '// `completion_menu_bg` (the skin\'s "Background") seeds the app background, and\n' +
    '// `ui_primary` becomes the primary (buttons, switches). The accent, rings and\n' +
    '// links stay on `ui_accent`, as in the TUI.\n' +
    'const janitorBase = skinToDesktopTheme({\n' +
    `  name: ${tsString(skin.name)},\n` +
    `  colors: { ...JANITOR_SKIN_COLORS, background: ${tsString(lookColor(skin, 'completion_menu_bg'))} }\n` +
    '}) as DesktopTheme\n\n' +
    'const janitorColors: DesktopTheme[\'colors\'] = {\n' +
    '  ...janitorBase.colors,\n' +
    `  primary: ${tsString(lookColor(skin, 'ui_primary'))},\n` +
    `  primaryForeground: ${tsString(lookColor(skin, 'completion_menu_bg'))}\n` +
    '}\n\n' +
    'export const janitorTheme: DesktopTheme = {\n' +
    '  ...janitorBase,\n' +
    '  colors: janitorColors,\n' +
    '  darkColors: janitorColors,\n' +
    `  label: ${tsString(JANITOR_THEME_LABEL)},\n` +
    `  description: ${tsString(JANITOR_THEME_DESCRIPTION)}\n` +
    '}\n\n'
  )
}

export function themePatches(skin = readJanitorSkin()) {
  return [
    {
      id: 'P12-theme-import',
      purpose: 'presets.ts imports upstream skinToDesktopTheme (no cycle: skin.ts imports color/types only)',
      file: 'src/themes/presets.ts',
      find: "import type { DesktopTheme, DesktopThemeTypography } from './types'\n",
      replace: "import { skinToDesktopTheme } from './skin'\nimport type { DesktopTheme, DesktopThemeTypography } from './types'\n",
      count: 1
    },
    {
      id: 'P12-theme-preset',
      purpose: 'Built-in `sentry-janitor` theme from the skin YAML, first in the picker; every upstream theme stays',
      file: 'src/themes/presets.ts',
      find: 'export const BUILTIN_THEMES: Record<string, DesktopTheme> = {\n  nous: nousTheme,\n',
      replace:
        janitorPresetSource(skin) +
        `export const BUILTIN_THEMES: Record<string, DesktopTheme> = {\n  ${tsString(skin.name)}: janitorTheme,\n  nous: nousTheme,\n`,
      count: 1
    },
    {
      id: 'P12-theme-default',
      purpose: 'Default skin when nothing is stored (or the stored one is retired): nous → sentry-janitor',
      file: 'src/themes/presets.ts',
      find: "export const DEFAULT_SKIN_NAME = 'nous'",
      replace: `export const DEFAULT_SKIN_NAME = ${tsString(skin.name)}`,
      count: 1
    },
    {
      id: 'P12-mode-default',
      purpose: 'Renderer mode with nothing stored: system → dark (a stored light/dark/system pick still wins)',
      file: 'src/themes/context.tsx',
      find: "  value === 'light' || value === 'dark' || value === 'system' ? value : 'system'\n",
      replace: "  value === 'light' || value === 'dark' || value === 'system' ? value : 'dark' // Janitor build: dark by default\n",
      count: 1
    },
    {
      id: 'P12-native-theme-default',
      purpose: 'Native appearance on a fresh install: system → dark, so the window backing and the index.html pre-paint are dark before the renderer loads',
      file: 'electron/main.ts',
      find: "    // Missing / malformed → follow the OS like a fresh install.\n  }\n\n  return 'system'\n}\n",
      replace: "    // Missing / malformed → follow the OS like a fresh install.\n  }\n\n  return 'dark' // Janitor build: the renderer defaults to dark too\n}\n",
      count: 1
    },
    {
      id: 'P12-look-banner-import',
      purpose: 'intro.tsx: the banner image replaces the text wordmark, so its now-unused import goes',
      file: 'src/components/chat/intro.tsx',
      find: "import introCopyJsonl from './intro-copy.jsonl?raw'\nimport { Wordmark } from './wordmark'\n",
      replace: "import introCopyJsonl from './intro-copy.jsonl?raw'\n",
      count: 1
    },
    {
      id: 'P12-look-banner',
      purpose: 'Empty chat: the J4NITOR-AGENT banner (línea gráfica) instead of the fitted text wordmark; additive blend drops its black backing',
      file: 'src/components/chat/intro.tsx',
      find: '        <Wordmark className="mb-1" text={WORDMARK} />\n',
      replace:
        '        <img\n' +
        '          alt={WORDMARK}\n' +
        '          className="mx-auto mb-3 h-auto w-full max-w-3xl mix-blend-plus-lighter"\n' +
        '          height={809}\n' +
        '          src={`${import.meta.env.BASE_URL}' + BANNER_ASSET + '`}\n' +
        '          width={1942}\n' +
        '        />\n',
      count: 1
    }
  ]
}

export const THEME_PATCHES = themePatches()
