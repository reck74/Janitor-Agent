// First real install fixes (task F1-26, bitácora 2026-11-23; directive #17).
//
// P15 — false boot failure during the first-launch install (F1-26a). The
//   renderer's cold boot bounds desktop.getConnection() with
//   BACKEND_BOOT_WAIT_TIMEOUT_MS (45 s, src/lib/with-timeout.ts), started when
//   the window loads. On a first launch main's getConnection() does not settle
//   until the user picks «Instalar Janitor localmente» AND the installer
//   finishes (minutes), so 45 s after the window opened the renderer latched
//   "Timed out connecting to Hermes backend" (use-gateway-boot.ts boot()) and
//   BootFailureOverlay covered the install overlay. The latch (bootFailed)
//   then drops main's later progress, so the screen stayed failed after the
//   backend came up until «Reintentar». Upstream defect (main has the same
//   wait with a 180 s budget): upstream candidate.
//   Fix: the boot wait re-arms its budget while main reports an install in
//   progress, a pending setup choice, or an install that finished less than
//   one budget ago (janitorBootWaitVerdict); and a boot that still latched a
//   failure re-runs itself when the install completes
//   (janitorRetryBootAfterInstall).
// P16 — the runtime probes run the engine's Python with HERMES_HOME (F1-26b).
//   backend-probes.ts spawns `python -c "import hermes_cli.config"` and
//   `<hermes> --version` with process.env, which has no HERMES_HOME, and that
//   import creates upstream's default ~/.hermes (SOUL.md included). main.ts
//   hands the probes the home it resolved, once, at startup.
// P17 — Spanish install stage labels (F1-26d): the install overlay printed
//   the manifest's stage `name` ("python-deps" → "Python deps").
// Plus Spanish for the renderer's boot timeouts and the cause classifier that
// reads them.
//
// The functions below are injected as their own source text
// (Function#toString), so what the tests call is byte-for-byte what ships:
// they must stay self-contained (no imports, no module constants).

/**
 * Should the renderer keep waiting for the backend after a boot budget ran
 * out? `bootstrap` is main's install snapshot (hermes:bootstrap:get), or null
 * when it could not be read. Returns { wait, reason }.
 */
export function janitorBootWaitVerdict(bootstrap, now, budgetMs) {
  if (!bootstrap || typeof bootstrap !== 'object') return { wait: false, reason: 'sin-estado' }
  // A failed install has its own screen; the boot failure is real.
  if (bootstrap.error) return { wait: false, reason: 'instalacion-fallida' }
  if (bootstrap.active) return { wait: true, reason: 'instalando' }
  // Main is waiting for the user to choose local install or remote.
  if (bootstrap.setupChoice) return { wait: true, reason: 'eligiendo' }

  const completedAt = bootstrap.completedAt

  // The backend starts right after the install: give it one full budget.
  if (typeof completedAt === 'number' && Number.isFinite(completedAt) && now - completedAt < budgetMs) {
    return { wait: true, reason: 'recien-instalado' }
  }

  return { wait: false, reason: 'sin-instalacion' }
}

/**
 * Should a boot that already concluded in failure run again because of this
 * install event? Only a completed install, only while the failure is the
 * current state of an unfinished boot, never during a connection switch.
 */
export function janitorRetryBootAfterInstall(eventType, state) {
  return (
    eventType === 'complete' &&
    Boolean(state) &&
    state.bootFailed === true &&
    state.bootCompleted !== true &&
    state.cancelled !== true &&
    state.switching !== true
  )
}

/** Spanish label for an installer stage name; null for an unknown stage (upstream formatting). */
export function janitorStageLabel(name) {
  const labels = {
    // scripts/install.sh (Linux, macOS)
    prerequisites: 'Requisitos del sistema',
    repository: 'Descarga de Janitor',
    venv: 'Entorno de Python',
    'python-deps': 'Dependencias de Python',
    'node-deps': 'Herramientas del navegador',
    path: 'Comando janitor',
    config: 'Configuración y skills',
    setup: 'Claves y ajustes',
    gateway: 'Servicio de mensajería',
    complete: 'Finalizar',
    // scripts/install.ps1 (Windows)
    uv: 'Gestor de paquetes uv',
    git: 'Git',
    node: 'Node.js',
    'system-packages': 'ripgrep y ffmpeg',
    python: 'Python',
    dependencies: 'Dependencias de Python',
    desktop: 'App de escritorio',
    'config-templates': 'Plantillas de configuración',
    'platform-sdks': 'Kits de mensajería',
    'bootstrap-marker': 'Marca de instalación',
    configure: 'Claves y modelos'
  }

  return Object.prototype.hasOwnProperty.call(labels, name) ? labels[name] : null
}

export const BOOT_TIMEOUT_ES = 'Se agotó el tiempo de espera al conectar con el backend de Janitor'
export const RECONNECT_TIMEOUT_ES = 'Se agotó el tiempo de espera al reconectar con el backend de Janitor'

/**
 * Module-level TypeScript injected into use-gateway-boot.ts. Free names, all
 * module scope there: withTimeout, RECONNECT_ATTEMPT_TIMEOUT_MS, window.
 */
export function bootWaitSource() {
  return [
    '// Janitor build (F1-26a): the cold-boot wait outlasts a first-launch install',
    '// (apps/desktop-janitor/brand/install-boot.mjs).',
    janitorBootWaitVerdict.toString(),
    '',
    janitorRetryBootAfterInstall.toString(),
    '',
    'async function janitorAwaitBackend<T>(promise: Promise<T>, budgetMs: number, message: string): Promise<T> {',
    '  for (;;) {',
    '    try {',
    '      return await withTimeout(promise, budgetMs, message)',
    '    } catch (error) {',
    "      if ((error as Error | null)?.name !== 'TimeoutError') {",
    '        throw error',
    '      }',
    '',
    '      // Bounded like every main-process round-trip (#93454); unreadable means no install.',
    '      const bootstrap = await withTimeout(',
    '        Promise.resolve(window.hermesDesktop?.getBootstrapState?.()),',
    '        RECONNECT_ATTEMPT_TIMEOUT_MS,',
    '        message',
    '      ).catch(() => null)',
    '',
    '      if (!janitorBootWaitVerdict(bootstrap, Date.now(), budgetMs).wait) {',
    '        throw error',
    '      }',
    '    }',
    '  }',
    '}',
    ''
  ].join('\n')
}

/** TypeScript injected into backend-probes.ts after PROBE_TIMEOUT_MS. */
export function probeHomeSource() {
  return [
    '',
    '// Janitor build (F1-26b): importing hermes_cli.config without HERMES_HOME creates',
    "// upstream's default home. main.ts hands over the home it resolved at startup.",
    'let janitorProbeHermesHome: string | null = null',
    '',
    'function janitorSetProbeHermesHome(home: string | null | undefined) {',
    '  janitorProbeHermesHome = home || null',
    '}',
    '',
    'function janitorProbeEnv(extra: Record<string, string> = {}): NodeJS.ProcessEnv {',
    '  return {',
    '    ...process.env,',
    '    ...(janitorProbeHermesHome ? { HERMES_HOME: janitorProbeHermesHome } : {}),',
    '    ...extra',
    '  }',
    '}',
    ''
  ].join('\n')
}

export const INSTALL_BOOT_PATCHES = [
  // ---- P15: no false boot failure during the install ------------------------
  {
    id: 'P15-boot-wait-helpers',
    purpose: 'Define the install-aware boot wait (janitorBootWaitVerdict, janitorAwaitBackend) and the recovery rule',
    file: 'src/app/gateway/hooks/use-gateway-boot.ts',
    find: 'const BOOT_RETRY_BASE_DELAY_MS = 2_000\n',
    replace: `const BOOT_RETRY_BASE_DELAY_MS = 2_000\n\n${bootWaitSource()}`,
    count: 1
  },
  {
    id: 'P15-boot-wait-call',
    purpose: 'Cold boot: the getConnection() budget re-arms while an install is running, pending or just finished',
    file: 'src/app/gateway/hooks/use-gateway-boot.ts',
    find:
      '        const conn = await withTimeout(\n' +
      '          getWindowBackend(true),\n' +
      '          BACKEND_BOOT_WAIT_TIMEOUT_MS,\n' +
      "          'Timed out connecting to Hermes backend'\n" +
      '        )\n',
    replace:
      '        const conn = await janitorAwaitBackend(\n' +
      '          getWindowBackend(true),\n' +
      '          BACKEND_BOOT_WAIT_TIMEOUT_MS,\n' +
      `          '${BOOT_TIMEOUT_ES}'\n` +
      '        )\n',
    count: 1
  },
  {
    id: 'P15-boot-recover-on-install',
    purpose: 'A boot that latched a failure re-runs itself when the install completes (no «Reintentar» needed)',
    file: 'src/app/gateway/hooks/use-gateway-boot.ts',
    find: '    const offBootProgress = desktop.onBootProgress(payload => {\n',
    replace:
      '    // Janitor build (F1-26a): the install finished after this boot gave up.\n' +
      '    const offJanitorInstallDone = desktop.onBootstrapEvent?.(event => {\n' +
      '      const state = { bootFailed, bootCompleted, cancelled, switching: $gatewaySwitching.get() }\n' +
      '\n' +
      '      if (!janitorRetryBootAfterInstall(event?.type, state)) {\n' +
      '        return\n' +
      '      }\n' +
      '\n' +
      '      bootFailed = false\n' +
      '      bootRetryAttempt = 0\n' +
      '      clearBootRetryTimer()\n' +
      "      resumeDesktopBootForRetry(translateNow('boot.steps.startingDesktopConnection'))\n" +
      '      void boot()\n' +
      '    })\n' +
      '\n' +
      '    const offBootProgress = desktop.onBootProgress(payload => {\n',
    count: 1
  },
  {
    id: 'P15-boot-recover-cleanup',
    purpose: 'Unsubscribe the install listener with the rest of the boot effect',
    file: 'src/app/gateway/hooks/use-gateway-boot.ts',
    find: '      offBootProgress()\n',
    replace: '      offBootProgress()\n      offJanitorInstallDone?.()\n',
    count: 1
  },
  {
    id: 'P15-reconnect-timeout-es',
    purpose: 'Soft switch / reconnect timeout message in Spanish',
    file: 'src/app/gateway/hooks/use-gateway-boot.ts',
    find: "'Timed out reconnecting to Hermes backend'",
    replace: `'${RECONNECT_TIMEOUT_ES}'`,
    count: 2
  },
  {
    id: 'P15-request-timeout-es',
    purpose: 'Request-path reconnect timeout message in Spanish',
    file: 'src/app/gateway/hooks/use-gateway-request.ts',
    find: "'Timed out reconnecting to Hermes backend'",
    replace: `'${RECONNECT_TIMEOUT_ES}'`,
    count: 1
  },
  {
    id: 'P15-timeout-cause-es',
    purpose: 'Boot failure classifier: the Spanish timeout messages still read as «no respondió a tiempo»',
    file: 'src/components/boot-failure-cause.ts',
    find: "  ['timedOut', /timed out|timeout/i],\n",
    replace: "  ['timedOut', /timed out|timeout|tiempo de espera/i],\n",
    count: 1
  },

  // ---- P16: probes carry the Janitor home -----------------------------------
  {
    id: 'P16-probe-home-state',
    purpose: 'backend-probes.ts: probe environment with the home main resolved',
    file: 'electron/backend-probes.ts',
    find: 'const PROBE_TIMEOUT_MS = resolveProbeTimeoutMs()\n',
    replace: `const PROBE_TIMEOUT_MS = resolveProbeTimeoutMs()\n${probeHomeSource()}`,
    count: 1
  },
  {
    id: 'P16-probe-home-import',
    purpose: 'canImportHermesCli (import hermes_cli.config) runs with HERMES_HOME',
    file: 'electron/backend-probes.ts',
    find: '      env: { ...process.env, ...(opts.env || {}) },\n',
    replace: '      env: janitorProbeEnv(opts.env || {}),\n',
    count: 1
  },
  {
    id: 'P16-probe-home-version',
    purpose: 'verifyHermesCli (`<hermes> --version`) runs with HERMES_HOME',
    file: 'electron/backend-probes.ts',
    find: "    await execProbe(hermesCommand, ['--version'], {\n",
    replace: "    await execProbe(hermesCommand, ['--version'], {\n      env: janitorProbeEnv(),\n",
    count: 1
  },
  {
    id: 'P16-probe-home-export',
    purpose: 'Export the setter',
    file: 'electron/backend-probes.ts',
    find: 'export {\n  canImportHermesCli,\n',
    replace: 'export {\n  canImportHermesCli,\n  janitorSetProbeHermesHome,\n',
    count: 1
  },
  {
    id: 'P16-probe-home-main-import',
    purpose: 'main.ts imports the setter',
    file: 'electron/main.ts',
    find: "import { canImportHermesCli, PROBE_TIMEOUT_MS, shouldTrustHermesOverride, verifyHermesCli } from './backend-probes'\n",
    replace:
      'import {\n' +
      '  canImportHermesCli,\n' +
      '  janitorSetProbeHermesHome,\n' +
      '  PROBE_TIMEOUT_MS,\n' +
      '  shouldTrustHermesOverride,\n' +
      '  verifyHermesCli\n' +
      "} from './backend-probes'\n",
    count: 1
  },
  {
    id: 'P16-probe-home-main-set',
    purpose: 'main.ts hands the resolved home (~/.janitor after P1) to every runtime probe',
    file: 'electron/main.ts',
    find: 'const HERMES_HOME = resolveHermesHome()\n',
    replace:
      'const HERMES_HOME = resolveHermesHome()\n' +
      'janitorSetProbeHermesHome(HERMES_HOME) // Janitor build (F1-26b): probes never create ~/.hermes\n',
    count: 1
  },

  // ---- P17: install stage labels in Spanish ---------------------------------
  {
    id: 'P17-stage-labels',
    purpose: 'Install overlay: Spanish label per installer stage (stage rows and «ahora: …»)',
    file: 'src/components/desktop-install-overlay.tsx',
    find: "function formatStageName(name: string): string {\n  // 'system-packages' -> 'System packages'; 'uv' stays 'uv'\n",
    replace:
      '// Janitor build (F1-26d): Spanish stage labels (apps/desktop-janitor/brand/install-boot.mjs).\n' +
      `${janitorStageLabel.toString()}\n\n` +
      'function formatStageName(name: string): string {\n' +
      '  const janitorLabel = janitorStageLabel(name)\n' +
      '\n' +
      '  if (janitorLabel) {\n' +
      '    return janitorLabel\n' +
      '  }\n' +
      '\n' +
      "  // 'system-packages' -> 'System packages'; 'uv' stays 'uv'\n",
    count: 1
  }
]
