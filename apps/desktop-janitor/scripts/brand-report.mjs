// Brand/i18n reports for the desktop overlay (read-only on apps/desktop).
//
//   node apps/desktop-janitor/scripts/brand-report.mjs untranslated
//       es.ts as the build ships it (P10 overrides + P6 brand rules): keys
//       missing from es.ts, values identical to en.ts that are not in
//       brand/catalog-overrides.mjs IDENTICAL_TO_ENGLISH, and stale allowlist
//       entries. Enforced by scripts/spanish.test.mjs.
//   node apps/desktop-janitor/scripts/brand-report.mjs thrown-errors [--write]
//       inventory of `new Error(<literal>)` in apps/desktop src/ and electron/
//       (path, line, has-brand, literal); --write refreshes
//       brand/inventory/thrown-errors.tsv. Not patched yet (scheduled work).

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { allPatches } from './brand-patches.mjs'
import { spanishCoverage } from './catalog-overrides.mjs'
import { computePatchedFiles } from './patch-engine.mjs'

const OVERLAY_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const APP_DIR = path.resolve(OVERLAY_DIR, '..', 'desktop')
export const INVENTORY_FILE = path.join(OVERLAY_DIR, 'brand', 'inventory', 'thrown-errors.tsv')

export function untranslatedReport(appDir = APP_DIR) {
  const es = computePatchedFiles(appDir, allPatches(appDir)).get('src/i18n/es.ts').toString('utf8')

  return spanishCoverage(es, fs.readFileSync(path.join(appDir, 'src', 'i18n', 'en.ts'), 'utf8'))
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue
    const full = path.join(dir, entry.name)

    if (entry.isDirectory()) walk(full, out)
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) out.push(full)
  }

  return out
}

const ERROR_LITERAL = /new Error\(\s*(['"`])((?:\\[\s\S]|(?!\1)[^\\])*?)\1/g

export function thrownErrorInventory(appDir = APP_DIR) {
  const rows = []

  for (const root of ['src', 'electron']) {
    for (const file of walk(path.join(appDir, root)).sort()) {
      const source = fs.readFileSync(file, 'utf8')

      for (const match of source.matchAll(ERROR_LITERAL)) {
        const line = source.slice(0, match.index).split('\n').length

        rows.push({
          path: path.relative(appDir, file).split(path.sep).join('/'),
          line,
          brand: /hermes/i.test(match[2]),
          literal: match[2]
        })
      }
    }
  }

  return rows
}

export function inventoryTsv(rows) {
  const clean = value => value.replace(/\t/g, ' ').replace(/\r?\n/g, '\\n')

  return ['path\tline\thas_hermes\tliteral', ...rows.map(r => `${r.path}\t${r.line}\t${r.brand ? 'yes' : 'no'}\t${clean(r.literal)}`)].join('\n') + '\n'
}

function main(argv) {
  const [command] = argv

  if (command === 'untranslated') {
    const { missing, identical, stale } = untranslatedReport()

    for (const key of missing) console.log(`missing\t${key}`)
    for (const row of identical) console.log(`identical\t${row.path}\t${JSON.stringify(row.value)}`)
    for (const key of stale) console.log(`stale-allowlist\t${key}`)
    console.error(`${missing.length} missing, ${identical.length} identical to English (not allowlisted), ${stale.length} stale allowlist entries`)

    return missing.length + identical.length + stale.length === 0 ? 0 : 1
  }

  if (command === 'thrown-errors') {
    const rows = thrownErrorInventory()
    const tsv = inventoryTsv(rows)

    if (argv.includes('--write')) {
      fs.mkdirSync(path.dirname(INVENTORY_FILE), { recursive: true })
      fs.writeFileSync(INVENTORY_FILE, tsv)
    } else {
      process.stdout.write(tsv)
    }

    const byRoot = root => rows.filter(r => r.path.startsWith(`${root}/`))
    console.error(
      `${rows.length} Error literal(s): src ${byRoot('src').length} (${byRoot('src').filter(r => r.brand).length} with Hermes), electron ${byRoot('electron').length} (${byRoot('electron').filter(r => r.brand).length} with Hermes)`
    )

    return 0
  }

  console.error('usage: brand-report.mjs untranslated | thrown-errors [--write]')

  return 2
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2))
}
