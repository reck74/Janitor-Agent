// Structural build patches P1-P5 (plan section 4.2, directive #17), P13,
// the app↔engine contract gate (F1-21a, brand/compat.mjs), and P14, the slash
// palette in Spanish (F1-19, brand/palette.mjs; before P10/P6 so the catalog
// guard also sees the skill rows it adds to es.ts).
// Anchors are exact source text of apps/desktop; `count` is the exact number
// of matches expected. A mismatch fails the build naming the patch id.

import { compatPatches } from './compat.mjs'
import { palettePatches } from './palette.mjs'

export const STRUCTURAL_PATCHES = [
  {
    id: 'P1-home',
    purpose: 'Default HERMES_HOME on macOS/Linux: ~/.hermes → ~/.janitor (Windows %LOCALAPPDATA%\\hermes untouched)',
    file: 'electron/main.ts',
    find: "  return path.join(app.getPath('home'), '.hermes')\n}\n\nconst HERMES_HOME = resolveHermesHome()",
    replace: "  return path.join(app.getPath('home'), '.janitor')\n}\n\nconst HERMES_HOME = resolveHermesHome()",
    count: 1
  },
  {
    id: 'P2-installer-source',
    purpose: 'First-run installer download: NousResearch/hermes-agent → reck74/Janitor-Agent',
    file: 'electron/bootstrap-runner.ts',
    find: 'https://raw.githubusercontent.com/NousResearch/hermes-agent/${ref}/scripts/${scriptName}',
    replace: 'https://raw.githubusercontent.com/reck74/Janitor-Agent/${ref}/scripts/${scriptName}',
    count: 1
  },
  {
    id: 'P3-backend-module',
    purpose: 'Backend entry point: python -m hermes_cli.main → python -m janitor.cli (managed runtime, dev checkout, override root)',
    file: 'electron/main.ts',
    find: "args: ['-m', 'hermes_cli.main', ...backendArgs],",
    replace: "args: ['-m', 'janitor.cli', ...backendArgs],",
    count: 3
  },
  {
    id: 'P3-no-path-hermes',
    purpose: 'Never adopt an upstream `hermes` found on PATH as the backend (HERMES_DESKTOP_HERMES override still honoured)',
    file: 'electron/main.ts',
    find: "    } else {\n      hermesCommand = findOnPath('hermes')\n    }",
    replace: "    } else {\n      hermesCommand = null // Janitor build: an upstream `hermes` on PATH is not Janitor\n    }",
    count: 1
  },
  {
    id: 'P3-no-system-python',
    purpose: 'Never adopt a system Python that merely imports upstream hermes_cli; fall through to the Janitor bootstrap',
    file: 'electron/main.ts',
    find: '  const python = await findSystemPython()\n\n  if (python) {\n    // Same smoke-test rationale as step 4',
    replace:
      '  const python = null as string | null // Janitor build: a system-wide hermes_cli is upstream Hermes\n\n  if (python) {\n    // Same smoke-test rationale as step 4',
    count: 1
  },
  {
    id: 'P3-ownership-matcher',
    purpose: 'Orphan-backend reaping recognises `-m janitor.cli serve` command lines',
    file: 'electron/backend-ownership.ts',
    find: '(?:hermes(?:\\.exe)?|hermes_cli\\.main|hermes_cli[/\\\\]main\\.py)',
    replace: '(?:hermes(?:\\.exe)?|hermes_cli\\.main|hermes_cli[/\\\\]main\\.py|janitor\\.cli)',
    count: 1
  },
  {
    id: 'P4-locale',
    purpose: 'Default UI language: en → es',
    file: 'src/i18n/languages.ts',
    find: "export const DEFAULT_LOCALE: Locale = 'en'",
    replace: "export const DEFAULT_LOCALE: Locale = 'es'",
    count: 1
  },
  {
    id: 'P5-app-name',
    purpose: 'APP_NAME default (app.setName, macOS menu, About, HUD title): Hermes → Janitor',
    file: 'electron/main.ts',
    find: "const APP_NAME = process.env.HERMES_DESKTOP_APP_NAME || 'Hermes'",
    replace: "const APP_NAME = process.env.HERMES_DESKTOP_APP_NAME || 'Janitor'",
    count: 1
  },
  {
    id: 'P5-window-titles',
    purpose: 'BrowserWindow titles: Hermes → Janitor',
    file: 'electron/main.ts',
    find: "    title: 'Hermes',",
    replace: "    title: 'Janitor',",
    count: 4
  },
  {
    id: 'P5-html-title',
    purpose: 'index.html <title>',
    file: 'index.html',
    find: '<title>Hermes</title>',
    replace: '<title>Janitor</title>',
    count: 1
  },
  {
    id: 'P5-html-lang',
    purpose: 'index.html document language',
    file: 'index.html',
    find: '<html lang="en">',
    replace: '<html lang="es">',
    count: 1
  },
  // Contract number read from janitor/desktop-compat.json when this module loads.
  ...compatPatches(),
  ...palettePatches()
]
