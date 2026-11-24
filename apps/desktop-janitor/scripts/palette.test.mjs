// F1-19: the slash palette in Spanish (brand/palette.mjs). Each table is tied
// to its source of truth, so a sync that adds a command, a category, a usage
// hint or a catalog skill fails here instead of shipping English.
// Read-only on apps/desktop; the engine's command registry is read by
// importing hermes_cli.commands with the system Python (stdlib-only module).

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

import { REPO_ROOT } from '../brand/compat.mjs'
import {
  APP_GROUPS,
  ENGINE_EXTRA_GROUPS,
  NOT_OFFERED_BY_ENGINE_TEXT,
  PALETTE_GROUP_LABELS,
  SKILL_DESCRIPTIONS,
  USAGE_HINTS
} from '../brand/palette.mjs'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'
import { classifyLiterals, literalText } from './ts-literals.mjs'

const patched = computePatchedFiles(APP_DIR, allPatches())
const finalText = file => patched.get(file).toString('utf8')

const ENGINE_DUMP = `
import json, sys
sys.path.insert(0, sys.argv[1])
import hermes_cli.commands as c
print(json.dumps([
    {"name": "/" + d.name, "category": d.category, "hint": d.args_hint or "", "gateway_only": bool(d.gateway_only)}
    for d in c.COMMAND_REGISTRY
]))
`

function engineCommands() {
  const python = process.env.PYTHON || 'python3'
  const result = spawnSync(python, ['-I', '-c', ENGINE_DUMP, REPO_ROOT], { encoding: 'utf8' })

  assert.equal(result.status, 0, `could not read hermes_cli.commands with ${python}: ${result.stderr || result.error}`)

  return JSON.parse(result.stdout)
}

const ENGINE = engineCommands()

function spanishCommandDescs() {
  const es = finalText('src/i18n/es.ts')
  const prefix = 'composer.commandDescs.'

  return new Map(
    classifyLiterals(es)
      .values.filter(v => v.path.startsWith(prefix))
      .map(v => [v.path.slice(prefix.length), literalText(es, v)])
  )
}

// Rows of the final registry whose value is null: the build offers them.
function offeredByRegistry() {
  const registry = JSON.parse(finalText('src/lib/desktop-slash-registry.json'))

  return new Set(Object.entries(registry).flatMap(([name, surface]) => (surface === null ? [name] : [])))
}

function engineOffered() {
  const offered = offeredByRegistry()

  return ENGINE.filter(cmd => !cmd.gateway_only && offered.has(cmd.name) && !(cmd.name in NOT_OFFERED_BY_ENGINE_TEXT))
}

// Minimal reader for janitor/catalog.yaml (`- id:` then `source:` per skill).
function catalogSkills() {
  const text = fs.readFileSync(path.join(REPO_ROOT, 'janitor', 'catalog.yaml'), 'utf8')
  const skills = []

  for (const line of text.split('\n')) {
    const id = line.match(/^ {2}- id: (\S+)\s*$/)
    const source = line.match(/^ {4}source: (\S+)\s*$/)

    if (id) skills.push({ id: id[1] })
    else if (source && skills.length > 0) skills.at(-1).source = source[1]
  }

  return skills
}

// ---- group headers -----------------------------------------------------------

test('every palette group the engine or the app can send has a Spanish header', () => {
  const groups = new Set([...ENGINE.map(cmd => cmd.category), ...ENGINE_EXTRA_GROUPS, ...APP_GROUPS])
  const missing = [...groups].filter(group => !PALETTE_GROUP_LABELS[group])

  assert.deepEqual(missing, [], 'add these groups to PALETTE_GROUP_LABELS in brand/palette.mjs')
})

test('the header labels are Spanish: none says hermes, only declared words equal the English key', () => {
  for (const [group, label] of Object.entries(PALETTE_GROUP_LABELS)) {
    assert.doesNotMatch(label, /hermes/i, group)

    if (label === group) assert.equal(group, 'Skills', `${group}: untranslated header`)
  }
})

test('the popover renders the translated header, not the raw group value', () => {
  const source = finalText('src/app/chat/composer/trigger-popover.tsx')

  assert.match(source, /\{JANITOR_PALETTE_GROUPS\[group \?\? ''\] \?\? group\}<\/div>/)

  for (const label of Object.values(PALETTE_GROUP_LABELS)) assert.ok(source.includes(`'${label}'`), label)
})

// ---- command descriptions and usage hints -----------------------------------------

test('every engine command the palette offers has a Spanish description', () => {
  const descs = spanishCommandDescs()
  const missing = engineOffered()
    .filter(cmd => !descs.has(cmd.name))
    .map(cmd => cmd.name)

  assert.deepEqual(missing, [], 'offered with the engine English text — add composer.commandDescs via brand/catalog-overrides.mjs or hide them')
})

test('every offered usage hint is pinned in USAGE_HINTS, and every pin matches the engine', () => {
  const byName = new Map(engineOffered().map(cmd => [cmd.name, cmd]))
  const missing = [...byName.values()].filter(cmd => cmd.hint && !USAGE_HINTS[cmd.name]).map(cmd => `${cmd.name} ${cmd.hint}`)
  const stale = Object.entries(USAGE_HINTS)
    .filter(([name, [en]]) => byName.get(name)?.hint !== en)
    .map(([name, [en]]) => `${name}: pinned ${JSON.stringify(en)}, engine ${JSON.stringify(byName.get(name)?.hint ?? '(not offered)')}`)

  assert.deepEqual(missing, [], 'usage hints that would render in English')
  assert.deepEqual(stale, [], 'USAGE_HINTS rows out of date')
})

test('Spanish usage hints keep every subcommand and flag the engine expects', () => {
  for (const [name, [en, es]] of Object.entries(USAGE_HINTS)) {
    const literals = text => (text.match(/--?[a-z][\w-]*|\b(?:on|off|status|list|clear|pause|resume|show|hide)\b/g) ?? []).sort()

    assert.deepEqual(literals(es), literals(en), name)
    assert.doesNotMatch(es, /hermes/i, name)
  }
})

test('/subscription, /upgrade, /topup and /debug are not offered', () => {
  const offered = offeredByRegistry()

  for (const name of ['/subscription', '/upgrade', '/topup', '/debug']) assert.equal(offered.has(name), false, name)
})

// ---- skill rows ------------------------------------------------------------------

test('every upstream skill of the Janitor catalog has a Spanish palette row, and no row is stale', () => {
  const upstream = catalogSkills()
    .filter(skill => skill.source !== 'janitor')
    .map(skill => skill.id)
    .sort()

  assert.ok(upstream.length > 0, 'catalog reader found no upstream skills')
  assert.deepEqual(Object.keys(SKILL_DESCRIPTIONS).sort(), upstream)
})

test('the skill rows reach es.ts and never shadow a command of the English catalog', () => {
  const descs = spanishCommandDescs()
  const en = fs.readFileSync(path.join(APP_DIR, 'src/i18n/en.ts'), 'utf8')
  const enCommands = new Set(
    classifyLiterals(en)
      .values.filter(v => v.path.startsWith('composer.commandDescs.'))
      .map(v => v.path.slice('composer.commandDescs.'.length))
  )

  for (const [id, text] of Object.entries(SKILL_DESCRIPTIONS)) {
    assert.equal(descs.get(`/${id}`), text.replace(/'/g, "\\'"), id)
    assert.equal(enCommands.has(`/${id}`), false, `/${id} is a command upstream translates`)
    assert.equal(ENGINE.some(cmd => cmd.name === `/${id}`), false, `/${id} is an engine command`)
  }
})

test('Janitor skills carry their palette text at the source: no override row for them', () => {
  for (const skill of catalogSkills().filter(s => s.source === 'janitor')) {
    assert.equal(skill.id in SKILL_DESCRIPTIONS, false, skill.id)
  }
})
