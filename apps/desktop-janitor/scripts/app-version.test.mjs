// P21 (brand/app-version.mjs): the app shows and carries Janitor's version.
// Read-only on apps/desktop and the repo.

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import vm from 'node:vm'

import { APP_VERSION_PATCHES, REPO_ROOT, janitorAppVersion, janitorDisplayVersion, pyprojectVersion } from '../brand/app-version.mjs'

import { APP_DIR, janitorBuilderConfig, readJson } from './build.mjs'
import { checkPatches, computePatchedFiles } from './patch-engine.mjs'

// Known cases of janitor/version.py display_version (first `+` only).
const DISPLAY_CASES = [
  ['0.21.5+janitor.1', '0.21.5-janitor.1'],
  ['0.20.1+janitor.2', '0.20.1-janitor.2'],
  ['1.2.3', '1.2.3'],
  ['1.2.3-janitor.4', '1.2.3-janitor.4'],
  ['1+2+3', '1-2+3']
]

test('janitorDisplayVersion follows janitor/version.py display_version', () => {
  for (const [raw, shown] of DISPLAY_CASES) {
    assert.equal(janitorDisplayVersion(raw), shown, raw)
  }
})

test('pyprojectVersion reads [project].version and nothing else', () => {
  const text = [
    '[build-system]',
    'requires = ["setuptools"]',
    'version = "9.9.9"',
    '',
    '[project]',
    'name = "hermes-agent"',
    'version = "0.21.5+janitor.1"  # bumped by release',
    '',
    '[project.optional-dependencies]',
    'version = "8.8.8"'
  ].join('\r\n')

  assert.equal(pyprojectVersion(text), '0.21.5+janitor.1')
  assert.equal(pyprojectVersion("[project]\nversion = '1.0.0'\n"), '1.0.0')
  assert.throws(() => pyprojectVersion('[tool.x]\nversion = "1.0.0"\n'))
  assert.throws(() => pyprojectVersion('[project]\nname = "x"\n[tool.x]\nversion = "1.0.0"\n'))
})

test('janitorAppVersion is semver and refuses a version electron-builder would reject', () => {
  assert.match(janitorAppVersion(), /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/)

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-version-'))

  try {
    fs.writeFileSync(path.join(root, 'pyproject.toml'), '[project]\nversion = "0.21.5+janitor.1"\n')
    assert.equal(janitorAppVersion(root), '0.21.5-janitor.1')
    fs.writeFileSync(path.join(root, 'pyproject.toml'), '[project]\nversion = "0.21"\n')
    assert.throws(() => janitorAppVersion(root), /not semver/)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('the app version is the release tag without its v (janitor/release_channel.py)', t => {
  const python = spawnSync('python3', ['-m', 'janitor.release_channel', '--expected-tag'], {
    cwd: REPO_ROOT,
    encoding: 'utf8'
  })

  if (python.error || python.status !== 0) {
    t.skip('python3 cannot run janitor.release_channel here')

    return
  }

  assert.equal(`v${janitorAppVersion()}`, python.stdout.trim())
})

test('the builder config carries Janitor\'s version, not apps/desktop/package.json\'s', () => {
  const merged = janitorBuilderConfig()
  const upstreamVersion = readJson(path.join(APP_DIR, 'package.json')).version

  assert.equal(merged.extraMetadata.version, janitorAppVersion())
  assert.notEqual(merged.extraMetadata.version, upstreamVersion)
  // The other extraMetadata keys survive the merge.
  assert.equal(merged.extraMetadata.productName, 'Janitor')
  // Artifact names stay unversioned: the release workflow looks them up by name.
  assert.doesNotMatch(merged.artifactName, /version/)
})

test('P21 resolves against apps/desktop and the shipped helper converts the engine version', () => {
  const { ok, results } = checkPatches(APP_DIR, APP_VERSION_PATCHES)

  assert.ok(ok, JSON.stringify(results.filter(r => !r.ok)))

  const main = computePatchedFiles(APP_DIR, APP_VERSION_PATCHES).get('electron/main.ts').toString('utf8')
  // Evaluate the injected definition exactly as it ships.
  const start = main.indexOf('function janitorDisplayVersion(')
  const end = main.indexOf('\n}\n', start) + 2
  const context = vm.createContext({})

  vm.runInContext(main.slice(start, end), context)

  for (const [raw, shown] of DISPLAY_CASES) {
    assert.equal(context.janitorDisplayVersion(raw), shown, raw)
  }
})
