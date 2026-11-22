// F1-08 first-run patches (P9): behaviour of the patched sources, evaluated in
// memory against the current apps/desktop. Read-only on apps/desktop.

import assert from 'node:assert/strict'
import module from 'node:module'
import { test } from 'node:test'
import vm from 'node:vm'

import { FIRST_RUN_PATCHES, MINIMAX_PITCH, MISSING_KEY_NOTICE, MISSING_KEY_PATTERN } from '../brand/first-run.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'
import { evaluateLiteral, objectLiteralAfter } from './plugin-locales.mjs'
import { classifyLiterals, literalText } from './ts-literals.mjs'

const patched = computePatchedFiles(APP_DIR, allPatches())
const text = file => {
  assert.ok(patched.has(file), `${file} is not patched`)

  return patched.get(file).toString('utf8')
}

/** Evaluate an ESM .ts module with no imports; returns its exports. */
function loadModule(source) {
  const js = module.stripTypeScriptTypes(source).replace(/^export (?=(?:const|function) )/gm, '')
  const names = [...source.matchAll(/^export (?:const|function) (\w+)/gm)].map(m => m[1])

  return vm.runInNewContext(`${js}\n;({ ${names.join(', ')} })`)
}

test('P9 patches are exact literals and never write "Hermes"', () => {
  for (const patch of FIRST_RUN_PATCHES) {
    assert.equal(typeof patch.find, 'string', patch.id)
    assert.ok(patch.id.startsWith('P9-'), patch.id)
    assert.doesNotMatch(patch.replace, /Hermes/, patch.id)
  }
})

test('guest onboarding (Nous free tier) never turns on, whatever env or argv say', () => {
  const guest = loadModule(text('electron/guest-onboarding.ts'))

  assert.equal(guest.guestOnboardingEnabled(['electron', '--guest-onboarding'], { HERMES_GUEST_ONBOARDING: '1' }), false)
  assert.equal(guest.guestOnboardingEnabled([], {}), false)
  // Backends are still stamped explicitly off, so an inherited '1' cannot leak.
  assert.equal(guest.desktopBackendSpawnEnv({ HERMES_GUEST_ONBOARDING: '1' }, false).HERMES_GUEST_ONBOARDING, '0')
  // The intro film / guided chat skip flag is untouched.
  assert.equal(guest.skipIntroEnabled(['--skip-intro'], {}), true)
})

test('MiniMax is the first API-key option and the featured row opens its key form', () => {
  const source = text('src/components/onboarding/index.tsx')
  const options = evaluateLiteral(objectLiteralAfter(source, 'const API_KEY_OPTIONS: ApiKeyOption[] = '))

  assert.equal(options[0].envKey, 'MINIMAX_API_KEY')
  // saveOnboardingApiKey derives the backend slug from the env key.
  assert.equal(options[0].envKey.replace(/_API_KEY$/, '').toLowerCase(), 'minimax')
  assert.equal(new Set(options.map(o => o.envKey)).size, options.length)

  const picker = source.slice(source.indexOf('export function Picker('))
  const minimaxRow = picker.indexOf("onClick={() => openKeyForm('MINIMAX_API_KEY')}")

  assert.ok(minimaxRow > 0, 'featured MiniMax row missing')
  assert.ok(minimaxRow < picker.indexOf('{showRest ? ('), 'MiniMax must come before the other providers')
  assert.doesNotMatch(picker, /<FeaturedProviderRow /)
  assert.match(source, /export const FEATURED_ID = 'minimax'/)
})

test('honest MiniMax copy, and Nous is no longer promoted anywhere in the picker or catalog', () => {
  assert.match(MINIMAX_PITCH, /clave API/)
  assert.doesNotMatch(MINIMAX_PITCH, /suscripci|300|gratis/i)

  const order = evaluateLiteral(objectLiteralAfter(text('src/components/onboarding/providers.tsx'), 'const PROVIDER_ORDER: Record<string, number> = '))

  assert.equal(order['minimax-oauth'], Math.min(...Object.values(order)))
  assert.equal(order.nous, Math.max(...Object.values(order)))

  // No Spanish value may call Nous the recommended way to use the app.
  const es = text('src/i18n/es.ts')

  for (const literal of classifyLiterals(es).values) {
    const value = literalText(es, literal)

    assert.doesNotMatch(value, /forma recomendada/i, `${literal.path} = ${value}`)
  }
})

test('the raw "No usable credentials" backend error becomes a Spanish prompt', () => {
  const pattern = vm.runInNewContext(MISSING_KEY_PATTERN)

  // Both backend forms (hermes_cli/runtime_provider.py, tui_gateway/methods_config.py).
  assert.ok(pattern.test("No usable credentials found for provider 'minimax'. Set MINIMAX_API_KEY."))
  assert.ok(pattern.test('No usable credentials found for minimax.'))
  assert.ok(!pattern.test('Connection refused'))
  assert.ok(text('src/components/onboarding/index.tsx').includes(`? '${MISSING_KEY_NOTICE}'`))
})

test('Hermes Cloud is not offered for a new connection; local, remote and SSH still are', () => {
  const kinds = text('src/app/settings/connections-registry.tsx').match(/\(\[('local'[^\]]*)\] as const\)/)[1]

  assert.deepEqual(kinds.split(',').map(s => s.trim().replace(/'/g, '')), ['local', 'remote', 'ssh'])

  const gateway = text('src/app/settings/gateway-settings.tsx')
  const cards = [...gateway.matchAll(/<ModeCard\s+active=\{state\.mode === '(\w+)'\}/g)].map(m => m[1])

  assert.deepEqual(cards, ['local', 'cloud', 'remote', 'ssh'])
  assert.match(gateway, /\{state\.mode === 'cloud' \? \(\s*<ModeCard\s+active=\{state\.mode === 'cloud'\}/)
  // The cloud panel and the saved-connection logic stay intact for existing setups.
  assert.match(gateway, /\{state\.mode === 'cloud' && !state\.envOverride \? \(/)
})

test('no surface offers to upload diagnostics to Nous', () => {
  for (const file of ['src/components/error-boundary.tsx', 'src/components/assistant-ui/thread/assistant-message.tsx']) {
    assert.doesNotMatch(text(file), /requestSendDiagnostics/, file)
  }

  // Copy diagnostics and Open logs remain on the failed-turn card.
  assert.match(text('src/components/assistant-ui/thread/assistant-message.tsx'), /copy\.errorCopyDiagnostics/)
})

test('the Nous billing entry only appears with a Nous account behind it', () => {
  const settings = text('src/app/settings/index.tsx')

  assert.match(settings, /const janitorShowBilling = billingPresentation\.status === 'normal' \|\| billingPresentation\.status === 'free_tier'/)
  assert.match(settings, /\.\.\.\(janitorShowBilling\s+\?\s+\[\s+\{\s+active: activeView === 'billing'/)
  assert.match(settings, /\n\s+janitorShowBilling,\n\s+keysView,/)
})
