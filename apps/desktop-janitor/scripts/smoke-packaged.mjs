// Launch smoke test of the PACKAGED Janitor app (F6-09).
//
// Starts the installed / extracted / mounted app with Playwright's Electron
// driver against a throwaway home, waits for the first screen (the
// «instalar Janitor» choice or the boot-error screen), checks branding and
// language, and ALWAYS writes a screenshot and the visible text to <out-dir>,
// also when a check fails. It never clicks anything: no install is started.
//
//   node apps/desktop-janitor/scripts/smoke-packaged.mjs <app executable> <out dir>
//
// The release workflow runs it on Linux, Windows and macOS and uploads <out-dir>
// as `janitor-smoke-<target>`: those screenshots are how the owner sees the app
// on systems nobody here runs.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const FIRST_SCREEN_RE = /Instalar Janitor localmente|no pudo iniciarse/i
const GLOBAL_TIMEOUT_MS = 4 * 60 * 1000
const FIRST_SCREEN_TIMEOUT_MS = 120 * 1000

/**
 * Environment for the app: the parent's (Windows and macOS need their system
 * variables) minus every HERMES_* / JANITOR_* the runner or the developer may
 * carry, with HOME, the profile and userData under `sandbox`.
 */
export function buildSmokeEnv(parentEnv, sandbox, platform = process.platform) {
  const env = {}

  for (const [key, value] of Object.entries(parentEnv)) {
    if (value === undefined || /^(HERMES|JANITOR)_/i.test(key)) continue
    env[key] = value
  }

  const home = path.join(sandbox, 'home')
  Object.assign(env, {
    HOME: home,
    // Without it the app puts the home at <userData>/hermes-home (main.ts,
    // resolveHermesHome) and that path shows on the install screen.
    HERMES_HOME: path.join(home, '.janitor'),
    HERMES_DESKTOP_USER_DATA_DIR: path.join(sandbox, 'user-data'),
    HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
    LANG: 'es_ES.UTF-8',
    TMPDIR: path.join(sandbox, 'tmp')
  })

  if (platform === 'win32') {
    Object.assign(env, {
      USERPROFILE: home,
      APPDATA: path.join(home, 'AppData', 'Roaming'),
      LOCALAPPDATA: path.join(home, 'AppData', 'Local'),
      TEMP: path.join(sandbox, 'tmp'),
      TMP: path.join(sandbox, 'tmp')
    })
  } else {
    Object.assign(env, {
      // A developer's ~/.local/bin/janitor must not be found as an existing install.
      PATH: '/usr/local/bin:/usr/bin:/bin',
      XDG_CONFIG_HOME: path.join(home, '.config'),
      XDG_DATA_HOME: path.join(home, '.local', 'share'),
      XDG_CACHE_HOME: path.join(home, '.cache'),
      XDG_STATE_HOME: path.join(home, '.local', 'state')
    })
  }

  return env
}

export function launchArgs(platform = process.platform) {
  return platform === 'linux' ? ['--ozone-platform=headless', '--no-sandbox', '--disable-gpu'] : []
}

/** Branding and language checks on the first screen. Returns a list of failures. */
export function checkFirstScreen({ title, lang, text }) {
  const failures = []

  if (!/Janitor/.test(title ?? '')) failures.push(`document.title has no «Janitor»: ${JSON.stringify(title)}`)
  if (!/^es\b/i.test(lang ?? '')) failures.push(`document.documentElement.lang is not Spanish: ${JSON.stringify(lang)}`)
  if (!FIRST_SCREEN_RE.test(text ?? '')) {
    failures.push('the first screen (instalar Janitor / error de arranque) never appeared')
  }

  // Paths are accepted (directive #17): the engine lives in ~/.janitor/hermes-agent.
  const withoutPaths = line => line.replace(/\S*[/\\]\S*/g, '')
  const hermes = (text ?? '').split('\n').filter(line => /hermes/i.test(withoutPaths(line)))
  if (hermes.length) failures.push(`visible text mentions Hermes: ${hermes.map(l => JSON.stringify(l.trim())).join(', ')}`)

  return failures
}

async function readScreen(win) {
  return win
    .evaluate(() => ({
      title: document.title,
      lang: document.documentElement.lang,
      text: document.body ? document.body.innerText : ''
    }))
    .catch(error => ({ title: '', lang: '', text: `<no se pudo leer la ventana: ${error.message}>` }))
}

async function main(executable, outDir) {
  const { _electron } = await import('playwright')

  fs.mkdirSync(outDir, { recursive: true })
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'janitor-smoke-'))
  for (const dir of ['home', 'user-data', 'tmp']) fs.mkdirSync(path.join(sandbox, dir), { recursive: true })

  const log = message => {
    const line = `[${new Date().toISOString()}] ${message}`
    console.log(line)
    fs.appendFileSync(path.join(outDir, 'smoke.log'), `${line}\n`)
  }

  let app
  let win
  let screen = { title: '', lang: '', text: '' }
  const failures = []

  const watchdog = setTimeout(() => {
    log(`global timeout (${GLOBAL_TIMEOUT_MS / 1000}s): killing the app`)
    try {
      app?.process()?.kill('SIGKILL')
    } catch {}
    process.exit(3)
  }, GLOBAL_TIMEOUT_MS)

  try {
    log(`launching ${executable} (sandbox ${sandbox})`)
    app = await _electron.launch({
      executablePath: executable,
      args: launchArgs(),
      env: buildSmokeEnv(process.env, sandbox),
      timeout: 120_000
    })

    const proc = app.process()
    proc.stdout?.on('data', d => fs.appendFileSync(path.join(outDir, 'app-stdout.log'), d))
    proc.stderr?.on('data', d => fs.appendFileSync(path.join(outDir, 'app-stderr.log'), d))

    win = await app.firstWindow({ timeout: 120_000 })
    await win.setViewportSize({ width: 1400, height: 900 }).catch(() => {})
    log('first window')

    const deadline = Date.now() + FIRST_SCREEN_TIMEOUT_MS
    do {
      screen = await readScreen(win)
      if (FIRST_SCREEN_RE.test(screen.text)) break
      await new Promise(resolve => setTimeout(resolve, 2000))
    } while (Date.now() < deadline)

    // Let the screen settle so the capture shows it whole.
    await new Promise(resolve => setTimeout(resolve, 3000))
    screen = await readScreen(win)
    failures.push(...checkFirstScreen(screen))
  } catch (error) {
    failures.push(`launch failed: ${error.message.split('\n')[0]}`)
  } finally {
    if (win) {
      await win.screenshot({ path: path.join(outDir, 'primera-pantalla.png') }).catch(error => {
        failures.push(`screenshot failed: ${error.message.split('\n')[0]}`)
      })
    }

    fs.writeFileSync(
      path.join(outDir, 'texto-visible.txt'),
      `title: ${screen.title}\nlang: ${screen.lang}\n\n${screen.text}\n`
    )

    if (app) await Promise.race([app.close().catch(() => {}), new Promise(r => setTimeout(r, 15_000))])
    try {
      app?.process()?.kill('SIGKILL')
    } catch {}
    fs.rmSync(sandbox, { recursive: true, force: true, maxRetries: 3 })
    clearTimeout(watchdog)
  }

  log(`title=${JSON.stringify(screen.title)} lang=${JSON.stringify(screen.lang)}`)
  if (failures.length) {
    for (const failure of failures) log(`FAIL ${failure}`)
    return 1
  }

  log('OK')
  return 0
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [executable, outDir] = process.argv.slice(2)

  if (!executable || !outDir) {
    console.error('usage: smoke-packaged.mjs <app executable> <out dir>')
    process.exit(2)
  }

  process.exit(await main(path.resolve(executable), path.resolve(outDir)))
}
