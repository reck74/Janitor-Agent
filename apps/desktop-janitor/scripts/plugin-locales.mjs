// P11: inject Spanish bundles into the bundled desktop plugins at build time
// (task F1-10). Bundles live in brand/plugin-locales/<plugin>.es.mjs as a
// single `export default { … }`; that object text is spliced into the plugin
// source at an exact anchor. Helpers here also read the plugin's own English
// bundle back out of its source, so the tests can compare shapes.

import fs from 'node:fs'
import module from 'node:module'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const BRAND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'brand', 'plugin-locales')

export const PLUGIN_LOCALES = [
  {
    plugin: 'kanban',
    file: 'src/plugins/kanban/i18n.ts',
    english: 'export const en: KanbanMessages = ',
    spanish: 'const es: KanbanMessages = ',
    find: "export const KANBAN_LOCALES: PluginLocaleBundles = { en, ja, zh, 'zh-hant': zhHant }",
    replace: literal =>
      `const es: KanbanMessages = ${literal}\n\nexport const KANBAN_LOCALES: PluginLocaleBundles = { en, es, ja, zh, 'zh-hant': zhHant }`
  },
  {
    plugin: 'hermes-bots',
    file: 'src/plugins/hermes-bots/i18n.ts',
    english: 'const en: BotsMessages = ',
    spanish: 'const es: BotsMessages = ',
    find: "export const BOTS_LOCALES: PluginLocaleBundles = { en, ja, zh, 'zh-hant': zhHant }",
    replace: literal =>
      `const es: BotsMessages = ${literal}\n\nexport const BOTS_LOCALES: PluginLocaleBundles = { en, es, ja, zh, 'zh-hant': zhHant }`
  },
  {
    plugin: 'radio',
    file: 'src/plugins/radio/plugin.js',
    english: 'const EN = ',
    spanish: '  en: EN,\n  es: ',
    find: 'const LOCALES = {\n  en: EN,\n',
    replace: literal => `const LOCALES = {\n  en: EN,\n  es: ${literal},\n`
  }
]

export function bundlePath(plugin) {
  return path.join(BRAND_DIR, `${plugin}.es.mjs`)
}

/** The object-literal text of a brand bundle file (`export default <here>`). */
export function bundleLiteral(plugin) {
  const text = fs.readFileSync(bundlePath(plugin), 'utf8')
  const match = /^export default /m.exec(text)

  if (!match) throw new Error(`${bundlePath(plugin)}: no top-level \`export default\``)

  return text.slice(match.index + match[0].length).trim().replace(/;$/, '')
}

export function pluginLocalePatches(entries = PLUGIN_LOCALES) {
  return entries.map(entry => ({
    id: `P11-locale-es:${entry.plugin}`,
    purpose: `Spanish bundle for the ${entry.plugin} plugin (brand/plugin-locales/${entry.plugin}.es.mjs)`,
    file: entry.file,
    find: entry.find,
    replace: entry.replace(bundleLiteral(entry.plugin)),
    count: 1
  }))
}

/** Text of the object literal that starts right after `prefix` in `source`. */
export function objectLiteralAfter(source, prefix) {
  const at = source.indexOf(prefix)

  if (at < 0 || source.indexOf(prefix, at + 1) >= 0) throw new Error(`anchor ${JSON.stringify(prefix)} must occur exactly once`)

  const start = at + prefix.length
  const end = matchingBracket(source, start)

  if (end < 0) throw new Error(`unbalanced object literal after ${JSON.stringify(prefix)}`)

  return source.slice(start, end + 1)
}

// Index of the bracket closing the one at `open`. Skips strings, template
// literals (with nested ${}) and comments; object literals of messages hold
// no regex literals, so none are handled.
function matchingBracket(source, open) {
  const stack = []
  let i = open

  const skipString = quote => {
    for (i++; i < source.length; i++) {
      if (source[i] === '\\') i++
      else if (source[i] === quote) return
    }
  }

  const skipTemplate = () => {
    for (i++; i < source.length; i++) {
      if (source[i] === '\\') i++
      else if (source[i] === '`') return
      else if (source[i] === '$' && source[i + 1] === '{') {
        const close = matchingBracket(source, i + 1)

        if (close < 0) return
        i = close
      }
    }
  }

  for (; i < source.length; i++) {
    const ch = source[i]

    if (ch === "'" || ch === '"') skipString(ch)
    else if (ch === '`') skipTemplate()
    else if (ch === '/' && source[i + 1] === '/') i = source.indexOf('\n', i) < 0 ? source.length : source.indexOf('\n', i)
    else if (ch === '/' && source[i + 1] === '*') i = source.indexOf('*/', i) + 1
    else if ('{[('.includes(ch)) stack.push(ch)
    else if ('}])'.includes(ch)) {
      stack.pop()

      if (stack.length === 0) return i
    }
  }

  return -1
}

/** Evaluate an object literal (TypeScript annotations allowed) in a sandbox. */
export function evaluateLiteral(literal) {
  const js = module.stripTypeScriptTypes(`(${literal})`)

  return vm.runInNewContext(js)
}

const kind = value => (Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value)

/**
 * Shape differences between a plugin's English bundle and a translation:
 * missing/extra keys, value kinds, function arity, and interpolated
 * arguments English renders that the translation drops.
 */
export function shapeDifferences(english, translated, prefix = '') {
  const out = []
  const keys = new Set([...Object.keys(english), ...Object.keys(translated)])

  for (const key of keys) {
    const at = prefix ? `${prefix}.${key}` : key

    if (!(key in translated)) {
      out.push(`${at}: missing`)
      continue
    }

    if (!(key in english)) {
      out.push(`${at}: not in English`)
      continue
    }

    const a = english[key]
    const b = translated[key]

    if (kind(a) !== kind(b)) {
      out.push(`${at}: ${kind(b)} where English has ${kind(a)}`)
    } else if (kind(a) === 'object') {
      out.push(...shapeDifferences(a, b, at))
    } else if (kind(a) === 'function') {
      if (a.length !== b.length) out.push(`${at}: takes ${b.length} argument(s), English takes ${a.length}`)

      const probes = Array.from({ length: a.length }, (_, n) => `⟦${n}⟧`)
      const en = String(a(...probes))
      const es = String(b(...probes))

      for (const probe of probes) {
        if (en.includes(probe) && !es.includes(probe)) out.push(`${at}: drops argument ${probe}`)
      }
    }
  }

  return out
}

/** Every string a bundle can render (functions called with probes). */
export function renderedStrings(bundle, prefix = '') {
  const out = []

  for (const [key, value] of Object.entries(bundle)) {
    const at = prefix ? `${prefix}.${key}` : key

    if (typeof value === 'string') out.push([at, value])
    else if (typeof value === 'function') out.push([at, String(value(...Array.from({ length: value.length }, (_, n) => `⟦${n}⟧`)))])
    else if (value && typeof value === 'object') out.push(...renderedStrings(value, at))
  }

  return out
}
