#!/usr/bin/env node
// Validate the release unit before smoke, upload or publication.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { lstatSync, readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

export function verifyArtifacts({ directory, commit, development = false }) {
  assert.match(commit, /^[a-f0-9]{40}$/, 'A full source commit is required')
  const manifest = JSON.parse(readFileSync(path.join(directory, 'janitor-release.json'), 'utf8'))
  assert.equal(manifest.commit, commit, 'Artifact source differs from the validated commit')
  assert.equal(manifest.buildKind, development ? 'development' : 'release')
  assert.equal(manifest.repository, 'reck74/Janitor-Agent')
  if (!development) assert.equal(manifest.sourceDirty, false, 'Release source was dirty')
  assert.match(manifest.janitorVersion, development ? /^\d+\.\d+\.\d+-dev\.[a-f0-9]{12}$/ : /^\d+\.\d+\.\d+$/)
  assert.match(manifest.upstreamRef, /^[a-f0-9]{40}$/)
  const images = readdirSync(directory).filter(name => name.endsWith('.AppImage'))
  assert.equal(images.length, 1, 'Publish one Linux x86_64 AppImage per release unit')
  const artifact = images[0]
  assert.ok([`janitor-desktop-${manifest.janitorVersion}-linux-x86_64.AppImage`, `janitor-desktop-${manifest.janitorVersion}-linux-x64.AppImage`].includes(artifact))
  const file = path.join(directory, artifact), stat = lstatSync(file)
  assert.ok(stat.isFile() && !stat.isSymbolicLink() && (stat.mode & 0o111), 'AppImage must be a regular executable')
  const sidecar = JSON.parse(readFileSync(`${file}.json`, 'utf8'))
  assert.deepEqual(sidecar, { ...manifest, artifact }, 'AppImage metadata differs from the release manifest')
  const checksum = createHash('sha256').update(readFileSync(file)).digest('hex')
  assert.equal(readFileSync(`${file}.sha256`, 'utf8'), `${checksum}  ${artifact}\n`, 'AppImage checksum does not match')
  return { artifact, commit, version: manifest.janitorVersion, buildKind: manifest.buildKind, sha256: checksum }
}
if (path.resolve(process.argv[1] || '') === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { directory: { type: 'string' }, commit: { type: 'string' }, development: { type: 'boolean' } } })
  console.log(JSON.stringify(verifyArtifacts(values)))
}
