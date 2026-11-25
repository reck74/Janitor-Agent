// App↔engine compatibility contract P13 (task F1-21a, design
// docs/janitor/plans/actualizacion-diseno.md 3.2/3.3; directive #17).
//
// janitor/desktop-compat.json holds one integer, `contract`, raised only when
// the engine needs a newer app (backend start, the RPC the app uses, the API
// plugin.js uses). The build bakes the repo's number into the Electron main
// process; at boot, before any LOCAL backend starts, the app reads the engine
// checkout's copy (<resolveUpdateRoot()>/janitor/desktop-compat.json):
//   engine > app → blocking Spanish dialog («Abrir la descarga» / «Salir»), no backend;
//   engine < app → the app's updates view opens (its normal «Actualizar motor» path);
//   absent or unreadable → compatible (an engine older than the contract).
// A remote backend returns before this point (runPrimaryBackendStartup): the
// contract is about the local checkout only. A first-launch install runs after
// that gate (no engine yet: compatible), so the gate runs once more when the
// install succeeds, before the new backend starts (F1-26e); each verdict is
// acted on once and the blocking dialog is never shown twice.
//
// decideDesktopCompat is injected into main.ts as its own source text
// (Function#toString), so the tested function is byte-for-byte what ships: it
// must stay self-contained (no imports, no module constants).

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
export const COMPAT_FILE = path.join('janitor', 'desktop-compat.json')
export const FORK_RELEASE_URL = 'https://github.com/reck74/Janitor-Agent/releases/latest'

export const COMPAT_DIALOG = {
  title: 'Janitor',
  message: 'Esta app es más vieja que el motor que acabas de instalar.',
  // Per process.platform (F6-04d); any other platform gets the Linux text.
  details: {
    linux:
      'Instala la versión nueva de la app: descarga el AppImage desde el enlace y reemplaza el anterior, o actualiza el paquete con tu gestor de paquetes si la instalaste así. Tus chats y ajustes no se tocan.',
    win32:
      'Instala la versión nueva de la app: descarga el instalador (.exe) desde el enlace y ejecútalo; se instala encima de la anterior. Tus chats y ajustes no se tocan.',
    darwin:
      'Instala la versión nueva de la app: descarga el .dmg desde el enlace y arrastra Janitor a Aplicaciones para reemplazar la anterior. Tus chats y ajustes no se tocan.'
  },
  buttons: ['Abrir la descarga', 'Salir']
}

/**
 * Pure verdict. `raw` is the engine file's text, or null when it does not exist.
 * Returns { status, appContract, engineContract, releaseUrl } with status one of
 * 'compatible' | 'app_vieja' | 'motor_viejo' | 'ilegible' ('ilegible' never blocks).
 * releaseUrl is the file's release_url only when it points into the fork on
 * github.com over https; anything else falls back to the fork's latest release.
 */
export function decideDesktopCompat(appContract, raw) {
  const forkReleases = 'https://github.com/reck74/Janitor-Agent/releases/latest'
  const isContract = value => Number.isInteger(value) && value >= 1

  const forkUrl = value => {
    if (typeof value !== 'string') return null

    let url

    try {
      url = new URL(value)
    } catch {
      return null
    }

    const insideFork =
      url.protocol === 'https:' &&
      url.host === 'github.com' &&
      !url.username &&
      !url.password &&
      url.pathname.startsWith('/reck74/Janitor-Agent/')

    return insideFork ? url.href : null
  }

  const verdict = (status, engineContract = null, releaseUrl = forkReleases) => ({
    status,
    appContract,
    engineContract,
    releaseUrl
  })

  if (raw === null || raw === undefined) return verdict('compatible')
  if (!isContract(appContract)) return verdict('ilegible')

  let data

  try {
    data = JSON.parse(raw)
  } catch {
    return verdict('ilegible')
  }

  if (!data || typeof data !== 'object' || Array.isArray(data) || !isContract(data.contract)) {
    return verdict('ilegible')
  }

  const status = data.contract > appContract ? 'app_vieja' : data.contract < appContract ? 'motor_viejo' : 'compatible'

  return verdict(status, data.contract, forkUrl(data.release_url) || forkReleases)
}

/** The contract this build bakes in, from the repo's janitor/desktop-compat.json. */
export function readDesktopContract(repoRoot = REPO_ROOT) {
  const file = path.join(repoRoot, COMPAT_FILE)
  const data = JSON.parse(fs.readFileSync(file, 'utf8'))

  if (!Number.isInteger(data?.contract) || data.contract < 1) {
    throw new Error(`${file}: "contract" must be an integer >= 1, got ${JSON.stringify(data?.contract)}`)
  }

  return data.contract
}

/**
 * TypeScript injected into electron/main.ts: the baked constant, the verdict
 * function and the boot gate. Free names it relies on, all module scope in
 * main.ts: app, dialog, shell, fs, path, resolveUpdateRoot, rememberLog,
 * sendOpenUpdatesRequested; plus the global process (dialog text per platform).
 */
export function compatGateSource(contract) {
  if (!Number.isInteger(contract) || contract < 1) {
    throw new Error(`desktop contract must be an integer >= 1, got ${JSON.stringify(contract)}`)
  }

  return [
    '// Janitor build (F1-21a): app↔engine contract. The number is baked from',
    '// janitor/desktop-compat.json at build time; the engine checkout\'s copy is',
    '// read before any local backend starts (apps/desktop-janitor/brand/compat.mjs).',
    `const JANITOR_DESKTOP_CONTRACT = ${contract}`,
    '',
    decideDesktopCompat.toString(),
    '',
    'function janitorReadEngineCompat(): string | null {',
    '  try {',
    "    return fs.readFileSync(path.join(resolveUpdateRoot(), 'janitor', 'desktop-compat.json'), 'utf8')",
    '  } catch (error) {',
    '    // Absent: an engine older than the contract (compatible). Any other error reads as unreadable.',
    "    return error?.code === 'ENOENT' ? null : ''",
    '  }',
    '}',
    '',
    '// The gate runs before every local start and again after a first-launch install',
    '// (F1-26e): each verdict is acted on once, and the blocking dialog is never shown twice.',
    'let janitorCompatNotified: string | null = null',
    'let janitorCompatBlocked = false',
    '',
    'async function janitorDesktopCompatGate(): Promise<void> {',
    '  if (janitorCompatBlocked) {',
    '    // The dialog is up (or the app is quitting): no second dialog, no backend.',
    '    await new Promise<never>(() => {})',
    '  }',
    '',
    '  const verdict = decideDesktopCompat(JANITOR_DESKTOP_CONTRACT, janitorReadEngineCompat())',
    '',
    "  rememberLog(`[janitor-compat] app ${verdict.appContract}, engine ${verdict.engineContract ?? 'n/a'}: ${verdict.status}`)",
    '',
    "  if (verdict.status === 'motor_viejo') {",
    '    const notice = `${verdict.appContract}:${verdict.engineContract}`',
    '',
    '    if (janitorCompatNotified === notice) {',
    '      return',
    '    }',
    '',
    '    janitorCompatNotified = notice',
    '    // The app is newer than the engine: offer the normal engine update path.',
    '    sendOpenUpdatesRequested()',
    '',
    '    return',
    '  }',
    '',
    "  if (verdict.status !== 'app_vieja') {",
    '    return',
    '  }',
    '',
    '  janitorCompatBlocked = true',
    '',
    '  const { response } = await dialog.showMessageBox({',
    "    type: 'error',",
    `    title: ${JSON.stringify(COMPAT_DIALOG.title)},`,
    `    message: ${JSON.stringify(COMPAT_DIALOG.message)},`,
    `    detail: (${JSON.stringify(COMPAT_DIALOG.details)}[process.platform] ?? ${JSON.stringify(COMPAT_DIALOG.details.linux)}) + '\\n\\n' + verdict.releaseUrl,`,
    `    buttons: ${JSON.stringify(COMPAT_DIALOG.buttons)},`,
    '    defaultId: 0,',
    '    cancelId: 1,',
    '    noLink: true',
    '  })',
    '',
    '  if (response === 0) {',
    '    // releaseUrl is validated by decideDesktopCompat: https://github.com/reck74/Janitor-Agent/… only.',
    '    await shell',
    '      .openExternal(verdict.releaseUrl)',
    '      .catch(error => rememberLog(`[janitor-compat] openExternal failed: ${error.message}`))',
    '  }',
    '',
    '  app.quit()',
    '  // Park: this app never starts a backend against an engine it cannot speak to.',
    '  await new Promise<never>(() => {})',
    '}',
    ''
  ].join('\n')
}

export function compatPatches(contract = readDesktopContract()) {
  const source = compatGateSource(contract)

  return [
    {
      id: 'P13-compat-gate',
      purpose: 'Bake the app↔engine contract and define the boot gate (F1-21a)',
      file: 'electron/main.ts',
      find: 'function unpackedPathFor(filePath) {\n',
      replace: `${source}\nfunction unpackedPathFor(filePath) {\n`,
      count: 1
    },
    {
      id: 'P13-compat-call',
      purpose: 'Run the gate before every local backend start, after the update gate (remote connections return earlier)',
      file: 'electron/main.ts',
      find: '      waitForLocalStart: waitForUpdateToFinish\n',
      replace:
        '      waitForLocalStart: async () => {\n' +
        '        const parked = await waitForUpdateToFinish()\n' +
        '\n' +
        '        await janitorDesktopCompatGate() // Janitor build (F1-21a)\n' +
        '\n' +
        '        return parked\n' +
        '      }\n',
      count: 1
    },
    {
      id: 'P13-compat-after-bootstrap',
      purpose: 'Run the gate again once a first-launch install succeeds, before the new backend starts (F1-26e)',
      file: 'electron/main.ts',
      find: "    rememberLog('[bootstrap] bootstrap complete; marker written. Re-resolving backend.')\n",
      replace:
        "    rememberLog('[bootstrap] bootstrap complete; marker written. Re-resolving backend.')\n" +
        '    // Janitor build (F1-26e): the gate before the install saw no engine; check the one just installed.\n' +
        '    await janitorDesktopCompatGate()\n',
      count: 1
    }
  ]
}
