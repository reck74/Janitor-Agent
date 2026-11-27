// P22 (plan docs/janitor/plans/actualizacion-automatica.md, Fase 9: F9-04, F9-05,
// F9-08): the app checks its OWN version at startup, downloads and verifies the
// new installer before it closes, and hands it to the relay script.
//
// The logic is brand/app-update.mjs, copied by the build to
// electron/janitor-app-update.mjs (scripts/build.mjs OVERLAY_FILES) and
// imported by main.ts; what is injected here is only the wiring to main.ts's
// own primitives and three call sites:
//   - checkUpdates: the status gains `janitorApp` and `updateAvailable` is also
//     true when the engine is current but the app is old (the case of
//     2026-11-27); a cached status only answers for the app version that made it;
//   - applyUpdatesPosixHandoff: verify + download first, then pass the delivery
//     to scripts/desktop-update/posix.sh. Unknown install kinds, builds without
//     key and engines older than the relay's app stage get `[]`: exactly today's
//     hand-off;
//   - the renderer: one notice with «Actualizar ahora» / «Más tarde», and
//     «Actualizar siempre sin preguntar» in Ajustes → Acerca de (decision 7.1).
//
// The public key (brand/update-key.pem, PEM/SPKI Ed25519) is baked into the
// app. It is the project owner's: no agent creates it. Without the file the
// build bakes `null` and the app never updates itself (today's behaviour).

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const BRAND_DIR = path.dirname(fileURLToPath(import.meta.url))
export const UPDATE_KEY_FILE = path.join(BRAND_DIR, 'update-key.pem')
export const RUNTIME_MODULE = 'electron/janitor-app-update.mjs'

/** The release public key as PEM text, or null when the repo has none. Throws on a file that is not an Ed25519 public key. */
export function readUpdatePublicKey(file = UPDATE_KEY_FILE) {
  if (!fs.existsSync(file)) return null

  const pem = fs.readFileSync(file, 'utf8')
  const key = crypto.createPublicKey(pem)

  if (key.asymmetricKeyType !== 'ed25519') {
    throw new Error(`${file}: the update key must be an Ed25519 public key, got ${key.asymmetricKeyType}`)
  }

  return key.export({ type: 'spki', format: 'pem' })
}

/** TypeScript injected into electron/main.ts. Free names, all module scope there:
 *  app, fs, path, spawn, HERMES_HOME, rememberLog, emitUpdateProgress, findOnPath, checkUpdates. */
export function appUpdateGlueSource(publicKeyPem) {
  return [
    '// Janitor build (P22, apps/desktop-janitor/brand/app-update-patches.mjs): signed updates of',
    '// the app itself. The logic is ./janitor-app-update.mjs (brand/app-update.mjs, byte for byte).',
    `const JANITOR_UPDATE_PUBLIC_KEY: string | null = ${publicKeyPem ? JSON.stringify(publicKeyPem) : 'null'}`,
    '',
    '// The pacman package that owns a file, or null (no pacman, not owned, any error).',
    'function janitorPackageOwner(file: string): Promise<string | null> {',
    '  return new Promise(resolve => {',
    "    if (!fs.existsSync('/usr/bin/pacman')) {",
    '      resolve(null)',
    '',
    '      return',
    '    }',
    '',
    "    let out = ''",
    "    const child = spawn('/usr/bin/pacman', ['-Qqo', '--', file], { stdio: ['ignore', 'pipe', 'ignore'] })",
    '',
    "    child.stdout.on('data', chunk => {",
    '      out += String(chunk)',
    '    })',
    "    child.on('error', () => resolve(null))",
    "    child.on('close', code => resolve(code === 0 ? out.trim().split(/\\s+/)[0] || null : null))",
    '  })',
    '}',
    '',
    'const janitorUpdater = janitorAppUpdate.createDesktopUpdater({',
    '  appVersion: app.getVersion(),',
    '  platform: process.platform,',
    '  arch: process.arch,',
    '  env: process.env,',
    '  execPath: process.execPath,',
    '  hermesHome: HERMES_HOME,',
    '  publicKeyPem: JANITOR_UPDATE_PUBLIC_KEY,',
    '  fetchImpl: (url, init) => fetch(url, init),',
    '  packageOwner: janitorPackageOwner,',
    '  pathLookup: command => findOnPath(command),',
    '  log: message => rememberLog(message),',
    '  progress: payload => emitUpdateProgress(payload)',
    '})',
    ''
  ].join('\n')
}

const AUTO_UPDATE_TITLE = 'Actualizar siempre sin preguntar'
const AUTO_UPDATE_DESC =
  'Cuando haya una versión nueva, Janitor la descarga, se cierra, la instala y vuelve a abrirse sin preguntarte. Si tu sistema pide contraseña para instalar, te la pedirá igual.'

export const NOTICE = {
  title: 'Hay una versión nueva de Janitor',
  now: 'Actualizar ahora',
  later: 'Más tarde',
  autoTitle: AUTO_UPDATE_TITLE,
  autoDescription: AUTO_UPDATE_DESC
}

export function appUpdatePatches(publicKeyPem = readUpdatePublicKey()) {
  return [
    // ---- main process ----
    {
      id: 'P22-import',
      purpose: 'Import the signed-update logic the build copies to electron/janitor-app-update.mjs',
      file: 'electron/main.ts',
      find: "import { readAndConsumeHandoffResult } from './handoff-result'\n",
      replace:
        "import { readAndConsumeHandoffResult } from './handoff-result'\n" +
        '// @ts-ignore Janitor build (P22): plain JS module copied in by the build\n' +
        "import * as janitorAppUpdate from './janitor-app-update.mjs'\n",
      count: 1
    },
    {
      id: 'P22-glue',
      purpose: 'Bake the release public key and build the updater from main.ts primitives',
      file: 'electron/main.ts',
      find: 'function readUpdateCheckCache() {\n',
      replace: `${appUpdateGlueSource(publicKeyPem)}\nfunction readUpdateCheckCache() {\n`,
      count: 1
    },
    {
      id: 'P22-check-cache',
      purpose: 'A cached update status only answers for the app version that produced it',
      file: 'electron/main.ts',
      find: '  if (!force && cacheIsFresh(cached, { branch, currentSha, now })) {\n',
      replace: '  if (!force && janitorUpdater.cacheMatchesApp(cached) && cacheIsFresh(cached, { branch, currentSha, now })) {\n',
      count: 1
    },
    {
      id: 'P22-check-app',
      purpose: 'checkUpdates also compares the app with the version the channel published (engine current, app old)',
      file: 'electron/main.ts',
      find:
        '  writeUpdateCheckCache({ fetchedAt: now, currentSha, branch, status: result })\n\n  return result\n}\n',
      replace:
        '  // Janitor build (P22): the app is part of the update too.\n' +
        '  const janitorResult = await janitorUpdater.augmentStatus(result)\n\n' +
        '  writeUpdateCheckCache({ fetchedAt: now, currentSha, branch, status: janitorResult })\n\n  return janitorResult\n}\n',
      count: 1
    },
    {
      id: 'P22-handoff',
      purpose: 'Verify the release and download the installer before closing; hand the delivery to posix.sh',
      file: 'electron/main.ts',
      find:
        "  const args = [...handoff.args, '--install-root', updateRoot, '--branch', branch, '--desktop-pid', String(process.pid)]\n",
      replace:
        '  // Janitor build (P22): download and verify first, change things afterwards. A refusal\n' +
        '  // returns before anything is spawned: nothing was changed.\n' +
        '  let janitorRelayText = \'\'\n\n' +
        '  try {\n' +
        "    janitorRelayText = fs.readFileSync(handoff.scriptPath, 'utf8')\n" +
        '  } catch {\n' +
        '    // unreadable: treated as a relay without the app stage (engine-only hand-off)\n' +
        '  }\n\n' +
        '  const janitorDelivery = await janitorUpdater.prepareHandoff({\n' +
        '    freshStatus: () => checkUpdates({ force: true }),\n' +
        '    relayScriptText: janitorRelayText\n' +
        '  })\n\n' +
        '  if (janitorDelivery.failure) {\n' +
        '    return janitorDelivery.failure\n' +
        '  }\n\n' +
        "  const args = [...handoff.args, '--install-root', updateRoot, '--branch', branch, '--desktop-pid', String(process.pid), ...janitorDelivery.args]\n",
      count: 1
    },
    // ---- renderer ----
    {
      id: 'P22-status-type',
      purpose: 'DesktopUpdateStatus carries the app side of the check',
      file: 'src/global.d.ts',
      find: 'export interface DesktopUpdateStatus {\n  supported: boolean\n',
      replace:
        'export interface DesktopUpdateStatus {\n  supported: boolean\n' +
        '  /** Janitor build (P22): the app itself, compared with the published version. */\n' +
        '  janitorApp?: {\n' +
        '    appVersion: string\n' +
        '    kind: string\n' +
        '    selfUpdate: boolean\n' +
        '    reason: string\n' +
        '    publishedVersion: string | null\n' +
        '    needsApp: boolean\n' +
        '    error: string | null\n' +
        '  }\n',
      count: 1
    },
    {
      id: 'P22-auto-setting',
      purpose: '«Actualizar siempre sin preguntar»: persisted choice, off by default',
      file: 'src/store/updates.ts',
      find: 'export const $updateStatus = atom<DesktopUpdateStatus | null>(null)\n',
      replace:
        'export const $updateStatus = atom<DesktopUpdateStatus | null>(null)\n\n' +
        '// Janitor build (P22, plan decision 7.1): ask at startup by default; the user can\n' +
        '// choose in Ajustes → Acerca de to update without being asked.\n' +
        "const JANITOR_AUTO_UPDATE_KEY = 'janitor.updates.auto'\n" +
        "export const $janitorAutoUpdate = atom<boolean>(storedString(JANITOR_AUTO_UPDATE_KEY) === '1')\n\n" +
        'export function setJanitorAutoUpdate(enabled: boolean): void {\n' +
        "  persistString(JANITOR_AUTO_UPDATE_KEY, enabled ? '1' : '0')\n" +
        '  $janitorAutoUpdate.set(enabled)\n' +
        '}\n\n' +
        '// At most one unattended start per run of the app: a failed update must not loop.\n' +
        'let janitorAutoUpdateStarted = false\n',
      count: 1
    },
    {
      id: 'P22-notice',
      purpose: 'One notice for engine and app: «Actualizar ahora» / «Más tarde», or no question when the user chose so',
      file: 'src/store/updates.ts',
      find:
        '  if (isUpdateToastSnoozed()) {\n    return\n  }\n\n' +
        '  if ($updateApply.get().applying) {\n    return\n  }\n\n' +
        '  notify({\n    action: {\n' +
        "      label: translateNow('notifications.seeWhatsNew'),\n" +
        '      onClick: () => {\n        snoozeUpdateToast()\n        openUpdateOverlayFor(target)\n      }\n    },\n',
      replace:
        '  if ($updateApply.get().applying) {\n    return\n  }\n\n' +
        '  // Janitor build (P22): the user chose not to be asked.\n' +
        "  if (target === 'client' && $janitorAutoUpdate.get() && !janitorAutoUpdateStarted) {\n" +
        '    janitorAutoUpdateStarted = true\n' +
        "    startActiveUpdate('client')\n\n" +
        '    return\n  }\n\n' +
        '  if (isUpdateToastSnoozed()) {\n    return\n  }\n\n' +
        '  notify({\n    action: {\n' +
        `      label: ${JSON.stringify(NOTICE.now)},\n` +
        '      onClick: () => {\n        snoozeUpdateToast()\n        startActiveUpdate(target)\n      }\n    },\n' +
        '    secondaryAction: {\n' +
        `      label: ${JSON.stringify(NOTICE.later)},\n` +
        '      onClick: () => snoozeUpdateToast()\n    },\n',
      count: 1
    },
    {
      id: 'P22-notice-title',
      purpose: 'Notice title names the product, not a commit count',
      file: 'src/store/updates.ts',
      find: "    onDismiss: () => snoozeUpdateToast(),\n    title: translateNow('notifications.updateReadyTitle')\n",
      replace: `    onDismiss: () => snoozeUpdateToast(),\n    title: ${JSON.stringify(NOTICE.title)}\n`,
      count: 1
    },
    {
      id: 'P22-settings-imports',
      purpose: 'Ajustes → Acerca de: the switch and its store',
      file: 'src/app/settings/about-settings.tsx',
      find: "import { Codicon } from '@/components/ui/codicon'\n",
      replace: "import { Codicon } from '@/components/ui/codicon'\nimport { Switch } from '@/components/ui/switch'\n",
      count: 1
    },
    {
      id: 'P22-settings-store',
      purpose: 'Ajustes → Acerca de: read the persisted choice',
      file: 'src/app/settings/about-settings.tsx',
      find: '  const checking = useStore($updateChecking)\n',
      replace: '  const checking = useStore($updateChecking)\n  const janitorAuto = useStore($janitorAutoUpdate) // Janitor build (P22)\n',
      count: 1
    },
    {
      id: 'P22-settings-store-import',
      purpose: 'Ajustes → Acerca de: import the choice from the updates store',
      file: 'src/app/settings/about-settings.tsx',
      find: '  $updateChecking,\n  $updateStatus,\n',
      replace: '  $janitorAutoUpdate,\n  $updateChecking,\n  $updateStatus,\n  setJanitorAutoUpdate,\n',
      count: 1
    },
    {
      id: 'P22-settings-row',
      purpose: 'Ajustes → Acerca de: «Actualizar siempre sin preguntar»',
      file: 'src/app/settings/about-settings.tsx',
      find: '        <ListRow\n          description={a.automaticUpdatesDesc}\n',
      replace:
        '        <ListRow\n' +
        '          action={\n' +
        `            <Switch aria-label=${JSON.stringify(AUTO_UPDATE_TITLE)} checked={janitorAuto} onCheckedChange={value => void setJanitorAutoUpdate(value)} />\n` +
        '          }\n' +
        `          description=${JSON.stringify(AUTO_UPDATE_DESC)}\n` +
        `          title=${JSON.stringify(AUTO_UPDATE_TITLE)}\n` +
        '        />\n\n' +
        '        <ListRow\n          description={a.automaticUpdatesDesc}\n',
      count: 1
    }
  ]
}

export const APP_UPDATE_PATCHES = appUpdatePatches()
