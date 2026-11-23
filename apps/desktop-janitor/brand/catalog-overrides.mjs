// Spanish catalog overrides (patch P10, task F1-10; directive #17).
//
// Set by key path in apps/desktop/src/i18n/es.ts at build time, BEFORE the P6
// brand rules (so the guard sees them too). Each entry pins the English text
// it translates:
//   - en.ts must still hold `en` at `path` — if upstream rewrites or removes
//     the English string, the build fails naming the path, so the Spanish is
//     reviewed instead of silently going stale;
//   - es.ts either lacks the key (upstream added it to en.ts only and the app
//     falls back to English) — it is inserted into its parent object — or holds
//     `from` (defaults to `en`: an untranslated copy) — it is replaced. Any
//     other current value means upstream translated or changed it: the build
//     fails so the override is dropped or revised.
//
// Values are plain strings. Terms follow es.ts (Configuración, Atajos de
// teclado, navegador integrado, dictado, Correo electrónico).

export const ES_OVERRIDES = [
  {
    path: 'keybinds.actions.composer.dictate',
    en: 'Start / stop dictation',
    es: 'Iniciar / detener dictado'
  },
  {
    path: 'settings.config.alwaysExternalLinksTitle',
    en: 'Always open links in external browser',
    es: 'Abrir siempre los enlaces en el navegador externo'
  },
  {
    path: 'settings.config.alwaysExternalLinksDesc',
    en: 'Open every link you click in your system browser instead of the in-app browser. "Open in in-app browser" in the right-click menu still works.',
    es: 'Abre cada enlace en el navegador del sistema en lugar del navegador integrado. “Abrir en el navegador integrado” del menú contextual sigue funcionando.'
  },
  {
    path: 'settings.config.voiceShortcutHintTitle',
    en: 'Voice recording shortcut',
    es: 'Atajo de grabación de voz'
  },
  {
    path: 'settings.config.voiceShortcutHintDesc',
    en: 'Set the voice recording shortcut in Settings → Keyboard Shortcuts ("Start / stop dictation"). The voice.record_key config value only applies to the CLI and TUI.',
    es: 'Configura el atajo de grabación de voz en Configuración → Atajos de teclado (“Iniciar / detener dictado”). El valor voice.record_key de la configuración solo se aplica a la CLI y a la TUI.'
  },
  {
    path: 'cron.deliveryLabels.email',
    en: 'Email',
    es: 'Correo electrónico'
  },
  {
    path: 'settings.subpages.modelMoa',
    en: 'Mixture of Agents',
    es: 'Mezcla de agentes (MoA)'
  },
  {
    path: 'settings.model.moaTitle',
    en: 'Mixture of Agents',
    es: 'Mezcla de agentes (MoA)'
  },
  {
    // F1-08: no visible string may call Nous "the recommended way" to use
    // Janitor. The featured Nous row is gone (P9-featured-id); this keeps the
    // copy honest if anything still renders it.
    path: 'onboarding.featuredPitch',
    en: 'One subscription, 300+ frontier models — the recommended way to run Hermes',
    from: 'Una suscripción, más de 300 modelos frontier: la forma recomendada de usar Hermes',
    es: 'Inicia sesión con una cuenta de Nous Portal para usar sus modelos.'
  },
  {
    // SSH mode looks for an upstream `hermes` executable on the remote and
    // runs it with the remote's ~/.hermes (electron/remote-lifecycle.ts,
    // locateHermes / buildSpawnCommand); the fork's installer only creates
    // `janitor`. New SSH connections are not offered (P9-ssh-mode-card); this
    // is what an existing SSH setup reads instead of "install Hermes from
    // hermes-agent.nousresearch.com".
    path: 'settings.gateway.sshErrNotInstalled',
    en: 'Hermes is not installed on the remote host. Install it there (curl -fsSL https://hermes-agent.nousresearch.com/install.sh | sh) or set the Hermes path.',
    from: 'Hermes no está instalado en el host remoto. Instálalo allí (curl -fsSL https://hermes-agent.nousresearch.com/install.sh | sh) o indica la ruta de Hermes.',
    es: 'La conexión por SSH no está soportada todavía en Janitor: no hay en el host remoto un motor que la app sepa arrancar. Usa la conexión local.'
  }
]

// es.ts leaves whose value is legitimately identical to en.ts after the brand
// rules. Anything else identical to English (or missing from es.ts) fails the
// "Spanish everywhere" test with its key path. An entry that stops being
// identical also fails, so the list never rots.
export const IDENTICAL_TO_ENGLISH = [
  {
    reason: 'Same word in Spanish',
    paths: [
      'common.error',
      'connectorsPage.card.state.serverError',
      'settings.mcp.statusError',
      'messaging.states.fatal',
      'install.error',
      'assistant.tool.statusError',
      'settings.subpages.appearanceGeneral',
      'settings.billing.summary.plan',
      'settings.billing.sections.plan',
      'profiles.colorFor',
      'sidebar.filter.manual',
      'shell.approvalMode.manual',
      'sidebar.terminal',
      'rightSidebar.terminal',
      'shell.statusbar.toggleTerminal',
      'sidebar.projects.ideaLabel',
      'settings.connections.kindLocal',
      'modelPicker.localDownloadsHeading',
      'interfaceMode.simple.label',
      'settings.uninstallSection.appLabel'
    ]
  },
  {
    reason: 'Term es.ts deliberately keeps in English (used the same way in its own prose)',
    paths: [
      'sidebar.filter.pullRequest', // es.ts prose: "abre un pull request"
      'common.docs', // es.ts: "Abrir docs", "Docs de ${provider}"
      'settings.envActions.docs',
      'statusStack.coding.worktrees', // es.ts: "Nuevo worktree"
      'settings.mcp.capabilitySummary[1][0]', // es.ts: "${prompts} prompts"
      'webhooks.fieldPrompt',
      'cron.promptLabel',
      'statusStack.control.loopPromptLabel',
      'skills.tabSkills',
      'webhooks.fieldSkills',
      'profiles.skillsLabel',
      'profiles.skills~3',
      'profiles.skills~2',
      'shell.statusbar.contextUsagePanel.categories.skills',
      'assistant.catalogInstall.skill',
      'assistant.catalogInstall.kind.skill',
      'skills.tabPlugins',
      'assistant.catalogInstall.kind.plugin',
      'connectorsPage.card.kindPlugin',
      'common.bots',
      'commandCenter.sharedGatewayRestarted~2',
      'commandCenter.sharedGatewayRestarted~3',
      'shell.gatewayMenu.gateway',
      'shell.statusbar.gateway',
      'shell.statusbar.backendLabel',
      'shell.statusbar.commit',
      'assistant.catalogInstall.commitLabel',
      'sidebar.filter.tokens',
      'agents.tokens',
      'artifacts.chat',
      'settings.sections.chat',
      'sidebar.row.untitledChat',
      'profiles.env',
      'assistant.tool.prefixes.web'
    ]
  },
  {
    reason: 'Acronyms and protocol names',
    paths: [
      'connectorsPage.add.typeStdio',
      'connectorsPage.add.url',
      'connectorsPage.add.authOauth',
      'settings.nav.mcp',
      'settings.model.tasks.mcp.label',
      'shell.statusbar.contextUsagePanel.categories.mcp',
      'settings.connections.kindSsh',
      'shell.statusbar.connectionSsh',
      'shell.statusbar.connectionSshTooltip',
      'artifacts.colLocationLink',
      'composer.url',
      'settings.vault.cvcField',
      'shell.statusbar.systemResources.ram',
      'updates.pidLabel',
      'shell.statusbar.cron',
      'shell.statusbar.webhooks',
      'desktop.yoloTitle',
      'settings.gateway.sshHostTitle',
      'settings.gateway.sshHostPickTitle'
    ]
  },
  {
    reason: 'Product, service or model names',
    paths: [
      'sendDiagnostics.links.discord',
      'webhooks.deliverOptions.telegram',
      'webhooks.deliverOptions.discord',
      'webhooks.deliverOptions.slack',
      'cron.deliveryLabels.telegram',
      'cron.deliveryLabels.discord',
      'cron.deliveryLabels.slack',
      'skills.provenance.hub',
      'skills.hub.pickerTitle',
      'composer.voiceEngineLiveShort',
      'freeTier.providerName',
      'freeTier.statusLabel',
      'onboarding.pro',
      'modelPicker.pro',
      'shell.modelOptions.ultra',
      // Third-party service, allowlisted by the brand rules (plan 2.8); its
      // entry points are hidden by P9-cloud-*.
      'settings.connections.kindCloud',
      'settings.gateway.cloudTitle',
      'settings.gateway.cloudSignInTitle',
      'shell.statusbar.connectionCloudTooltip'
    ]
  },
  {
    reason: 'Placeholders and example values (hostnames, ids, URLs)',
    paths: [
      'settings.vault.originPlaceholder',
      'settings.appearance.installPlaceholder',
      'settings.customEndpoints.namePlaceholder',
      'settings.connections.labelPlaceholder',
      'messaging.fieldCopy.MATTERMOST_URL.placeholder',
      'messaging.fieldCopy.MATRIX_HOMESERVER.placeholder',
      'messaging.fieldCopy.MATRIX_USER_ID.placeholder',
      'messaging.fieldCopy.SIGNAL_HTTP_URL.placeholder',
      'profiles.remoteOverride.urlPlaceholder',
      'composer.urlPlaceholder',
      'install.remoteUrlPlaceholder'
    ]
  },
  {
    reason: '"Auto" is the Spanish UI word too',
    paths: [
      'settings.appearance.tabStripAuto',
      'settings.appearance.textDirection.auto',
      'settings.customEndpoints.contextPlaceholder',
      'profiles.autoColor'
    ]
  }
]

export const IDENTICAL_PATHS = new Set(IDENTICAL_TO_ENGLISH.flatMap(group => group.paths))
