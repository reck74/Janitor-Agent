// Janitor's electron-builder config: upstream's config deep-merged with
// electron-builder.janitor.json. CommonJS because the wrapper that build.mjs
// writes over apps/desktop/electron-builder.config.cjs (the only config
// upstream's run-electron-builder.mjs passes) requires it.
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const OVERRIDES_FILE = path.resolve(__dirname, '..', 'electron-builder.janitor.json')

const isPlainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)

function mergeBuilderConfig(base, overrides) {
  const merged = { ...base }

  for (const [key, value] of Object.entries(overrides)) {
    merged[key] = isPlainObject(value) && isPlainObject(base[key]) ? mergeBuilderConfig(base[key], value) : value
  }

  return merged
}

function janitorConfig(upstream) {
  return mergeBuilderConfig(upstream, JSON.parse(fs.readFileSync(OVERRIDES_FILE, 'utf8')))
}

module.exports = { OVERRIDES_FILE, janitorConfig, mergeBuilderConfig }
