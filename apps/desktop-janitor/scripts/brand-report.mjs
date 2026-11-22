// Brand/i18n reports for the desktop overlay (read-only on apps/desktop).
//
//   node apps/desktop-janitor/scripts/brand-report.mjs untranslated
//       es.ts leaves whose value is identical to en.ts (likely untranslated;
//       upstream's completeness test only checks that keys exist)
//   node apps/desktop-janitor/scripts/brand-report.mjs thrown-errors [--write]
//       inventory of `new Error(<literal>)` in apps/desktop src/ and electron/
//       (path, line, has-brand, literal); --write refreshes
//       brand/inventory/thrown-errors.tsv. Not patched yet (scheduled work).

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { identicalToEnglish } from './catalog-brand.mjs'

const OVERLAY_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const APP_DIR = path.resolve(OVERLAY_DIR, '..', 'desktop')
export const INVENTORY_FILE = path.join(OVERLAY_DIR, 'brand', 'inventory', 'thrown-errors.tsv')

export function untranslatedReport(appDir = APP_DIR, locale = 'es') {
  const read = name => fs.readFileSync(path.join(appDir, 'src', 'i18n', `${name}.ts`), 'utf8')

  return identicalToEnglish(read(locale), read('en'))
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
    const rows = untranslatedReport()

    for (const row of rows) console.log(`${row.path}\t${JSON.stringify(row.value)}`)
    console.error(`${rows.length} es.ts value(s) identical to en.ts (many are legitimately identical: URLs, product names, acronyms)`)

    return 0
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
