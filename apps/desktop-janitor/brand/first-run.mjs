// First-run patches P9 (task F1-08, plan 2.2 and 4.4; directive #17).
//
// MiniMax is the recommended, preconfigured provider (not mandatory); the Nous
// free tier and Nous account flows are hidden; "Hermes Cloud" (Nous's hosted
// backend) is not offered on a fresh install; Janitor users are not invited to
// upload diagnostics to Nous. Same contract as brand/patches.mjs: exact anchor,
// exact count, a miss fails the build naming the patch id.
//
// Upstream first-run flow these patches act on (guest onboarding off):
//   boot overlay (install / "Preparing") → DesktopOnboardingOverlay
//   (components/onboarding/index.tsx) → Picker: featured provider row (Nous),
//   optional local-models row, "Other providers" disclosure (Fireworks, the
//   OAuth providers sorted by providers.tsx PROVIDER_ORDER, OpenRouter),
//   "choose later" and "I have an API key" (ApiKeyForm, curated
//   API_KEY_OPTIONS first) → model confirm → app.
// The intro film and the guided onboarding chat (components/onboarding-chat/,
// store/onboarding-script.ts) only run with guest onboarding on, which
// P9-no-guest-onboarding makes impossible.

// Honest copy: MiniMax needs the user's own key; no subscription, no model count.
export const MINIMAX_PITCH = 'Proveedor recomendado para Janitor. Necesita tu propia clave API de MiniMax.'
// Matches both backend forms: hermes_cli/runtime_provider.py ("…for provider
// 'minimax'. Set MINIMAX_API_KEY…") and tui_gateway/methods_config.py ("…for minimax.").
export const MISSING_KEY_PATTERN = '/No usable credentials found for /i'
export const MISSING_KEY_NOTICE =
  'El proveedor configurado todavía no tiene clave API. Pega tu clave de MiniMax (recomendado) o elige otro proveedor.'

export const FIRST_RUN_PATCHES = [
  // ---- MiniMax first -------------------------------------------------------
  {
    id: 'P9-minimax-key-option',
    purpose: 'MiniMax heads the curated API-key options, so the key form can preselect MINIMAX_API_KEY (slug candidates → "minimax")',
    file: 'src/components/onboarding/index.tsx',
    find: "const API_KEY_OPTIONS: ApiKeyOption[] = [\n  {\n    id: 'fireworks',",
    replace:
      "const API_KEY_OPTIONS: ApiKeyOption[] = [\n" +
      '  // Janitor build: MiniMax is the recommended provider (plan 2.2).\n' +
      '  {\n' +
      "    id: 'minimax',\n" +
      "    name: 'MiniMax',\n" +
      "    envKey: 'MINIMAX_API_KEY',\n" +
      "    docsUrl: 'https://www.minimax.io/',\n" +
      "    short: 'recomendado para Janitor',\n" +
      `    description: '${MINIMAX_PITCH}'\n` +
      '  },\n' +
      '  {\n' +
      "    id: 'fireworks',",
    count: 1
  },
  {
    id: 'P9-local-endpoint-name',
    purpose: 'Key-form option label (renderer literal, not in the catalog)',
    file: 'src/components/onboarding/index.tsx',
    find: "    name: 'Local / custom endpoint',",
    replace: "    name: 'Endpoint local o personalizado',",
    count: 1
  },
  {
    id: 'P9-derived-key-description',
    purpose: 'Generic description of backend-listed API-key providers (renderer template, not in the catalog)',
    file: 'src/components/onboarding/index.tsx',
    find: 'description: `Direct API access to ${row.name}.`,',
    replace: 'description: `Acceso directo a la API de ${row.name}.`,',
    count: 1
  },
  {
    id: 'P9-missing-key-notice',
    purpose:
      "First-run notice: the backend's raw English \"No usable credentials found for provider 'x'…\" becomes a plain Spanish prompt",
    file: 'src/components/onboarding/index.tsx',
    find: '          {reason ? <ReasonNotice reason={reason} /> : null}\n',
    replace:
      '          {reason ? (\n' +
      '            <ReasonNotice\n' +
      '              reason={\n' +
      '                // Janitor build: a missing key is the normal first-run state, not an error to quote.\n' +
      `                ${MISSING_KEY_PATTERN}.test(reason)\n` +
      `                  ? '${MISSING_KEY_NOTICE}'\n` +
      '                  : reason\n' +
      '              }\n' +
      '            />\n' +
      '          ) : null}\n',
    count: 1
  },
  {
    id: 'P9-featured-id',
    purpose: 'No OAuth provider is featured any more (Nous was): onboarding and Settings → Providers stop promoting Nous',
    file: 'src/components/onboarding/index.tsx',
    find: "export const FEATURED_ID = 'nous'",
    // `minimax` is the API-key slug; the OAuth list only knows `minimax-oauth`,
    // so nothing in it matches and Nous falls into the ordinary list.
    replace: "export const FEATURED_ID = 'minimax'",
    count: 1
  },
  {
    id: 'P9-featured-row',
    purpose: 'The featured row of the first-run picker is MiniMax: it opens the API-key form on MINIMAX_API_KEY',
    file: 'src/components/onboarding/index.tsx',
    find: '        {featured ? <FeaturedProviderRow onSelect={select} provider={featured} /> : null}\n',
    replace:
      '        {/* Janitor build: MiniMax is the recommended provider (plan 2.2). */}\n' +
      '        <button\n' +
      '          className="group relative flex w-full items-center justify-between gap-4 rounded-[8px] bg-primary/[0.06] px-3 py-2.5 text-left transition-colors hover:bg-primary/10"\n' +
      "          onClick={() => openKeyForm('MINIMAX_API_KEY')}\n" +
      '          type="button"\n' +
      '        >\n' +
      // Theme tokens, not .arc-nous (hardcoded blue → orange): the arc follows the active theme (F1-13).
      '          <span aria-hidden className="arc-border arc-reverse [--arc-c1:var(--dt-primary)]! [--arc-c2:color-mix(in_srgb,var(--arc-c1)_45%,transparent)]!" />\n' +
      '          <div className="min-w-0">\n' +
      '            <div className="flex items-center gap-2">\n' +
      '              <span className="text-[length:var(--conversation-text-font-size)] font-semibold">MiniMax</span>\n' +
      '              <span className="inline-flex items-center gap-1.5 bg-primary px-2 py-0.5 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-primary-foreground">\n' +
      '                <span aria-hidden="true" className="dither inline-block size-2 shrink-0" />\n' +
      '                {t.onboarding.recommended}\n' +
      '              </span>\n' +
      '            </div>\n' +
      `            <p className="mt-1 text-xs leading-5 text-muted-foreground">${MINIMAX_PITCH}</p>\n` +
      '          </div>\n' +
      '          <KeyRound className="size-4 shrink-0 text-primary transition group-hover:translate-x-0.5" />\n' +
      '        </button>\n',
    count: 1
  },
  {
    id: 'P9-picker-collapsible',
    purpose: 'Keep the "Other providers" disclosure: MiniMax anchors the choice, everything else (Nous included) sits behind it',
    file: 'src/components/onboarding/index.tsx',
    find: '  const collapsible = Boolean(featured)\n',
    replace: '  const collapsible = true // Janitor build: the MiniMax row anchors the choice\n',
    count: 1
  },
  {
    id: 'P9-provider-order',
    purpose: 'OAuth provider order: MiniMax first, Nous last among the curated ones',
    file: 'src/components/onboarding/providers.tsx',
    find: "  nous: 0,\n  'openai-codex': 1,\n  'minimax-oauth': 2,",
    replace: "  'minimax-oauth': 0,\n  'openai-codex': 1,\n  nous: 98, // Janitor build: Nous is not promoted (plan 2.2)",
    count: 1
  },

  // ---- Nous free tier off --------------------------------------------------
  {
    id: 'P9-no-guest-onboarding',
    purpose: 'HERMES_GUEST_ONBOARDING=1 / --guest-onboarding are ignored: the Nous free tier, intro film and guided chat never turn on',
    file: 'electron/guest-onboarding.ts',
    find: "  return env[GUEST_ONBOARDING_ENV] === '1' || argv.includes(GUEST_ONBOARDING_FLAG)\n",
    replace:
      '  // Janitor build: the Nous free tier never turns on (plan 2.2), whatever env or argv say.\n' +
      '  void argv\n' +
      '  void env\n' +
      '\n' +
      '  return false\n',
    count: 1
  },

  // ---- Hermes Cloud not offered --------------------------------------------
  {
    id: 'P9-cloud-mode-card',
    purpose: 'Gateway settings: the "Hermes Cloud" mode card only shows while a cloud connection is already active',
    file: 'src/app/settings/gateway-settings.tsx',
    find:
      '          <ModeCard\n' +
      "            active={state.mode === 'cloud'}\n" +
      '            description={g.cloudDesc}\n' +
      '            disabled={state.envOverride}\n' +
      '            icon={Cloud}\n' +
      "            onSelect={() => setState(current => ({ ...current, mode: 'cloud' }))}\n" +
      '            title={g.cloudTitle}\n' +
      '          />\n',
    replace:
      "          {/* Janitor build: Nous's hosted cloud is a third-party service; not offered (plan 4.4). */}\n" +
      "          {state.mode === 'cloud' ? (\n" +
      '            <ModeCard\n' +
      "              active={state.mode === 'cloud'}\n" +
      '              description={g.cloudDesc}\n' +
      '              disabled={state.envOverride}\n' +
      '              icon={Cloud}\n' +
      "              onSelect={() => setState(current => ({ ...current, mode: 'cloud' }))}\n" +
      '              title={g.cloudTitle}\n' +
      '            />\n' +
      '          ) : null}\n',
    count: 1
  },
  {
    id: 'P9-cloud-mode-grid',
    purpose: 'Gateway settings: the two offered mode cards (local, remote) fill the grid; Cloud/SSH only add a card when already active',
    file: 'src/app/settings/gateway-settings.tsx',
    find: '<div className="grid auto-rows-fr grid-cols-1 gap-2 sm:grid-cols-2 min-[72rem]:grid-cols-4">',
    replace: '<div className="grid auto-rows-fr grid-cols-1 gap-2 sm:grid-cols-2">',
    count: 1
  },
  {
    id: 'P9-cloud-connection-kind',
    purpose: 'Connections: a new connection is local or remote (no Cloud, no SSH); existing cloud/SSH entries still list and edit',
    file: 'src/app/settings/connections-registry.tsx',
    find: "(['local', 'cloud', 'remote', 'ssh'] as const)",
    replace: "(['local', 'remote'] as const)",
    count: 1
  },

  // ---- SSH mode not offered ------------------------------------------------
  // electron/remote-lifecycle.ts looks for a `hermes` executable on the remote
  // (`command -v hermes`, ~/.local/bin/hermes, /usr/local/bin/hermes,
  // ~/.hermes/hermes-agent/venv/bin/hermes), runs `env HERMES_DESKTOP=1 <hermes>
  // [--profile p] serve --isolated …` and keeps its lock, update marker and
  // profiles under the remote ${HERMES_HOME:-$HOME/.hermes}. The fork's
  // installer only creates `janitor` (~/.janitor). So against a Janitor host it
  // cannot start, and against an upstream install it would connect to Hermes,
  // not Janitor. Not verified with Janitor: not offered (settings.gateway.
  // sshErrNotInstalled says so for an existing SSH setup).
  {
    id: 'P9-ssh-mode-card',
    purpose: 'Gateway settings: the SSH mode card only shows while an SSH connection is already active',
    file: 'src/app/settings/gateway-settings.tsx',
    find:
      '          <ModeCard\n' +
      "            active={state.mode === 'ssh'}\n" +
      '            description={g.sshDesc}\n' +
      '            disabled={state.envOverride}\n' +
      '            hint={g.sshTrustHint}\n' +
      '            icon={Terminal}\n' +
      "            onSelect={() => setState(current => ({ ...current, mode: 'ssh' }))}\n" +
      '            title={g.sshTitle}\n' +
      '          />\n',
    replace:
      '          {/* Janitor build: SSH mode starts an upstream `hermes` on the remote; not supported yet. */}\n' +
      "          {state.mode === 'ssh' ? (\n" +
      '            <ModeCard\n' +
      "              active={state.mode === 'ssh'}\n" +
      '              description={g.sshDesc}\n' +
      '              disabled={state.envOverride}\n' +
      '              hint={g.sshTrustHint}\n' +
      '              icon={Terminal}\n' +
      "              onSelect={() => setState(current => ({ ...current, mode: 'ssh' }))}\n" +
      '              title={g.sshTitle}\n' +
      '            />\n' +
      '          ) : null}\n',
    count: 1
  },

  // ---- No diagnostics upload to Nous ---------------------------------------
  {
    id: 'P9-no-diagnostics-boundary',
    purpose: 'Crash screen: drop "Send diagnostics to Nous" (logs stay one click away)',
    file: 'src/components/error-boundary.tsx',
    find:
      '        <Button onClick={() => requestSendDiagnostics(error.stack || error.message)} variant="text">\n' +
      '          {t.errors.sendDiagnostics}\n' +
      '        </Button>\n',
    replace: '',
    count: 1
  },
  {
    id: 'P9-no-diagnostics-boundary-import',
    purpose: 'Unused after P9-no-diagnostics-boundary',
    file: 'src/components/error-boundary.tsx',
    find: "import { requestSendDiagnostics } from '@/store/send-diagnostics'\n",
    replace: '',
    count: 1
  },
  {
    id: 'P9-no-diagnostics-turn-error',
    purpose: 'Failed-turn card: drop "Send diagnostics" (Copy diagnostics and Open logs stay)',
    file: 'src/components/assistant-ui/thread/assistant-message.tsx',
    find:
      '      <button className="aui-error-action" onClick={() => requestSendDiagnostics(diagnosticsText())} type="button">\n' +
      '        <Upload className="size-3" />\n' +
      '        {copy.errorSendDiagnostics}\n' +
      '      </button>\n',
    replace: '',
    count: 1
  },
  {
    id: 'P9-no-diagnostics-turn-error-import',
    purpose: 'Unused after P9-no-diagnostics-turn-error',
    file: 'src/components/assistant-ui/thread/assistant-message.tsx',
    find: "import { requestSendDiagnostics } from '@/store/send-diagnostics'\n",
    replace: '',
    count: 1
  },
  {
    id: 'P9-no-diagnostics-turn-error-icon',
    purpose: 'Unused after P9-no-diagnostics-turn-error',
    file: 'src/components/assistant-ui/thread/assistant-message.tsx',
    find: '  Upload,\n',
    replace: '',
    count: 1
  },

  // ---- Nous billing only for a Nous account --------------------------------
  {
    id: 'P9-billing-flag',
    purpose: 'Settings: the Billing entry is shown only when a Nous account (or its free tier) is behind it',
    file: 'src/app/settings/index.tsx',
    find: "  const canViewPlans = billingPresentation.status === 'normal' && Boolean(billingPresentation.plan?.action)\n",
    replace:
      "  const canViewPlans = billingPresentation.status === 'normal' && Boolean(billingPresentation.plan?.action)\n" +
      '  // Janitor build: without a Nous sign-in the page is only a Nous sign-in pitch.\n' +
      "  const janitorShowBilling = billingPresentation.status === 'normal' || billingPresentation.status === 'free_tier'\n",
    count: 1
  },
  {
    id: 'P9-billing-nav-open',
    purpose: 'Settings: wrap the Billing nav entry in janitorShowBilling (opening half)',
    file: 'src/app/settings/index.tsx',
    find: "          {\n            active: activeView === 'billing',\n            children: [",
    replace: "          ...(janitorShowBilling\n            ? [\n          {\n            active: activeView === 'billing',\n            children: [",
    count: 1
  },
  {
    id: 'P9-billing-nav-close',
    purpose: 'Settings: wrap the Billing nav entry in janitorShowBilling (closing half)',
    file: 'src/app/settings/index.tsx',
    find: "            id: 'billing',\n            label: t.settings.nav.billing,\n            onSelect: () => setActiveView('billing')\n          },",
    replace:
      "            id: 'billing',\n            label: t.settings.nav.billing,\n            onSelect: () => setActiveView('billing')\n          }\n              ]\n            : []),",
    count: 1
  },
  {
    id: 'P9-billing-nav-deps',
    purpose: 'Settings: recompute the nav when the billing state resolves',
    file: 'src/app/settings/index.tsx',
    find: '      billingView,\n      canViewPlans,\n      keysView,',
    replace: '      billingView,\n      canViewPlans,\n      janitorShowBilling,\n      keysView,',
    count: 1
  }
]
