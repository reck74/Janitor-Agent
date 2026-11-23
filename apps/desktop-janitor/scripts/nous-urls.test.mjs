// Nous / upstream-Hermes links in the app as the Janitor build ships it
// (F1-21b, directive #17). Every match of NOUS_URL in apps/desktop src/ and
// electron/ AFTER all build patches must be a row of
// brand/inventory/nous-urls.tsv with in_build = sí (decision c, or b when the
// element is hidden but its code stays). A new upstream link fails here with
// its file; a reapointed/removed one (in_build = no) must stay gone.
// Read-only on apps/desktop.

import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { allPatches } from './brand-patches.mjs'
import { APP_DIR } from './build.mjs'
import { computePatchedFiles } from './patch-engine.mjs'

const INVENTORY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'brand', 'inventory', 'nous-urls.tsv')

// nousresearch.com (any host or path), NousResearch/<repo> (GitHub or bare),
// and the Nous Discord invite.
export const NOUS_URL =
  /(?:https?:\/\/)?[\w.-]*nousresearch\.com(?:\/[^\s'"`<>)\\]*)?|(?:https?:\/\/)?(?:github\.com[:/]|raw\.githubusercontent\.com\/)?NousResearch\/[\w.-]+(?:[/#][^\s'"`<>)\\]*)?|discord\.gg\/NousResearch/gi

// Shipped sources: code and data under src/ and electron/, minus tests and the
// non-Spanish catalogs (the app runs in Spanish; directive #17).
export function isScanned(rel) {
  if (!/^(src|electron)\//.test(rel)) return false
  if (!/\.(ts|tsx|js|mjs|cjs|json|html)$/.test(rel)) return false
  if (/\.(test|spec)[.-]/.test(rel) || rel.split('/').includes('__tests__')) return false
  if (/^src\/i18n\/(intro-)?[a-z]{2}(-[a-z]+)?\.ts$/.test(rel) && !/\/(intro-)?es\.ts$/.test(rel)) return false

  return true
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue
    const full = path.join(dir, entry.name)

    if (entry.isDirectory()) walk(full, out)
    else out.push(full)
  }

  return out
}

export function nousUrls(text) {
  return [...text.matchAll(NOUS_URL)].map(m => m[0])
}

/** Every NOUS_URL match in the shipped sources of `appDir` after `patches`, as "path\turl" keys. */
export function builtNousUrls(appDir, patches) {
  const patched = computePatchedFiles(appDir, patches)
  const hits = []

  for (const root of ['src', 'electron']) {
    for (const file of walk(path.join(appDir, root)).sort()) {
      const rel = path.relative(appDir, file).split(path.sep).join('/')

      if (!isScanned(rel)) continue
      const text = (patched.get(rel) ?? fs.readFileSync(file)).toString('utf8')

      for (const url of nousUrls(text)) hits.push(`${rel}\t${url}`)
    }
  }

  return hits.sort()
}

export function readInventory(file = INVENTORY) {
  const [header, ...lines] = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean)
  const columns = header.split('\t')

  return lines.map(line => {
    const cells = line.split('\t')

    assert.equal(cells.length, columns.length, `malformed inventory row: ${line}`)

    return Object.fromEntries(columns.map((c, i) => [c, cells[i]]))
  })
}

const rows = readInventory()
const patches = allPatches()

test('every inventory row is complete and classified', () => {
  for (const row of rows) {
    assert.match(row.decision, /^[abc]$/, row.url)
    assert.match(row.in_build, /^(sí|no)$/, row.url)
    assert.ok(row.what.length > 5 && row.reason.length > 10, `${row.path}: ${row.url}`)
    // Reapointed or removed links never ship; kept ones always do.
    if (row.decision === 'a') assert.equal(row.in_build, 'no', `${row.path}: ${row.url}`)
    if (row.decision === 'c') assert.equal(row.in_build, 'sí', `${row.path}: ${row.url}`)
    assert.deepEqual(nousUrls(row.url), [row.url], `inventory url must be exactly one NOUS_URL match: ${row.url}`)
  }
})

test('the built app carries exactly the Nous/Hermes links the inventory keeps, no other', () => {
  const kept = rows.filter(r => r.in_build === 'sí').map(r => `${r.path}\t${r.url}`).sort()
  const built = builtNousUrls(APP_DIR, patches)
  const unexpected = [...built]
  const stale = []

  for (const key of kept) {
    const at = unexpected.indexOf(key)

    if (at < 0) stale.push(key)
    else unexpected.splice(at, 1)
  }

  assert.deepEqual(
    unexpected,
    [],
    'Nous/Hermes link(s) not in apps/desktop-janitor/brand/inventory/nous-urls.tsv — reapoint (a), hide (b) or keep with a reason (c)'
  )
  assert.deepEqual(stale, [], 'inventory rows kept (in_build = sí) that the build no longer contains — update the inventory')
})

test('links reapointed or removed (in_build = no) are gone from the built file', () => {
  const patched = computePatchedFiles(APP_DIR, patches)

  for (const row of rows.filter(r => r.in_build === 'no')) {
    const text = (patched.get(row.path) ?? fs.readFileSync(path.join(APP_DIR, row.path))).toString('utf8')

    assert.ok(!text.includes(row.url), `${row.path} still ships ${row.url}`)
  }
})

test('a new upstream Nous link fails the scan with its file', () => {
  const planted = "const SUPPORT = 'https://portal.nousresearch.com/new-page'; const DOCS = 'https://github.com/NousResearch/hermes-agent/wiki'"

  assert.deepEqual(nousUrls(planted), ['https://portal.nousresearch.com/new-page', 'https://github.com/NousResearch/hermes-agent/wiki'])
  assert.deepEqual(nousUrls("appId 'com.nousresearch.hermes' and https://github.com/reck74/Janitor-Agent/releases"), [])
  assert.ok(isScanned('src/app/new-thing.tsx'))
  assert.ok(isScanned('src/i18n/es.ts'))
  assert.ok(!isScanned('src/i18n/de.ts'))
  assert.ok(!isScanned('src/app/new-thing.test.tsx'))
})

// ---- other brand leftovers fixed in the same task ---------------------------

const built = file => computePatchedFiles(APP_DIR, patches).get(file).toString('utf8')

test('download and release-notes buttons point at the fork releases', () => {
  for (const file of ['src/app/updates-overlay.tsx', 'src/app/settings/about-settings.tsx']) {
    assert.match(built(file), /const INSTALLER_URL = 'https:\/\/github\.com\/reck74\/Janitor-Agent\/releases\/latest'/, file)
  }

  assert.match(built('src/app/settings/about-settings.tsx'), /const RELEASE_NOTES_URL = 'https:\/\/github\.com\/reck74\/Janitor-Agent\/releases'/)
})

test('the Telegram QR flow names the bot Janitor instead of letting the backend default to "Hermes Agent"', () => {
  const source = built('src/app/messaging/telegram-qr-setup.tsx')

  assert.match(source, /startTelegramOnboarding\('Janitor', scopeProfile\)/)
  assert.doesNotMatch(source, /startTelegramOnboarding\(undefined/)
})

test('Nous account commands /login and /topup are not offered in the slash palette or /help', () => {
  const registry = JSON.parse(built('src/lib/desktop-slash-registry.json'))

  // A non-null row is an unavailable spec the live catalog never overrides
  // (desktop-slash-commands.ts: resolveDesktopCommand / REGISTRY_OFFERED_NAMES).
  assert.equal(registry['/login'], 'settings')
  assert.equal(registry['/topup'], 'settings')
})

test('the update hand-off progress and the corrupt-store notice speak Janitor', () => {
  const main = built('electron/main.ts')

  assert.doesNotMatch(main, /Updating Hermes/)
  assert.equal(main.split("'Actualizando Janitor: esta ventana se cerrará").length - 1, 2)
  assert.match(built('src/app/chat/sidebar/section-states.tsx'), /janitor sessions recover --source &lt;state\.db&gt; --inspect-only/)
})
