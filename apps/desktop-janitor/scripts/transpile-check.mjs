// Syntax check of patched TypeScript without writing into apps/desktop.
// Prefers esbuild from apps/desktop/node_modules (handles .ts and .tsx); the
// desktop-overlay CI job has no node_modules, so .ts files fall back to Node's
// built-in type stripping plus `node --check` on a temp copy.

import fs from 'node:fs'
import module, { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'

const esbuildByAppDir = new Map()

function loadEsbuild(appDir) {
  if (!esbuildByAppDir.has(appDir)) {
    try {
      esbuildByAppDir.set(appDir, createRequire(path.join(appDir, 'package.json'))('esbuild'))
    } catch {
      esbuildByAppDir.set(appDir, null)
    }
  }

  return esbuildByAppDir.get(appDir)
}

/**
 * Returns { ok: true, via } | { ok: false, via, error } | { ok: null, reason }
 * (null = no tool available for this file type on this machine).
 */
export function checkTranspiles(source, file, appDir) {
  const loader = file.endsWith('.tsx') ? 'tsx' : file.endsWith('.ts') ? 'ts' : null

  if (!loader) return { ok: null, reason: `not TypeScript: ${file}` }

  const tool = loadEsbuild(appDir)

  if (tool) {
    try {
      tool.transformSync(source, { loader, format: 'esm', sourcefile: file })

      return { ok: true, via: 'esbuild' }
    } catch (error) {
      return { ok: false, via: 'esbuild', error: error.message }
    }
  }

  if (loader === 'ts' && typeof module.stripTypeScriptTypes === 'function') {
    let js

    try {
      js = module.stripTypeScriptTypes(source)
    } catch (error) {
      return { ok: false, via: 'node-strip-types', error: error.message }
    }

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-transpile-'))
    const tmp = path.join(dir, `${path.basename(file)}.mjs`)

    try {
      fs.writeFileSync(tmp, js)
      const result = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' })

      return result.status === 0 ? { ok: true, via: 'node-strip-types' } : { ok: false, via: 'node --check', error: result.stderr }
    } finally {
      fs.rmSync(dir, { recursive: true, force: true })
    }
  }

  return { ok: null, reason: `no transpiler for ${file} (install apps/desktop deps for esbuild)` }
}
