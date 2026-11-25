// F4-02, F4-04, F4-05: the Janitor desktop plugin (Servicios, Skills and
// Agentes screens). The plugin ships as a
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
      state: { profile: { get: () => 'default' } },
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
    export const Input = () => null
    export const Switch = () => null
    export const useQuery = () => ({})
    export const useQueryClient = () => ({})
    export const useValue = atom => atom.get()
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

test('the plugin registers each page with its sidebar entry and palette command on one path', () => {
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

  const routes = contributions.filter(c => c.area === sdk.ROUTES_AREA)
  const navs = contributions.filter(c => c.area === sdk.SIDEBAR_NAV_AREA)
  const palette = contributions.filter(c => c.area === sdk.PALETTE_AREA)

  assert.deepEqual(navs.map(n => n.data.label), ['Servicios', 'Skills', 'Agentes'])
  assert.equal(new Set(routes.map(r => r.data.path)).size, 3)

  for (const nav of navs) {
    const route = routes.find(r => r.data.path === nav.data.path)
    assert.equal(typeof route?.render, 'function', nav.data.label)
  }

  for (const command of palette) {
    command.data.run()
  }

  assert.deepEqual(sdk.calls.navigate, navs.map(n => n.data.path))
  assert.equal(new Set(contributions.map(c => c.id)).size, contributions.length)
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

test('the install hand-off names the guided skill by id, carries no path and asks for confirmation', () => {
  const text = plugin.installRequest({ label: 'Honcho', skill: 'janitor-honcho' })

  assert.match(text, /Honcho/)
  assert.match(text, /janitor-honcho/)
  assert.doesNotMatch(text, /\//)
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
      { name: 'waha', skill: 'janitor-waha', url: 'http://127.0.0.1:3000', state: 'running', containers: [{ name: 'janitor-waha', state: 'running' }] },
      { name: 'future', skill: 'janitor-future', url: '', state: 'stopped', containers: [] }
    ],
    unmanaged: [{ skill: 'janitor-opendesign' }]
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

test('an unsupported system says why instead of blaming Docker', () => {
  const line = plugin.dockerLine({ status: 'unsupported' })

  assert.match(line, /Windows/)
  assert.match(line, /Linux o macOS/)
  assert.notEqual(line, plugin.dockerLine({ status: 'unavailable' }))
})

test('visible copy never says Hermes', () => {
  const texts = [
    ...Object.values(plugin.APPS).flatMap(a => [a.label, a.description, a.note ?? '']),
    ...['ok', 'missing', 'unavailable', 'timeout', 'unsupported'].map(status => plugin.dockerLine({ status })),
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

// --- Skills (F4-04) and Agentes (F4-05) ---------------------------------------

const CATALOG_FILE = path.resolve(HERE, '..', '..', '..', 'janitor', 'catalog.yaml')
const { readFileSync } = await import('node:fs')
const catalogIds = [...readFileSync(CATALOG_FILE, 'utf8').matchAll(/^ {2}- id: (\S+)\s*$/gm)].map(m => m[1])

test('every catalog skill has Spanish copy: the English SKILL.md text is never needed', () => {
  assert.ok(catalogIds.length > 10)

  for (const id of catalogIds) {
    const info = plugin.skillInfo(id)
    assert.ok(info.label, id)
    assert.notEqual(info.description, 'Skill del catálogo de Janitor.', `${id} has no Spanish description`)
  }

  assert.equal(plugin.skillInfo('nueva-de-upstream').description, 'Skill del catálogo de Janitor.')
})

test('the skills screen shows the backend groups with the local selection; another OS can only be switched off', () => {
  const payload = {
    propositos: [
      {
        id: 'documentos',
        nombre: 'Documentos y oficina',
        skills: [
          { id: 'pdf', disponible: true, otra_plataforma: false, plataformas: [], descripcion: 'PDF files: create, read' },
          { id: 'docx', disponible: true, otra_plataforma: false, plataformas: [] }
        ]
      },
      {
        id: 'opcional',
        nombre: 'Opcionales',
        skills: [
          { id: 'apple-notes', disponible: false, otra_plataforma: true, plataformas: ['macos'] },
          { id: 'findmy', disponible: false, otra_plataforma: true, plataformas: ['macos'] }
        ]
      }
    ]
  }

  const [docs, optional] = plugin.skillGroups(payload, ['docx', 'findmy'])

  assert.equal(docs.label, 'Documentos y oficina')
  assert.deepEqual(docs.skills.map(s => [s.id, s.on]), [['pdf', false], ['docx', true]])
  assert.doesNotMatch(docs.skills[0].description, /create, read/)
  assert.deepEqual(optional.skills.map(s => [s.id, s.locked]), [['apple-notes', true], ['findmy', false]])
  assert.equal(optional.skills[0].note, 'Solo en macOS.')
})

test('toggling keeps order and a selection compares as a set', () => {
  assert.deepEqual(plugin.toggleSkill(['a', 'b'], 'c', true), ['a', 'b', 'c'])
  assert.deepEqual(plugin.toggleSkill(['a', 'b', 'c'], 'b', false), ['a', 'c'])
  assert.deepEqual(plugin.toggleSkill(['a'], 'a', true), ['a'])
  assert.equal(plugin.sameSelection(['a', 'b'], ['b', 'a']), true)
  assert.equal(plugin.sameSelection(['a'], ['a', 'b']), false)
})

test('profile names and skill ids never leave the plugin namespace', () => {
  assert.equal(plugin.skillsPath('default'), '/perfiles/default/skills')
  assert.equal(plugin.skillsPath('lupa_2'), '/perfiles/lupa_2/skills')

  for (const bad of ['', '..', '../x', 'a/b', 'A', '-x', 'x'.repeat(65), null, 'a b', 'a?b']) {
    assert.throws(() => plugin.skillsPath(bad), String(bad))
  }

  for (const id of catalogIds) {
    assert.equal(plugin.isValidSkillId(id), true, id)
  }

  for (const bad of ['', '..', '../pdf', 'a/b', 'PDF', '/etc']) {
    assert.equal(plugin.isValidSkillId(bad), false, bad)
  }
})

test('new agent names follow the backend rules', () => {
  for (const ok of ['lupa', 'lupa-2', 'mi_agente', 'x'.repeat(64)]) {
    assert.equal(plugin.newAgentNameError(ok, ['default']), null, ok)
  }

  for (const bad of ['', 'Lupa', '../lupa', 'lupa/x', 'default', 'hermes', '-x', 'a b', null, 7, 'x'.repeat(65)]) {
    assert.equal(plugin.newAgentNameError(bad, []), 'nombre_invalido', String(bad))
  }

  assert.equal(plugin.newAgentNameError('lupa', ['default', 'lupa']), 'existe')
})

test('agents read as people: the main one is Janitor, specialists carry their template', () => {
  assert.equal(plugin.profileLabel({ nombre: 'default', principal: true }), 'Janitor (principal)')
  assert.equal(plugin.profileLabel({ nombre: 'lupa', plantilla: 'investigador' }), 'lupa · Investigador')
  assert.equal(plugin.profileLabel({ nombre: 'suelto', plantilla: null }), 'suelto')
})

test('save and create failures read as Spanish lines, and the created line mentions credentials without values', () => {
  assert.equal(plugin.restStatus(new Error('400: invalid skills')), 400)
  assert.equal(plugin.restStatus(new Error('fetch failed')), null)
  assert.match(plugin.skillsErrorText(new Error('404: unknown profile')), /ya no existe/)
  assert.match(plugin.skillsErrorText(new Error('boom')), /No se guardó nada/)
  assert.match(plugin.agentErrorText('existe'), /No se sobrescribe/)
  assert.equal(plugin.agentErrorText('algo-nuevo'), plugin.agentErrorText('fallo'))
  assert.match(plugin.createdText({ nombre: 'lupa', credenciales: true }), /memoria vacía/)
  assert.match(plugin.createdText({ nombre: 'lupa', credenciales: false }), /configúralas/)
})

test('Skills and Agentes copy never says Hermes', () => {
  const texts = [
    ...catalogIds.flatMap(id => Object.values(plugin.skillInfo(id))),
    ...['nombre_invalido', 'existe', 'plantilla_desconocida', 'tiempo_agotado', 'fallo', 'unreachable'].map(plugin.agentErrorText),
    ...['400: x', '404: x', 'x'].map(m => plugin.skillsErrorText(new Error(m))),
    plugin.createdText({ nombre: 'a', credenciales: true }),
    plugin.createdText({ nombre: 'a', credenciales: false }),
    plugin.errorText('activation_failed')
  ]

  for (const text of texts) {
    assert.doesNotMatch(text, /hermes/i, text)
  }
})
