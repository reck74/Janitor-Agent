// F4-02: the Janitor desktop plugin (Servicios screen). The plugin ships as a
// runtime disk plugin seeded by janitor/desktop_plugin; it is not part of the
// build layer, but its pure logic is tested here so the desktop-overlay CI job
// (which runs build.test.mjs) covers it.
//
// The module is imported for real. Its imports resolve the way the app's
// runtime loader resolves them: only `@hermes/plugin-sdk`, `react` and
// `react/jsx-runtime` exist (stubbed here); any other specifier fails the load.

import assert from 'node:assert/strict'
import module from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PLUGIN_FILE = path.resolve(HERE, '..', '..', '..', 'janitor', 'desktop_plugin', 'assets', 'desktop-plugins', 'janitor', 'plugin.js')
const PLUGIN_URL = pathToFileURL(PLUGIN_FILE).href

const dataUrl = source => `data:text/javascript,${encodeURIComponent(source)}`

const STUBS = {
  '@hermes/plugin-sdk': dataUrl(`
    export const calls = { navigate: [], newChat: 0 }
    export const host = {
      navigate: p => calls.navigate.push(p),
      newChat: () => { calls.newChat += 1 },
      notify: () => {},
      composer: { getDraft: async () => null, setDraft: async () => true, insertText: async () => true, focus: () => {} }
    }
    export const ROUTES_AREA = 'routes'
    export const SIDEBAR_NAV_AREA = 'sidebar.nav'
    export const PALETTE_AREA = 'palette'
    export const Badge = () => null
    export const Button = () => null
    export const ErrorState = () => null
    export const useQuery = () => ({})
    export const useQueryClient = () => ({})
  `),
  react: dataUrl('export const useState = v => [v, () => {}]; export default {}'),
  'react/jsx-runtime': dataUrl('export const jsx = (t, p) => ({ t, p }); export const jsxs = (t, p) => ({ t, p })')
}

const requested = []

module.registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL === PLUGIN_URL) {
      requested.push(specifier)

      if (!(specifier in STUBS)) {
        throw new Error(`plugin imports ${specifier}: the desktop runtime loader refuses it`)
      }

      return { shortCircuit: true, url: STUBS[specifier] }
    }

    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    // No package.json next to the asset: load it as ESM, as the app does.
    return url === PLUGIN_URL ? { ...nextLoad(url, context), format: 'module' } : nextLoad(url, context)
  }
})

const plugin = await import(PLUGIN_URL)
const sdk = await import(STUBS['@hermes/plugin-sdk'])

test('plugin.js imports only what the desktop runtime loader provides', () => {
  assert.ok(requested.length > 0)
  assert.deepEqual([...new Set(requested)].filter(s => !(s in STUBS)), [])
})

test('the plugin registers the Servicios page, its sidebar entry and a palette command on one path', () => {
  const contributions = []
  const ctx = {
    register: c => contributions.push(c),
    registerMany: cs => contributions.push(...cs),
    setTimeout: () => () => {},
    os: {},
    rest: async () => ({})
  }

  assert.equal(plugin.default.id, 'janitor')
  assert.notEqual(plugin.default.defaultEnabled, false)
  plugin.default.register(ctx)

  const byArea = Object.fromEntries(contributions.map(c => [c.area, c]))
  const route = byArea[sdk.ROUTES_AREA]
  const nav = byArea[sdk.SIDEBAR_NAV_AREA]
  const palette = byArea[sdk.PALETTE_AREA]

  assert.equal(typeof route.render, 'function')
  assert.equal(nav.data.path, route.data.path)
  assert.equal(nav.data.label, 'Servicios')
  palette.data.run()
  assert.deepEqual(sdk.calls.navigate, [route.data.path])
})

test('each state maps to a badge and only the buttons that make sense for it', () => {
  assert.deepEqual(plugin.stateView('running').actions, ['stop'])
  assert.deepEqual(plugin.stateView('stopped').actions, ['start'])
  assert.deepEqual(plugin.stateView('partial').actions, ['start', 'stop'])
  assert.deepEqual(plugin.stateView('not_installed').actions, ['install'])
  assert.deepEqual(plugin.stateView('docker_unavailable').actions, [])
  // An unknown state (Open Design, or a newer backend) never offers start/stop.
  assert.deepEqual(plugin.stateView('something-new').actions, ['install'])

  const labels = ['running', 'partial', 'stopped', 'not_installed', 'docker_unavailable', 'x'].map(
    s => plugin.stateView(s).label
  )
  assert.equal(new Set(labels).size, labels.length, 'every state reads differently')
})

test('a running container is not a working service: health decides the badge and «Abrir»', () => {
  const responding = plugin.stateView('running', 'responding')
  const silent = plugin.stateView('running', 'not_responding')
  const unchecked = plugin.stateView('running', 'unchecked')
  const oldBackend = plugin.stateView('running', undefined)

  assert.equal(responding.openable, true)
  assert.equal(silent.openable, false)
  assert.match(silent.hint, /no contesta/)
  assert.equal(unchecked.label, oldBackend.label)
  assert.match(unchecked.label, /[Cc]ontenedor/)
  assert.equal(new Set([responding.label, silent.label, unchecked.label]).size, 3)
  for (const view of [responding, silent, unchecked]) {
    assert.deepEqual(view.actions, ['stop'])
  }
  // Health only refines a running service; it never turns a stopped one into "En marcha".
  assert.equal(plugin.stateView('stopped', 'responding').label, plugin.stateView('stopped').label)

  const [entry] = plugin.entriesFrom({ services: [{ name: 'n8n', skill: 'janitor-n8n', state: 'running', health: 'not_responding' }] })
  assert.equal(entry.health, 'not_responding')
})

test('the install hand-off names the guided skill and asks for confirmation, without sending anything', () => {
  const text = plugin.installRequest({
    label: 'Honcho',
    skill: 'janitor-honcho',
    skillMd: '/opt/janitor/skills/services/janitor-honcho/SKILL.md'
  })

  assert.match(text, /Honcho/)
  assert.match(text, /janitor-honcho/)
  assert.match(text, /\/opt\/janitor\/skills\/services\/janitor-honcho\/SKILL\.md/)
  assert.match(text, /confirmación antes de cambiar nada/)
  assert.doesNotMatch(text, /hermes/i)
})

test('service-name validation mirrors the backend: no paths, flags or upper case', () => {
  for (const ok of ['honcho', 'n8n', 'janitor-waha']) {
    assert.equal(plugin.isValidServiceName(ok), true, ok)
  }

  for (const bad of ['', '../honcho', 'a/b', '..', '-rf', 'Honcho', 'honcho;rm', 'honcho ', 'x'.repeat(41), null]) {
    assert.equal(plugin.isValidServiceName(bad), false, String(bad))
  }
})

test('entries keep backend services and stateless applications, with the WAHA privacy note', () => {
  const entries = plugin.entriesFrom({
    docker: { available: true, status: 'ok' },
    services: [
      { name: 'waha', skill: 'janitor-waha', skill_md: '/x/SKILL.md', url: 'http://127.0.0.1:3000', state: 'running', containers: [{ name: 'janitor-waha', state: 'running' }] },
      { name: 'future', skill: 'janitor-future', skill_md: '', url: '', state: 'stopped', containers: [] }
    ],
    unmanaged: [{ skill: 'janitor-opendesign', skill_md: '/y/SKILL.md' }]
  })

  const [waha, future, design] = entries
  assert.match(waha.note, /proveedor de IA/)
  assert.match(waha.note, /[Ss]olo lectura/)
  assert.equal(future.label, 'future')
  assert.doesNotMatch(future.description, /[A-Za-z]+ (self-host|backend)/)
  assert.equal(design.managed, false)
  assert.equal(design.state, 'unknown')
  assert.deepEqual(plugin.stateView(design.state).actions, ['install'])
})

test('visible copy never says Hermes', () => {
  const texts = [
    ...Object.values(plugin.APPS).flatMap(a => [a.label, a.description, a.note ?? '']),
    ...['ok', 'missing', 'unavailable', 'timeout'].map(status => plugin.dockerLine({ status })),
    ...['busy', 'docker_unavailable', 'not_installed', 'timeout', 'docker_failed', 'x'].map(plugin.errorText),
    ...['start', 'stop', 'x'].map(plugin.pendingText),
    ...['responding', 'not_responding', 'unchecked'].flatMap(h => {
      const view = plugin.stateView('running', h)

      return [view.label, view.hint ?? '']
    })
  ]

  for (const text of texts) {
    assert.doesNotMatch(text, /hermes/i, text)
  }
})

test('REST failures map to an inline error code', () => {
  assert.equal(plugin.restErrorCode(new Error('404: unknown service')), 'unknown_service')
  assert.equal(plugin.restErrorCode(new Error('fetch failed')), 'unreachable')
  assert.equal(plugin.isOpenableUrl('http://127.0.0.1:1973'), true)
  assert.equal(plugin.isOpenableUrl('file:///etc/passwd'), false)
})
