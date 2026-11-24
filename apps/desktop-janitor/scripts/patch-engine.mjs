// Build-time patch engine for the Janitor desktop overlay (directive #17).
//
// A patch is { id, file, find, replace, count } — `file` relative to
// apps/desktop, `find` an exact string or a /g regex, `count` the exact number
// of matches expected — or { id, file, transform } for whole-file rules (the
// catalog brand rules). A patch whose anchor is missing or matches a different
// number of times FAILS, naming the patch id and file: that is how upstream
// drift surfaces at sync time.
//
// Every change to apps/desktop (asset copies and text patches) goes through a
// journaled transaction:
//   1. all patches are computed in memory first (an anchor miss writes nothing);
//   2. the original bytes of every target are saved to a journal directory and
//      a manifest is renamed into place BEFORE the first target is written;
//   3. restore() puts the originals back and deletes the journal.
// If the process dies between 2 and 3, the next run (or `build.mjs --restore`)
// finds the journal and restores first. A target edited since the build wrote
// it (e.g. an upstream merge after a crash) is never clobbered: restore stops
// and names it.

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

export const JOURNAL_DIRNAME = '.janitor-build-journal'

export class PatchError extends Error {
  constructor(patch, message) {
    super(`[patch ${patch.id}] ${patch.file}: ${message}`)
    this.patchId = patch.id
    this.file = patch.file
  }
}

export function defaultJournalDir(appDir) {
  return path.join(appDir, JOURNAL_DIRNAME)
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex')
}

export function countMatches(text, find) {
  if (typeof find === 'string') {
    if (!find) throw new Error('empty anchor')

    return text.split(find).length - 1
  }

  if (!find.flags.includes('g')) throw new Error(`regex anchor ${find} must use the g flag`)

  return [...text.matchAll(find)].length
}

/** Apply one patch to `text`, enforcing its anchor count. */
export function applyPatch(text, patch) {
  if (patch.transform) {
    try {
      return patch.transform(text)
    } catch (error) {
      throw new PatchError(patch, error.message)
    }
  }

  const found = countMatches(text, patch.find)

  if (found !== patch.count) {
    const anchor = typeof patch.find === 'string' ? JSON.stringify(patch.find.slice(0, 120)) : String(patch.find)

    throw new PatchError(
      patch,
      `anchor ${anchor} matched ${found} time(s), expected ${patch.count} — upstream changed this code; update the patch in apps/desktop-janitor/brand/`
    )
  }

  return typeof patch.find === 'string' ? text.split(patch.find).join(patch.replace) : text.replace(patch.find, patch.replace)
}

function readText(appDir, file) {
  const full = path.join(appDir, file)

  if (!fs.existsSync(full)) return null

  return fs.readFileSync(full, 'utf8')
}

/**
 * Compute every patched file in memory. Never writes.
 * Returns { files: Map<file, { original, patched }>, results: [{ id, file, ok, error? }] }.
 */
export function planPatches(appDir, patches) {
  const files = new Map()
  const results = []

  for (const patch of patches) {
    if (!files.has(patch.file)) {
      const original = readText(appDir, patch.file)

      files.set(patch.file, { original, patched: original })
    }

    const entry = files.get(patch.file)

    if (entry.patched === null) {
      results.push({ id: patch.id, file: patch.file, ok: false, error: `[patch ${patch.id}] ${patch.file}: file not found` })
      continue
    }

    try {
      entry.patched = applyPatch(entry.patched, patch)
      results.push({ id: patch.id, file: patch.file, ok: true })
    } catch (error) {
      results.push({ id: patch.id, file: patch.file, ok: false, error: error.message })
    }
  }

  return { files, results }
}

/** Dry run: verify every anchor against the current sources. Never writes. */
export function checkPatches(appDir, patches) {
  const { results } = planPatches(appDir, patches)

  return { ok: results.every(r => r.ok), results }
}

/** Patched text per file; throws one error listing every failed patch. */
export function computePatchedFiles(appDir, patches) {
  const { files, results } = planPatches(appDir, patches)
  const failures = results.filter(r => !r.ok)

  if (failures.length > 0) {
    throw new Error(`${failures.length} build patch(es) failed:\n${failures.map(f => `  ${f.error}`).join('\n')}`)
  }

  const writes = new Map()

  for (const [file, { original, patched }] of files) {
    if (patched !== original) writes.set(file, Buffer.from(patched, 'utf8'))
  }

  return writes
}

function resolveInside(appDir, relative) {
  const full = path.resolve(appDir, relative)

  if (full !== appDir && !full.startsWith(appDir + path.sep)) {
    throw new Error(`journal target escapes the app dir: ${relative}`)
  }

  return full
}

function processAlive(pid) {
  try {
    process.kill(pid, 0)

    return true
  } catch (error) {
    return error.code === 'EPERM'
  }
}

export function readJournal(journalDir) {
  const manifestPath = path.join(journalDir, 'manifest.json')

  if (!fs.existsSync(manifestPath)) return null

  return JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
}

/**
 * Restore every target recorded in the journal and delete it.
 * Returns the list of restored targets, or null when there is no journal.
 * Throws (and keeps the journal) when a target no longer holds what the build
 * wrote, unless `force` is set.
 */
export function restoreJournal(appDir, { journalDir = defaultJournalDir(appDir), force = false } = {}) {
  appDir = path.resolve(appDir)
  const manifest = readJournal(journalDir)

  if (!manifest) {
    // A crash before the manifest rename leaves backups but no manifest; no
    // target was written yet, so they are just debris.
    fs.rmSync(journalDir, { recursive: true, force: true })

    return null
  }

  const conflicts = []

  for (const entry of manifest.entries) {
    const full = resolveInside(appDir, entry.target)
    const current = fs.existsSync(full) ? sha256(fs.readFileSync(full)) : null
    const known = current === entry.patchedSha256 || current === entry.originalSha256 || (current === null && entry.originalSha256 === null)

    if (!known) conflicts.push(entry.target)
  }

  if (conflicts.length > 0 && !force) {
    throw new Error(
      `build journal ${journalDir} cannot be restored safely: these files changed after the build patched them:\n` +
        conflicts.map(c => `  ${c}`).join('\n') +
        '\nInspect them, then run `node apps/desktop-janitor/scripts/build.mjs --restore --force` to put the originals back anyway.'
    )
  }

  const restored = []

  for (const entry of manifest.entries) {
    const full = resolveInside(appDir, entry.target)

    if (entry.backup === null) {
      fs.rmSync(full, { force: true })
    } else {
      fs.writeFileSync(full, fs.readFileSync(path.join(journalDir, 'files', entry.backup)))
    }

    restored.push(entry.target)
  }

  fs.rmSync(journalDir, { recursive: true, force: true })

  return restored
}

/**
 * Restore a journal left by a dead build. Must run BEFORE patches are computed
 * (they are computed against the pristine tree). A journal held by a live
 * process aborts.
 */
export function recoverInterrupted(appDir, { journalDir = defaultJournalDir(appDir), log = () => {} } = {}) {
  appDir = path.resolve(appDir)
  const existing = readJournal(journalDir)

  if (existing) {
    if (existing.pid !== process.pid && processAlive(existing.pid)) {
      throw new Error(`another Janitor desktop build (pid ${existing.pid}) holds ${journalDir}`)
    }

    const restored = restoreJournal(appDir, { journalDir })
    log(`recovered an interrupted build: restored ${restored.length} file(s) from ${journalDir}`)

    return restored
  }

  if (fs.existsSync(journalDir)) fs.rmSync(journalDir, { recursive: true, force: true })

  return null
}

/**
 * Journaled write of `writes` (Map<target relative to appDir, Buffer>).
 * Returns restore(). Recovers a leftover journal first (see recoverInterrupted).
 */
export function beginTransaction(appDir, writes, { journalDir = defaultJournalDir(appDir), log = () => {} } = {}) {
  appDir = path.resolve(appDir)
  recoverInterrupted(appDir, { journalDir, log })

  const entries = []
  fs.mkdirSync(path.join(journalDir, 'files'), { recursive: true })

  for (const [target, content] of writes) {
    const full = resolveInside(appDir, target)
    const exists = fs.existsSync(full)
    const original = exists ? fs.readFileSync(full) : null
    const backup = exists ? String(entries.length) : null

    if (exists) fs.writeFileSync(path.join(journalDir, 'files', backup), original)

    entries.push({
      target,
      backup,
      originalSha256: original ? sha256(original) : null,
      patchedSha256: sha256(content)
    })
  }

  const manifestPath = path.join(journalDir, 'manifest.json')
  fs.writeFileSync(`${manifestPath}.tmp`, JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString(), entries }, null, 2))
  fs.renameSync(`${manifestPath}.tmp`, manifestPath)

  for (const [target, content] of writes) {
    fs.writeFileSync(resolveInside(appDir, target), content)
  }

  let done = false

  return () => {
    if (done) return []
    done = true

    return restoreJournal(appDir, { journalDir }) ?? []
  }
}
