import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { ARCH_DIR, pkgverFromTag, renderArchPackage } from './arch-package.mjs'

// The Arch package is built and run on Linux only (the release workflow's
// arch-package job, an Arch container). Tests that source the PKGBUILD or run
// the launcher need Linux bash (macOS ships bash 3.2, where an empty array is
// unbound under `set -u`; Windows has no system bash): elsewhere they skip.
const LINUX_ONLY = process.platform !== 'linux' && 'Arch packaging runs on Linux only'
const has = tool => spawnSync('bash', ['-c', `command -v ${tool}`]).status === 0
const needs = tool => LINUX_ONLY || (!has(tool) && `${tool} not installed`)

function tmpdir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-arch-test-'))
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }))

  return dir
}

function fakeAppimage(dir) {
  const file = path.join(dir, 'Janitor-linux-x86_64.AppImage')
  fs.writeFileSync(file, 'not really an AppImage\n')

  return file
}

test('pkgver is the release tag without the v and with dots for dashes', () => {
  assert.equal(pkgverFromTag('v0.21.5-janitor.1'), '0.21.5.janitor.1')
  assert.equal(pkgverFromTag('v10.0.12-janitor.30'), '10.0.12.janitor.30')

  for (const bad of ['0.21.5-janitor.1', 'v0.21.5', 'v0.21.5+janitor.1', 'v0.21-janitor.1', 'v0.21.5-janitor.1-x', '', null]) {
    assert.throws(() => pkgverFromTag(bad), /v<n>\.<n>\.<n>-janitor\.<n>/, String(bad))
  }
})

test('the rendered PKGBUILD names the release and pins the real AppImage hash', { skip: LINUX_ONLY }, t => {
  const dir = tmpdir(t)
  const appimage = fakeAppimage(dir)
  const out = path.join(dir, 'pkg')

  const result = renderArchPackage({ appimage, tag: 'v0.21.5-janitor.1', outDir: out })
  const expectedSha = crypto.createHash('sha256').update(fs.readFileSync(appimage)).digest('hex')

  assert.equal(result.pkgver, '0.21.5.janitor.1')
  assert.ok(fs.existsSync(path.join(out, 'janitor-desktop-0.21.5.janitor.1.AppImage')))

  for (const source of ['janitor-desktop.sh', 'Janitor.desktop', 'LICENSE']) {
    assert.ok(fs.existsSync(path.join(out, source)), source)
  }

  const probe = spawnSync(
    'bash',
    ['-c', 'source PKGBUILD; printf "%s\\n" "$pkgname" "$pkgver" "$_tag" "${sha256sums[0]}" "${#source[@]}" "${#sha256sums[@]}"'],
    { cwd: out, encoding: 'utf8' }
  )

  assert.equal(probe.status, 0, probe.stderr)
  const [pkgname, pkgver, tag, sha, nSources, nSums] = probe.stdout.trim().split('\n')
  assert.equal(pkgname, 'janitor-desktop-bin')
  assert.equal(pkgver, '0.21.5.janitor.1')
  assert.equal(tag, 'v0.21.5-janitor.1')
  assert.equal(sha, expectedSha)
  assert.equal(nSources, nSums)

  // Each local source's checksum is the hash of the file shipped next to the PKGBUILD.
  const sums = spawnSync('bash', ['-c', 'source PKGBUILD; printf "%s\\n" "${sha256sums[@]:1}"'], {
    cwd: out,
    encoding: 'utf8'
  }).stdout.trim().split('\n')
  const local = [
    'janitor-desktop.sh',
    'Janitor.desktop',
    'LICENSE',
    'janitor-update-helper',
    'ai.janitor.desktop.update.policy',
    'update-key.pem'
  ].map(name =>
    crypto.createHash('sha256').update(fs.readFileSync(path.join(out, name))).digest('hex')
  )
  assert.deepEqual(sums, local)
})

test('the package carries the updater with the release public key, or an empty key the helper refuses', t => {
  const dir = tmpdir(t)
  const appimage = fakeAppimage(dir)
  const pem = crypto.generateKeyPairSync('ed25519').publicKey.export({ type: 'spki', format: 'pem' })
  const keyFile = path.join(dir, 'test-key.pem')

  fs.writeFileSync(keyFile, pem)

  const withKey = renderArchPackage({ appimage, tag: 'v0.21.5-janitor.1', outDir: path.join(dir, 'con'), updateKey: keyFile })
  const withoutKey = renderArchPackage({ appimage, tag: 'v0.21.5-janitor.1', outDir: path.join(dir, 'sin'), updateKey: path.join(dir, 'no-existe.pem') })

  assert.equal(withKey.hasUpdateKey, true)
  assert.equal(fs.readFileSync(path.join(dir, 'con', 'update-key.pem'), 'utf8'), pem)
  assert.equal(withoutKey.hasUpdateKey, false)
  assert.equal(fs.statSync(path.join(dir, 'sin', 'update-key.pem')).size, 0)
  assert.equal(fs.statSync(path.join(dir, 'con', 'janitor-update-helper')).mode & 0o777, 0o755)

  fs.writeFileSync(keyFile, 'esto no es una clave')
  assert.throws(() => renderArchPackage({ appimage, tag: 'v0.21.5-janitor.1', outDir: path.join(dir, 'mal'), updateKey: keyFile }), /not a PEM public key/)

  // The helper is only ever reachable through its own polkit action, password every time.
  const policy = fs.readFileSync(path.join(dir, 'con', 'ai.janitor.desktop.update.policy'), 'utf8')

  assert.match(policy, /<allow_active>auth_admin<\/allow_active>/)
  assert.match(policy, /<allow_any>no<\/allow_any>/)
  assert.match(policy, /exec\.path">\/usr\/lib\/janitor-desktop\/janitor-update-helper</)
})

test('rendering refuses a malformed tag before writing anything', t => {
  const dir = tmpdir(t)
  const out = path.join(dir, 'pkg')

  assert.throws(() => renderArchPackage({ appimage: fakeAppimage(dir), tag: 'v0.21.5', outDir: out }))
  assert.equal(fs.existsSync(out), false)
})

test('makepkg accepts the rendered PKGBUILD', { skip: needs('makepkg') }, t => {
  const dir = tmpdir(t)
  const out = path.join(dir, 'pkg')
  renderArchPackage({ appimage: fakeAppimage(dir), tag: 'v0.21.5-janitor.1', outDir: out })

  const run = spawnSync('makepkg', ['--printsrcinfo'], { cwd: out, encoding: 'utf8' })
  assert.equal(run.status, 0, run.stderr)
  assert.match(run.stdout, /pkgname = janitor-desktop-bin/)
})

test('the launcher runs the app with the user flags file before its own arguments', { skip: LINUX_ONLY }, t => {
  const dir = tmpdir(t)
  const appdir = path.join(dir, 'app')
  const config = path.join(dir, 'config')
  fs.mkdirSync(appdir)
  fs.mkdirSync(config)

  const fakeApp = path.join(appdir, 'Janitor')
  fs.writeFileSync(fakeApp, '#!/usr/bin/env bash\nprintf "<%s>\\n" "$@"\n')
  fs.chmodSync(fakeApp, 0o755)

  const env = { PATH: process.env.PATH, HOME: dir, JANITOR_DESKTOP_APPDIR: appdir, XDG_CONFIG_HOME: config }
  const launcher = path.join(ARCH_DIR, 'janitor-desktop.sh')

  const bare = spawnSync('bash', [launcher, 'janitor://x'], { env, encoding: 'utf8' })
  assert.equal(bare.status, 0, bare.stderr)
  assert.equal(bare.stdout, '<janitor://x>\n')

  fs.writeFileSync(
    path.join(config, 'janitor-desktop-flags.conf'),
    '# Wayland\n\n--ozone-platform=wayland\n   # indented comment\n  --enable-features=A,B  \n'
  )

  const run = spawnSync('bash', [launcher, 'one arg', '--two'], { env, encoding: 'utf8' })
  assert.equal(run.status, 0, run.stderr)
  assert.equal(run.stdout, '<--ozone-platform=wayland>\n<--enable-features=A,B>\n<one arg>\n<--two>\n')
})

test('the desktop entry is valid', { skip: needs('desktop-file-validate') }, () => {
  const run = spawnSync('desktop-file-validate', [path.join(ARCH_DIR, 'Janitor.desktop')], { encoding: 'utf8' })
  assert.equal(run.status, 0, run.stdout + run.stderr)
  assert.equal(run.stdout.trim(), '')
})
