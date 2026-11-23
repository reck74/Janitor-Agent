// Exact-literal map for user-visible text OUTSIDE the i18n catalogs
// (patches P7: Electron main process, P8: renderer chrome). Directive #17.
//
// Each entry is [exact source text, replacement, expected count = 1]. The
// anchor is the source text byte for byte (escapes as written in the .ts file,
// hence `\\n` and `\\u2019` below); `${...}` inside these quoted strings is
// literal source text, not interpolation. Never a blanket regex: outside the
// catalogs, lowercase `hermes` is storage keys, IPC channels, protocol schemes
// and IDs.
//
// Spanish follows the terms already used in src/i18n/es.ts (backend, registro,
// Reintentar, Abrir registros, Reparar instalación, Recargar y reintentar,
// entorno de ejecución, tú).
//
// Deliberately NOT patched (see ALLOWLISTED_FILES / KEPT_LITERALS):
//   - `Details:` in bootstrap-failure-copy.ts: the install overlay splits the
//     message on that marker (src/components/desktop-install-overlay.tsx).
//   - Backend labels used only in logs, thrown Errors (inventoried in
//     brand/inventory/thrown-errors.tsv), Electron role menu items (labelled
//     by Electron itself).

export const LITERALS = {
  'electron/main.ts': [
    // Default app name (P5 sets the title-bar/window defaults; this is the
    // name used by app.setName, the macOS menu and the HUD window title).
    // — application menu —
    ["label: 'Check for Updates…'", "label: 'Buscar actualizaciones…'"],
    ['{ label: `About ${APP_NAME}`', '{ label: `Acerca de ${APP_NAME}`'],
    ["label: 'File',", "label: 'Archivo',"],
    ["label: 'New Window' }", "label: 'Nueva ventana' }"],
    ["label: 'Open Folder…' }", "label: 'Abrir carpeta…' }"],
    ["label: 'Close'", "label: 'Cerrar'"],
    ["label: 'Edit',", "label: 'Editar',"],
    ["label: 'Substitutions',", "label: 'Sustituciones',"],
    ["label: 'View',", "label: 'Ver',"],
    ["label: 'Reload' }", "label: 'Recargar' }"],
    ["label: 'Toggle Developer Tools',", "label: 'Herramientas de desarrollo',"],
    ["label: 'Actual Size',", "label: 'Tamaño real',"],
    ["label: 'Zoom In',", "label: 'Acercar',"],
    ["label: 'Zoom Out',", "label: 'Alejar',"],
    ["label: 'Window',", "label: 'Ventana',"],
    ["label: 'Help',", "label: 'Ayuda',"],
    // — update hand-off dialogs —
    ["title: 'Hermes update',", "title: 'Actualización de Janitor',", 2],
    ["message: 'The update finished, but needs one more step',", "message: 'La actualización terminó, pero falta un paso más',"],
    ['message: "Hermes couldn\'t finish updating",', "message: 'Janitor no pudo terminar la actualización',"],
    [
      '"You\'re still on the previous version and can keep using it. Try the update again, or open the update log to report the problem.\\n\\n" +',
      "'Sigues en la versión anterior y puedes seguir usándola. Vuelve a intentar la actualización o abre el registro de actualización para informar del problema.\\n\\n' +"
    ],
    ['`Details: ${result.message}`', '`Detalles: ${result.message}`'],
    ["buttons: ['Try again', 'Open log', 'Close'],", "buttons: ['Reintentar', 'Abrir registro', 'Cerrar'],"],
    // — plugin compatibility dialog —
    ["buttons: ['Open Plugins', 'OK'],", "buttons: ['Abrir plugins', 'Aceptar'],"],
    // — file dialogs —
    ["title: 'Save Image',", "title: 'Guardar imagen',"],
    ["'Save File'", "'Guardar archivo'", 3],
    ["title: options?.title || 'Add context',", "title: options?.title || 'Añadir contexto',"],
    ["title: options?.title || 'Save',", "title: options?.title || 'Guardar',"],
    ["title: 'Choose default project directory',", "title: 'Elegir directorio de proyecto predeterminado',"],
    // — boot progress (rendered verbatim by the onboarding overlay) —
    ["message: 'Waiting to start Hermes backend',", "message: 'Esperando para iniciar el backend de Janitor',"],
    [
      'message: `Still waiting for first-run setup choice after ${Math.round(stuckAfterMs / 1000)} seconds`,',
      'message: `Seguimos esperando que elijas la configuración inicial (${Math.round(stuckAfterMs / 1000)} s)`,'
    ],
    ["message: 'Waiting for first-run setup choice',", "message: 'Esperando que elijas la configuración inicial',"],
    [
      "'An update is finishing — Hermes will start automatically when it completes…'",
      "'Hay una actualización terminando; Janitor se iniciará automáticamente cuando acabe…'"
    ],
    ["'Restarting Hermes to load the updated app…'", "'Reiniciando Janitor para cargar la app actualizada…'"],
    ["advanceBootProgress('runtime.external', `Using ${backend.label}`", "advanceBootProgress('runtime.external', `Usando ${backend.label}`"],
    ["message: 'Hermes runtime is ready',", "message: 'El entorno de ejecución de Janitor está listo',"],
    ["message: 'Restarting desktop connection',", "message: 'Reiniciando la conexión de escritorio',"],
    ["'Resolving Hermes backend'", "'Buscando el backend de Janitor'", 2],
    ['`Connecting to remote Hermes backend at ${remote.baseUrl}`', '`Conectando al backend remoto de Janitor en ${remote.baseUrl}`'],
    ["message: 'Remote Hermes backend is ready',", "message: 'El backend remoto de Janitor está listo',"],
    ["'Resolving Hermes runtime'", "'Buscando el entorno de ejecución de Janitor'"],
    ["message: 'Attached to the running Hermes backend',", "message: 'Conectado al backend de Janitor en ejecución',"],
    [
      "advanceBootProgress('backend.spawn', `Starting Hermes backend via ${backend.label}`",
      "advanceBootProgress('backend.spawn', `Iniciando el backend de Janitor (${backend.label})`"
    ],
    ['message: `Hermes backend failed to start: ${error.message}`,', 'message: `El backend de Janitor no pudo iniciarse: ${error.message}`,'],
    ["'Waiting for Hermes backend to launch'", "'Esperando a que arranque el backend de Janitor'"],
    ["'Waiting for Hermes backend to become ready'", "'Esperando a que el backend de Janitor esté listo'"],
    [
      "message: 'Hermes backend is ready. Finalizing desktop startup',",
      "message: 'El backend de Janitor está listo. Terminando de iniciar la app',"
    ],
    ['message: `Desktop boot failed: ${message}`,', 'message: `Falló el inicio de la app: ${message}`,'],
    // The managed-runtime label is interpolated into the spawn message above.
    ['label: `Hermes at ${ACTIVE_HERMES_ROOT}`,', 'label: `Janitor en ${ACTIVE_HERMES_ROOT}`,'],
    // — renderer crash recovery page —
    ["title: 'Hermes desktop UI was terminated',", "title: 'La interfaz de Janitor se cerró inesperadamente',"],
    [
      '`The desktop UI process was terminated unexpectedly (reason: ${reason}${exit}). ` +',
      '`El proceso de la interfaz se cerró inesperadamente (motivo: ${reason}${exit}). ` +'
    ],
    [
      "'Your sessions and the background gateway are unaffected — reload to continue.',",
      "'Tus sesiones y el gateway en segundo plano no se vieron afectados; recarga para continuar.',"
    ],
    ['`, exit code ${String(details.exitCode)}`', '`, código de salida ${String(details.exitCode)}`'],
    // — open-in-terminal result shown to the user —
    ["error: 'Hermes is not installed yet' }", "error: 'Janitor aún no está instalado' }"]
  ],

  'electron/quit-guard.ts': [
    ["buttons: backendOwned ? ['Keep Running', 'Quit Anyway'] : ['Cancel', 'Quit'],", "buttons: backendOwned ? ['Seguir ejecutando', 'Salir de todos modos'] : ['Cancelar', 'Salir'],"],
    ["remaining === 1 ? '• 1 more' : `• ${remaining} more`", "remaining === 1 ? '• 1 más' : `• ${remaining} más`"],
    [
      "'Quitting stops the agent mid-turn. Any work it has not finished writing is lost.'",
      "'Salir detiene al agente a mitad de turno. Se pierde todo lo que aún no haya terminado de escribir.'"
    ],
    [
      "'The agent keeps running on the remote backend. Quitting only closes Hermes on this computer; reconnect later to see the results.'",
      "'El agente sigue ejecutándose en el backend remoto. Salir solo cierra Janitor en este equipo; vuelve a conectarte más tarde para ver los resultados.'"
    ],
    [
      "work.count === 1 ? 'Hermes is still working on 1 chat.' : `Hermes is still working on ${work.count} chats.`",
      "work.count === 1 ? 'Janitor sigue trabajando en 1 chat.' : `Janitor sigue trabajando en ${work.count} chats.`"
    ]
  ],

  'electron/minimize-to-tray.ts': [
    ["tray.setToolTip('Hermes')", "tray.setToolTip('Janitor')"],
    ["{ label: 'Show Hermes', click: restore }", "{ label: 'Mostrar Janitor', click: restore }"],
    ["{ label: 'Quit Hermes', click: () => app.quit() }", "{ label: 'Salir de Janitor', click: () => app.quit() }"]
  ],

  'electron/plugin-compat-notice.ts': [
    ["title: 'Some plugins were turned off',", "title: 'Se desactivaron algunos plugins',"],
    [
      'message: `These plugins were built for an older Hermes and were turned off: ${nameList}. Hermes works normally without them.`,',
      'message: `Estos plugins se crearon para una versión anterior de Janitor y se desactivaron: ${nameList}. Janitor funciona con normalidad sin ellos.`,'
    ],
    [
      'detail: `Look for an updated version of each plugin or ask its author.\\n\\n${list}`',
      'detail: `Busca una versión actualizada de cada plugin o consulta a su autor.\\n\\n${list}`'
    ],
    ["title: 'Some plugins need an update',", "title: 'Algunos plugins necesitan una actualización',"],
    [
      'message: `These plugins were built for an older Hermes and will stop working on ${report.removal_date}: ${nameList}.`,',
      'message: `Estos plugins se crearon para una versión anterior de Janitor y dejarán de funcionar el ${report.removal_date}: ${nameList}.`,'
    ],
    [
      "detail: `Look for an updated version or ask the plugin's author before then.\\n\\n${list}`",
      'detail: `Busca una versión actualizada o consulta al autor del plugin antes de esa fecha.\\n\\n${list}`'
    ]
  ],

  'electron/bootstrap-failure-copy.ts': [
    ["['uv', 'Package installer']", "['uv', 'Instalador de paquetes']"],
    ["['system-packages', 'System packages']", "['system-packages', 'Paquetes del sistema']"],
    ["['repository', 'Hermes source code']", "['repository', 'Código fuente de Janitor']"],
    ["['python', 'Python runtime']", "['python', 'Entorno de ejecución de Python']"],
    ["['venv', 'Python environment']", "['venv', 'Entorno de Python']"],
    ["['dependencies', 'Python packages']", "['dependencies', 'Paquetes de Python']"],
    ["['node-deps', 'Browser tool packages']", "['node-deps', 'Paquetes de la herramienta de navegador']"],
    ["['desktop', 'Desktop app build']", "['desktop', 'Compilación de la app de escritorio']"],
    ["['platform-sdks', 'Platform tools']", "['platform-sdks', 'Herramientas de la plataforma']"],
    ["['configure', 'Settings']", "['configure', 'Configuración']"],
    ["['config-templates', 'Settings templates']", "['config-templates', 'Plantillas de configuración']"],
    ["['path', 'Hermes command']", "['path', 'Comando janitor']"],
    ["['gateway', 'Hermes service']", "['gateway', 'Servicio de Janitor']"],
    ["['bootstrap-marker', 'Finishing touches']", "['bootstrap-marker', 'Últimos ajustes']"],
    ["['prerequisites', 'System prerequisites']", "['prerequisites', 'Requisitos del sistema']"],
    ["['python-deps', 'Python packages']", "['python-deps', 'Paquetes de Python']"],
    ["['config', 'Settings']", "['config', 'Configuración']"],
    ["['setup', 'Settings']", "['setup', 'Configuración']"],
    ["['complete', 'Finishing touches']", "['complete', 'Últimos ajustes']"],
    [
      "'Common causes: no internet connection, antivirus blocking the installer, or another copy of Hermes running. ' +",
      "'Causas comunes: no hay conexión a internet, un antivirus bloquea el instalador u otra copia de Janitor está en ejecución. ' +"
    ],
    [
      "'Close other Hermes windows and choose Reload and retry; if it fails again, open the logs and send them to support.'",
      "'Cierra las demás ventanas de Janitor y elige Recargar y reintentar; si vuelve a fallar, abre los registros y envíalos al soporte.'"
    ],
    ["? `Setting up Hermes stopped during the '${label}' step.`", '? `La instalación de Janitor se detuvo en el paso “${label}”.`'],
    [": 'Setting up Hermes stopped before it could finish.'", ": 'La instalación de Janitor se detuvo antes de terminar.'"],
    [": 'unknown error'", ": 'error desconocido'"],
    [
      '"Part of Hermes\' installation is missing (it may have been deleted or quarantined by antivirus). " +',
      "'Falta parte de la instalación de Janitor (puede que se haya borrado o que un antivirus la haya puesto en cuarentena). ' +"
    ],
    [
      "'Choose Repair install below to put it back — your chats and settings are not affected. ' +",
      "'Elige Reparar instalación abajo para restaurarla; tus chats y ajustes no se ven afectados. ' +"
    ]
  ],

  'electron/renderer-load-error-page.ts': [
    ['<button id="reload" type="button">Reload</button>', '<button id="reload" type="button">Recargar</button>'],
    [
      '`<p>The renderer bundle is missing ${missingAssets!.length} module file(s) ` +',
      '`<p>A la interfaz le faltan ${missingAssets!.length} archivo(s) de módulo ` +'
    ],
    [
      '`(first ${assets.length} shown) — the last update replaced the app while ` +',
      '`(se muestran los primeros ${assets.length}): la última actualización reemplazó la app mientras ` +'
    ],
    ['`its files were locked.</p><ul>${items}</ul>`', '`sus archivos estaban bloqueados.</p><ul>${items}</ul>`'],
    ["'Hermes couldn\\u2019t start the desktop UI'", "'Janitor no pudo iniciar la interfaz'"],
    ["'The desktop renderer failed to load.'", "'No se pudo cargar la interfaz de escritorio.'"],
    [
      '`<p>Repair with: <code>hermes desktop --force-build</code></p>`',
      '`<p>Repárala con: <code>janitor desktop --force-build</code></p>`'
    ],
    ['<html lang="en">', '<html lang="es">'],
    [
      '<p>If this keeps happening, check <code>logs/desktop.log</code> and try\n  <code>hermes desktop --force-build</code>, then restart the app.</p>',
      '<p>Si sigue ocurriendo, revisa <code>logs/desktop.log</code> y prueba\n  <code>janitor desktop --force-build</code>; luego reinicia la app.</p>'
    ]
  ],

  'electron/notification-ipc.ts': [["title: payload?.title || 'Hermes',", "title: payload?.title || 'Janitor',"]],

  'electron/notification-linux.ts': [
    // D-Bus Notify app_name: the name the notification daemon shows.
    ["body: [\n                'Hermes',", "body: [\n                'Janitor',"],
    ["['default', 'View',", "['default', 'Ver',"]
  ],

  'electron/update-marker.ts': [
    [
      'message: `An update is already running (PID ${owner.pid}, started ${elapsed} ago). Wait for it to finish, then try again.`',
      'message: `Ya hay una actualización en curso (PID ${owner.pid}, iniciada hace ${elapsed}). Espera a que termine y vuelve a intentarlo.`'
    ]
  ],

  // ---- P8: renderer chrome that bypasses i18n ----

  'src/components/chat/intro.tsx': [["const WORDMARK = 'HERMES AGENT'", "const WORDMARK = 'JANITOR'"]],
  'src/components/pane-shell/tree/renderer/tree-group.tsx': [['cursor prefix={1} text="HERMES" />', 'cursor prefix={1} text="JANITOR" />']],
  'src/app/contrib/context.tsx': [['cursor prefix={1} text="HERMES" />', 'cursor prefix={1} text="JANITOR" />']],
  // «Obtener el instalador» / «Abrir la página de descarga»: the Janitor app is downloaded from the
  // fork's releases, never from upstream's site (which installs Hermes).
  'src/app/updates-overlay.tsx': [["const INSTALLER_URL = 'https://hermes-agent.nousresearch.com/'", "const INSTALLER_URL = 'https://github.com/reck74/Janitor-Agent/releases/latest'"]],
  'src/app/settings/about-settings.tsx': [["const RELEASE_NOTES_URL = 'https://github.com/NousResearch/hermes-agent/releases'", "const RELEASE_NOTES_URL = 'https://github.com/reck74/Janitor-Agent/releases'"], ["const INSTALLER_URL = 'https://hermes-agent.nousresearch.com/'", "const INSTALLER_URL = 'https://github.com/reck74/Janitor-Agent/releases/latest'"]],
  'src/components/assistant-ui/thread/status.tsx': [["label={hint || 'Hermes is working'}", "label={hint || 'Janitor está trabajando'}"]],
  'src/components/assistant-ui/thread/message-reactions.tsx': [['title="Reacted by Hermes"', 'title="Reacción de Janitor"']],
  'src/main.tsx': [["document.title = 'Hermes HUD'", "document.title = 'Janitor HUD'"]],
  'src/components/intro-reveal/intro-root.tsx': [["document.title = 'Hermes'", "document.title = 'Janitor'"]],
  'src/components/onboarding-chat/setup-profile.ts': [
    // Title of the welcome chat (stored as the session title).
    ["export const SETUP_CHAT_TITLE = 'Welcome to Hermes'", "export const SETUP_CHAT_TITLE = 'Bienvenido a Janitor'"],
    // Model-facing prompts: the agent must not call itself Hermes.
    ['`You are Hermes. The user', '`You are Janitor. The user'],
    ['a piece of the Hermes app itself', 'a piece of the Janitor app itself'],
    ['never touch the Hermes install itself', 'never touch the Janitor install itself']
  ],
  // F1-08/F1-10: English renderer literals seen on a fresh install.
  'src/lib/model-status-label.ts': [
    // Provider titles in the first-run picker and the model pill.
    ["  anthropic: 'Anthropic API Key',", "  anthropic: 'Anthropic (clave API)',"],
    [
      "  'claude-code': 'Anthropic OAuth: Required Extra Usage Credits to Use Subscription',",
      "  'claude-code': 'Anthropic OAuth: requiere créditos de uso adicional para usar la suscripción',"
    ],
    ["  'openai-codex': 'ChatGPT or Codex Subscription',", "  'openai-codex': 'Suscripción de ChatGPT o Codex',"]
  ],
  // Settings section without a catalog key (t.settings.sections.browser is
  // absent, so the English fallback label renders).
  'src/app/settings/constants.ts': [["    label: 'Browser',", "    label: 'Navegador',"]],
  // Composer "+" button label.
  'src/app/chat/index.tsx': [["        label: 'Add context',", "        label: 'Añadir contexto',"]],
  // Boot overlay decode word ("CONE" stays legible via prefix={4}).
  'src/components/gateway-connecting-overlay.tsx': [["const TEXT = 'CONNECTING'", "const TEXT = 'CONECTANDO'"]],
  // Capabilities ▸ Plugins descriptions of the bundled plugins.
  'src/plugins/kanban/plugin.tsx': [
    [
      "  description: 'Multi-agent task board — board page, sidebar entry, and a live in-flight count in the status bar.',",
      "  description: 'Tablero de tareas multiagente: página del tablero, entrada en la barra lateral y recuento en vivo en la barra de estado.',"
    ]
  ],
  'src/plugins/radio/plugin.js': [
    [
      "  description: 'Free live radio with pinned stations, search, and an audio-reactive waveform.',",
      "  description: 'Radio en vivo gratuita con emisoras fijadas, búsqueda y una onda que reacciona al audio.',"
    ]
  ],
  'src/plugins/hermes-bots/plugin.tsx': [
    [
      "    'Bot Mode — a one-chat-per-agent roster with avatars, routines, group chats, and bot-to-bot messaging. Ships with the app; disable here if unwanted.',",
      "    'Modo Bot: una lista con un chat por agente, avatares, rutinas, chats de grupo y mensajes entre bots. Viene con la app; desactívalo aquí si no lo quieres.',"
    ]
  ],
  'src/store/onboarding-script.ts': [
    // Onboarding runbook/persona sent to the model.
    ['that Hermes installs and runs locally', 'that Janitor installs and runs locally', 2],
    ['"You are Hermes, and this is a brand-new user', '"You are Janitor, and this is a brand-new user'],
    ['you are Hermes, one thing, talking to them', 'you are Janitor, one thing, talking to them'],
    ['so Hermes can connect to them later', 'so Janitor can connect to them later'],
    ['Hermes can build pieces of its own interface', 'Janitor can build pieces of its own interface'],
    ['a piece of the Hermes interface', 'a piece of the Janitor interface']
  ]
}

// Files with brand text that stay as they are, and why.
export const ALLOWLISTED_FILES = {
  'electron/portal-session.ts': 'Hermes Cloud / Nous Portal sign-in: third-party service names (plan 2.8).'
}

// Literals with "Hermes" that were reviewed and intentionally left.
export const KEPT_LITERALS = [
  ['electron/main.ts', "process.env.HERMES_DESKTOP_APP_NAME", 'env var name (core, directive #1)'],
  ['electron/main.ts', "label: `Hermes source at ${...}`", 'dev-checkout backend label, logs only'],
  ['electron/main.ts', "label: `existing Hermes CLI at ${hermesCommand}`", 'PATH adoption is disabled by P3 (only HERMES_DESKTOP_HERMES reaches it)'],
  ['electron/main.ts', "label: 'Hermes Agent not installed yet; bootstrap required'", 'sentinel label, logs only'],
  ['electron/main.ts', "label: `Hermes backend for profile \"${profile}\"`", 'pool backend label, logs only'],
  ['electron/main.ts', "app.setAppUserModelId('com.nousresearch.hermes')", 'Windows-only AUMID; Windows is out of scope for phase 1'],
  ['electron/terminal-ipc.ts', "env.TERM_PROGRAM = 'Hermes'", 'environment value read by shells, not shown'],
  ['electron/bootstrap-failure-copy.ts', 'Details:', 'parse marker split by src/components/desktop-install-overlay.tsx'],
  ['src/components/chat/intro.tsx', "headline: 'What should Hermes look at?'", 'headline copy is parsed but never rendered (only the wordmark and the i18n body are)']
]
