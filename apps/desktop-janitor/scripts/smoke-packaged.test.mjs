import assert from 'node:assert/strict'
import path from 'node:path'
import { test } from 'node:test'

import { buildSmokeEnv, checkFirstScreen, launchArgs } from './smoke-packaged.mjs'

const INSTALL_SCREEN = 'Configurar Janitor\nInstalar Janitor localmente\nSe instalará en /tmp/x/home/.janitor/hermes-agent'

test('smoke env drops inherited HERMES_*/JANITOR_* and isolates home and userData in the sandbox', () => {
  const sandbox = path.join(path.sep, 'sb')
  const env = buildSmokeEnv(
    { HERMES_HOME: '/real/home', JANITOR_SKILLS_ROOT: '/x', hermes_foo: 'y', SystemRoot: 'C:\\Windows', HOME: '/real' },
    sandbox,
    'linux'
  )

  for (const [key, value] of Object.entries(env)) {
    if (/^(HERMES|JANITOR)_/i.test(key)) assert.ok(value.startsWith(sandbox) || value === '1', `${key}=${value}`)
  }
  assert.ok(env.HOME.startsWith(sandbox))
  assert.ok(env.HERMES_HOME.startsWith(env.HOME))
  assert.ok(env.HERMES_DESKTOP_USER_DATA_DIR.startsWith(sandbox))
  assert.equal(env.hermes_foo, undefined)
  assert.equal(env.SystemRoot, 'C:\\Windows')

  const win = buildSmokeEnv({ USERPROFILE: 'C:\\Users\\real', LOCALAPPDATA: 'C:\\real' }, sandbox, 'win32')
  for (const key of ['USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP']) assert.ok(win[key].startsWith(sandbox), key)
})

test('only Linux gets the headless flags', () => {
  assert.ok(launchArgs('linux').includes('--ozone-platform=headless'))
  assert.deepEqual(launchArgs('win32'), [])
  assert.deepEqual(launchArgs('darwin'), [])
})

test('first screen: branded Spanish install screen passes; paths with hermes are accepted', () => {
  assert.deepEqual(checkFirstScreen({ title: 'Janitor', lang: 'es', text: INSTALL_SCREEN }), [])
  assert.deepEqual(
    checkFirstScreen({ title: 'Janitor', lang: 'es-ES', text: 'El backend de Janitor no pudo iniciarse: boom' }),
    []
  )
})

test('first screen: Hermes in visible text, English, wrong title or no first screen fail', () => {
  const fails = screen => checkFirstScreen({ title: 'Janitor', lang: 'es', text: INSTALL_SCREEN, ...screen })

  assert.equal(fails({ text: `${INSTALL_SCREEN}\nInstalar Hermes` }).length, 1)
  assert.equal(fails({ lang: 'en' }).length, 1)
  assert.equal(fails({ title: 'Hermes' }).length, 1)
  assert.equal(fails({ text: 'Cargando…' }).length, 1)
})
