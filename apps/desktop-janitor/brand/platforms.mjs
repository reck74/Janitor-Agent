// P20 (tasks F6-04a-e, plan phase 6): Windows and macOS builds with the Janitor
// brand. Directive #17: exact anchors over apps/desktop, applied at build time
// and reverted afterwards.
//
//   P20-home-windows  ~/.janitor on Windows too (no registry HERMES_HOME, no
//                     %LOCALAPPDATA%\hermes), like the launcher (janitor/home.py).
//                     P1 already rewrites the POSIX default the Windows branch
//                     now falls through to; HERMES_HOME and
//                     HERMES_DESKTOP_USER_DATA_DIR are checked before, unchanged.
//   P20-aumid         Windows AppUserModelID = the builder appId, which
//                     electron-builder writes into the Start Menu shortcut.
//   P20-exe-identity  Version strings rcedit stamps onto Janitor.exe (Task
//                     Manager, file properties).
//   P20-mac-roles     Spanish labels for the role items of the application
//                     menu (only built on macOS): Electron labels roles in English.
//   P20-about-skew    Spanish note in the About panel when the app build is stale.
//   P20-git-for-windows  Spanish start-up error when Git Bash is missing (Windows).
//   P20-git-home-*    scripts/install.ps1 puts PortableGit in <home>\git (home =
//                     HERMES_HOME or %USERPROFILE%\.janitor), not in
//                     %LOCALAPPDATA%\hermes\git. The app's resolved home
//                     (HERMES_HOME in main.ts) is probed first for bash.exe
//                     (findGitBash) and git.exe (resolveGitBinary), so an app
//                     already open during the install, blind to the new user
//                     variable HERMES_GIT_BASH_PATH, still finds it. The variable
//                     and every upstream candidate stay, in their order.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const BUILDER_CONFIG = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'electron-builder.janitor.json')

/** The Janitor appId (electron-builder.janitor.json); the AUMID must equal it. */
export function janitorAppId(file = BUILDER_CONFIG) {
  const appId = JSON.parse(fs.readFileSync(file, 'utf8')).appId

  if (typeof appId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(appId)) {
    throw new Error(`${file}: appId must be a reverse-DNS id, got ${JSON.stringify(appId)}`)
  }

  return appId
}

export const EXE_IDENTITY = {
  ProductName: 'Janitor',
  FileDescription: 'Janitor',
  CompanyName: 'Janitor Agent'
}

// [role, Spanish label (TypeScript expression), expected count in main.ts].
// `quit` and `minimize` appear in the macOS and the other-platform branches.
export const MENU_ROLE_LABELS = [
  ['services', "'Servicios'"],
  ['hide', '`Ocultar ${APP_NAME}`'],
  ['hideOthers', "'Ocultar otros'"],
  ['unhide', "'Mostrar todo'"],
  ['quit', '`Salir de ${APP_NAME}`', 2],
  ['undo', "'Deshacer'"],
  ['redo', "'Rehacer'"],
  ['cut', "'Cortar'"],
  ['copy', "'Copiar'"],
  ['paste', "'Pegar'"],
  ['pasteAndMatchStyle', "'Pegar con el mismo estilo'"],
  ['delete', "'Eliminar'"],
  ['selectAll', "'Seleccionar todo'"],
  ['showSubstitutions', "'Mostrar sustituciones'"],
  ['toggleTextReplacement', "'Sustitución de texto'"],
  ['forceReload', "'Forzar recarga'"],
  ['togglefullscreen', "'Pantalla completa'"],
  ['minimize', "'Minimizar'", 2],
  ['zoom', "'Zoom'"],
  ['front', "'Traer todo al frente'"],
  ['close', "'Cerrar ventana'"]
]

const WINDOWS_HOME_BRANCHES = `  if (IS_WINDOWS) {
    // A GUI app launched from Explorer inherits the environment block captured
    // at login, so a HERMES_HOME set via \`setx\` AFTER login is invisible in
    // process.env even though the CLI (a fresh shell) sees it. Without this the
    // backend silently falls back to %LOCALAPPDATA%\\hermes and reports "No
    // inference provider configured" despite a valid configured home (#45471).
    // Consult the live User-scoped registry value before the default below.
    const fromRegistry = readWindowsUserEnvVar('HERMES_HOME')

    if (fromRegistry) {
      return normalizeHermesHomeRoot(fromRegistry)
    }
  }

  if (IS_WINDOWS && process.env.LOCALAPPDATA) {
    const localappdata = path.join(process.env.LOCALAPPDATA, 'hermes')
    const legacy = path.join(app.getPath('home'), '.hermes')

    // Migrate transparently to LOCALAPPDATA, but honour an existing legacy
    // ~/.hermes setup (no LOCALAPPDATA install yet) so users don't lose state.
    if (!directoryExists(localappdata) && directoryExists(legacy)) {
      return legacy
    }

    return localappdata
  }

`

export function platformPatches(appId = janitorAppId()) {
  const identityFind = "      ProductName: 'Hermes',\n      FileDescription: 'Hermes',\n      CompanyName: 'Nous Research',\n"
  const identityReplace = Object.entries(EXE_IDENTITY)
    .map(([key, value]) => `      ${key}: ${JSON.stringify(value).replace(/"/g, "'")},\n`)
    .join('')

  return [
    {
      id: 'P20-home-windows',
      purpose: 'Windows home: registry HERMES_HOME / %LOCALAPPDATA%\\hermes → falls through to ~/.janitor (P1)',
      file: 'electron/main.ts',
      find: WINDOWS_HOME_BRANCHES,
      replace:
        '  // Janitor build (F6-04a): ~/.janitor on every platform, like the launcher\n' +
        '  // (janitor/home.py). No registry HERMES_HOME and no %LOCALAPPDATA%\\hermes:\n' +
        '  // both belong to an upstream install.\n\n',
      count: 1
    },
    {
      id: 'P20-aumid',
      purpose: 'Windows AppUserModelID: com.nousresearch.hermes → the Janitor appId (Start Menu shortcut, notifications)',
      file: 'electron/main.ts',
      find: "  app.setAppUserModelId('com.nousresearch.hermes')\n",
      replace: `  app.setAppUserModelId('${appId}') // Janitor build (F6-04b): = electron-builder.janitor.json appId\n`,
      count: 1
    },
    {
      id: 'P20-exe-identity',
      purpose: 'Janitor.exe version strings stamped by rcedit: Hermes / Nous Research → Janitor',
      file: 'scripts/set-exe-identity.mjs',
      find: identityFind,
      replace: identityReplace,
      count: 1
    },
    ...MENU_ROLE_LABELS.map(([role, label, count = 1]) => ({
      id: `P20-mac-roles#${role}`,
      purpose: `Application menu role ${role}: Spanish label`,
      file: 'electron/main.ts',
      find: `{ role: '${role}' }`,
      replace: `{ role: '${role}', label: ${label} }`,
      count
    })),
    {
      id: 'P20-about-skew',
      purpose: 'About panel: stale app build note in Spanish',
      file: 'electron/main.ts',
      find: '— app build out of date, update the desktop app`',
      replace: '— la app está desactualizada, actualiza la app de escritorio`',
      count: 1
    },
    {
      id: 'P20-git-for-windows',
      purpose: 'Windows start-up error shown in the install overlay when Git Bash is missing: Spanish, Janitor',
      file: 'electron/main.ts',
      find:
        `      "Hermes needs a helper called Git for Windows, which isn't installed. " +\n` +
        "        'Choose Repair install to add it automatically, or install it yourself from git-scm.com and reopen Hermes.'\n",
      replace:
        "      'Janitor necesita un componente llamado Git para Windows, que no está instalado. ' +\n" +
        "        'Elige Reparar instalación para añadirlo automáticamente, o instálalo tú desde git-scm.com y vuelve a abrir Janitor.'\n",
      count: 1
    },
    {
      id: 'P20-git-home-option',
      purpose: 'findGitBash options: the resolved app home, where install.ps1 puts PortableGit',
      file: 'electron/find-git-bash.ts',
      find: '  findOnPath?: (command: string) => string | null\n}\n',
      replace:
        '  findOnPath?: (command: string) => string | null\n' +
        '  janitorHome?: string // Janitor build (P20-git-home): PortableGit lives in <home>\\git\n' +
        '}\n',
      count: 1
    },
    {
      id: 'P20-git-home-bash',
      purpose: 'findGitBash: <home>\\git\\bin and \\usr\\bin bash.exe before %LOCALAPPDATA%\\hermes\\git',
      file: 'electron/find-git-bash.ts',
      find: "  if (localAppData) {\n    candidates.push(joinWin(localAppData, 'hermes', 'git', 'bin', 'bash.exe'))\n",
      replace:
        '  // Janitor build (P20-git-home): scripts/install.ps1 puts PortableGit in\n' +
        '  // <home>\\git (MinGit: usr\\bin\\bash.exe), ahead of the upstream location.\n' +
        '  if (opts.janitorHome) {\n' +
        "    candidates.push(joinWin(opts.janitorHome, 'git', 'bin', 'bash.exe'))\n" +
        "    candidates.push(joinWin(opts.janitorHome, 'git', 'usr', 'bin', 'bash.exe'))\n" +
        '  }\n\n' +
        "  if (localAppData) {\n    candidates.push(joinWin(localAppData, 'hermes', 'git', 'bin', 'bash.exe'))\n",
      count: 1
    },
    {
      id: 'P20-git-home-caller',
      purpose: 'main.ts findGitBash passes the resolved app home (HERMES_HOME)',
      file: 'electron/main.ts',
      find: '  return _findGitBash({\n    isWindows: IS_WINDOWS,\n',
      replace: '  return _findGitBash({\n    janitorHome: HERMES_HOME, // Janitor build (P20-git-home)\n    isWindows: IS_WINDOWS,\n',
      count: 1
    },
    {
      id: 'P20-git-home-binary',
      purpose: 'resolveGitBinary: <home>\\git\\cmd and \\bin git.exe before %LOCALAPPDATA%\\hermes\\git',
      file: 'electron/main.ts',
      find: "  if (localAppData) {\n    candidates.push(path.join(localAppData, 'hermes', 'git', 'cmd', 'git.exe'))\n",
      replace:
        '  // Janitor build (P20-git-home): PortableGit from scripts/install.ps1 is in <home>\\git.\n' +
        "  candidates.push(path.join(HERMES_HOME, 'git', 'cmd', 'git.exe'))\n" +
        "  candidates.push(path.join(HERMES_HOME, 'git', 'bin', 'git.exe'))\n\n" +
        "  if (localAppData) {\n    candidates.push(path.join(localAppData, 'hermes', 'git', 'cmd', 'git.exe'))\n",
      count: 1
    }
  ]
}
