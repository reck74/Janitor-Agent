'use strict'
const base = require('../electron-builder.upstream.cjs')
const metadata = require('../../../janitor_ext/release.json')
module.exports = {
  ...base, appId: 'com.reck74.janitor-agent', productName: 'Janitor Agent',
  executableName: 'janitor-desktop', artifactName: 'janitor-desktop-${version}-${os}-${arch}.${ext}',
  icon: 'assets/janitor-icon.png',
  extraMetadata: { ...base.extraMetadata, name: 'janitor-desktop', productName: 'Janitor Agent', version: metadata.janitorVersion },
  directories: { ...base.directories, output: process.env.JANITOR_DESKTOP_OUTPUT || 'release' },
  publish: [{ provider: 'github', owner: 'reck74', repo: 'Janitor-Agent', channel: 'latest' }],
  extraResources: [...base.extraResources,
    { from: 'janitor/bootstrap', to: 'janitor-bootstrap' },
    { from: '../../janitor_ext/release.json', to: 'janitor-release.json' },
    { from: 'janitor/update.mjs', to: 'janitor-update.mjs' },
    { from: 'janitor/setup-preload.cjs', to: 'janitor-setup-preload.cjs' }],
  linux: { ...base.linux, icon: 'assets/janitor-icon.png', executableName: 'janitor-desktop', desktop: { entry: { Name: 'Janitor Agent' } },
    maintainer: 'Janitor Agent contributors', synopsis: 'Janitor Agent desktop', target: ['AppImage'] }
}
