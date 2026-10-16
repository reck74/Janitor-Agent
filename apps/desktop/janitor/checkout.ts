import { spawn } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import metadata from '../../../janitor_ext/release.json'
import { collectRelaunchArgs } from '../electron/updater-process'
import type { CheckoutStrategy, CheckoutStrategyDeps } from '../electron/updater/checkout.upstream'

import {
  acquireLock,
  assertOwnedAppImage,
  fetchRelease,
  isNewer,
  prepareUpdate,
  recordPrepared,
  releaseLock,
  selectRelease
} from './update.mjs'

export function createCheckoutStrategy(deps: CheckoutStrategyDeps): CheckoutStrategy {
  let applying = false

  return {
    mechanism: 'posix-handoff',
    async check() {
      try {
        assertOwnedAppImage(process.env.APPIMAGE)
      } catch (error) {
        return {
          supported: false,
          mechanism: 'posix-handoff',
          reason: 'external-package-owner',
          message: error.message
        }
      }

      try {
        const selection = selectRelease(await fetchRelease())

        return {
          supported: true,
          mechanism: 'posix-handoff',
          channelSelectable: false,
          channel: 'stable',
          currentVersion: metadata.janitorVersion,
          latestTag: `v${selection.version}`,
          updateAvailable: isNewer(selection.version, metadata.janitorVersion),
          fetchedAt: Date.now()
        }
      } catch (error) {
        return {
          supported: true,
          mechanism: 'posix-handoff',
          error: 'fetch-failed',
          message: error.message,
          currentVersion: metadata.janitorVersion,
          fetchedAt: Date.now()
        }
      }
    },
    async apply() {
      if (applying) {
        return { ok: false, error: 'update-already-running' }
      }

      applying = true

      let lock,
        prepared,
        worker,
        workerPath,
        planPath,
        stopped = false

      try {
        const target = process.env.APPIMAGE
        assertOwnedAppImage(target)
        const selection = selectRelease(await fetchRelease())

        if (!isNewer(selection.version, metadata.janitorVersion)) {
          return { ok: true, message: 'Janitor Desktop is current.' }
        }

        lock = acquireLock(deps.hermesHome)
        deps.emitUpdateProgress({
          stage: 'download',
          message: 'Downloading and verifying Janitor Desktop…',
          percent: null
        })
        prepared = await prepareUpdate({
          selection,
          target,
          onDirectory: progress => recordPrepared(lock, progress, 'downloading')
        })
        recordPrepared(lock, prepared)
        const temporary = path.join(deps.hermesHome, 'tmp')
        mkdirSync(temporary, { recursive: true, mode: 0o700 })
        workerPath = path.join(temporary, `janitor-update-${lock.token}.mjs`)
        planPath = path.join(temporary, `janitor-update-${lock.token}.json`)
        cpSync(path.join(process.resourcesPath, 'janitor-update.mjs'), workerPath)
        writeFileSync(
          planPath,
          JSON.stringify({
            ...prepared,
            lock,
            parentPid: process.pid,
            runtimeRoot: deps.resolveUpdateRoot(),
            home: deps.hermesHome,
            noGatewayRestart: deps.remoteGatewayActive(),
            args: collectRelaunchArgs(process.argv.slice(1))
          }),
          { mode: 0o600 }
        )
        worker = spawn(process.execPath, [workerPath, '--apply', planPath], {
          detached: true,
          stdio: 'ignore',
          env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }
        })
        let failure: Error | null = null
        worker.once('error', error => {
          failure = error
        })
        worker.once('exit', code => {
          failure = new Error(`Janitor update worker exited (${code})`)
        })

        for (let attempt = 0; !existsSync(path.join(lock.directory, 'ready')); attempt++) {
          if (failure) {
            throw failure
          }

          if (attempt === 100) {
            throw new Error('Janitor update worker did not become ready')
          }

          await new Promise(resolve => setTimeout(resolve, 100))
        }

        await deps.preflightStateDb(deps.hermesHome, deps.rememberLog)
        await deps.stopBackendsForUpdate()
        stopped = true
        deps.emitUpdateProgress({
          stage: 'handoff',
          message: 'Updating Janitor. Desktop will reopen after both updates succeed.',
          percent: null
        })
        deps.markQuittingForHandoff()
        worker.unref()
        deps.quit()

        return { ok: true, handedOff: true, mechanism: 'posix-handoff' }
      } catch (error) {
        worker?.kill()

        if (workerPath) {
          rmSync(workerPath, { force: true })
        }

        if (planPath) {
          rmSync(planPath, { force: true })
        }

        if (prepared) {
          rmSync(prepared.directory, { recursive: true, force: true })
        }

        if (lock) {
          releaseLock(lock)
        }

        if (stopped) {
          try {
            await deps.startHermes()
          } catch (recovery) {
            deps.rememberLog(recovery.message)
          }
        }

        deps.emitUpdateProgress({ stage: 'error', message: error.message, percent: null })

        return { ok: false, mechanism: 'posix-handoff', error: 'janitor-update-failed', message: error.message }
      } finally {
        applying = false
      }
    }
  }
}
