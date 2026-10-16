import { readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { app, dialog } from 'electron'

import { resolveDesktopHermesHome } from '../electron/data-paths'
import { recoverInterruptedUpdate } from '../janitor/update.mjs'

// Resolve the fork home before Electron reads configuration or acquires its lock.
const home = resolveDesktopHermesHome({
  home: os.homedir(),
  env: {
    ...process.env,
    HERMES_HOME: process.env.HERMES_HOME || process.env.JANITOR_HOME || path.join(os.homedir(), '.janitor')
  }
})

process.env.HERMES_HOME = home
process.env.JANITOR_HOME = home
process.env.HERMES_DESKTOP_APP_NAME ??= 'Janitor Agent'
// The update worker only accepts the new version after its main renderer has
// loaded. Preserve the challenge across the upstream Linux launcher handoff,
// then remove it as soon as a native window exists, before starting its backend.
const readyPath = process.env.JANITOR_UPDATE_READY_PATH
const readyToken = process.env.JANITOR_UPDATE_READY_TOKEN

if (readyPath && readyToken) {
  app.on('browser-window-created', (_, window) => {
    delete process.env.JANITOR_UPDATE_READY_PATH
    delete process.env.JANITOR_UPDATE_READY_TOKEN
    window.webContents.once('did-finish-load', () => {
      const url = window.webContents.getURL()

      if (!url.startsWith('file:') || !url.endsWith('/index.html')) {
        return
      }

      const confirm = async () => {
        if (window.isDestroyed()) {
          return
        }

        const rendered = await window.webContents.executeJavaScript(
          "document.readyState === 'complete' && !!document.getElementById('root')?.childElementCount"
        )

        if (!rendered) {
          setTimeout(() => void confirm().catch(() => {}), 100)

          return
        }

        const pending = `${readyPath}.${process.pid}.tmp`
        writeFileSync(
          pending,
          JSON.stringify({ token: readyToken, product: app.getName(), version: app.getVersion(), pid: process.pid }),
          { mode: 0o600, flag: 'wx' }
        )
        renameSync(pending, readyPath)
      }

      void confirm().catch(() => {})
    })
  })
}

await import('../electron/entry.upstream')

void app.whenReady().then(async () => {
  const resultPath = path.join(home, '.janitor-desktop-update-result.json')

  try {
    recoverInterruptedUpdate(home)
    const result = JSON.parse(readFileSync(resultPath, 'utf8'))

    if (!result.ok) {
      await dialog.showMessageBox({
        type: 'warning',
        title: 'Janitor update needs attention',
        message:
          result.runtimeUpdated && result.desktopUpdated
            ? 'The update was interrupted after both components were installed.'
            : result.runtimeUpdated
              ? 'The runtime updated, but the Desktop update did not complete.'
              : 'The Janitor update did not complete.',
        detail: result.error || 'Retry the update from Settings.',
        buttons: ['OK']
      })
    }

    rmSync(resultPath, { force: true })
  } catch {
    /* No previous transaction result. */
  }
})
