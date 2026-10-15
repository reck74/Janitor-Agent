import path from 'node:path'

import { runBootstrap as upstreamBootstrap } from '../electron/bootstrap-runner.upstream'
import {
  collectSetupCredentials,
  hasSetupCredentials,
  type JanitorSetupCredentials,
  setupHonchoMode
} from '../janitor/bootstrap-credentials'
export * from '../electron/bootstrap-runner.upstream'

let pending: JanitorSetupCredentials | null = null
let promptOnRetry = false

export async function runBootstrap(options) {
  if (promptOnRetry || !hasSetupCredentials(options.hermesHome)) {
    pending ??= await collectSetupCredentials(options.abortSignal)

    if (!pending) {
      return { ok: false, cancelled: true }
    }
  }

  const values = pending
    ? {
        MINIMAX_API_KEY: pending.minimax,
        HONCHO_API_KEY: pending.mode === 'cloud' ? pending.honcho : '',
        OPENAI_API_KEY: pending.mode === 'local' ? pending.embeddings : '',
        JANITOR_HONCHO_MODE: pending.mode
      }
    : { JANITOR_HONCHO_MODE: setupHonchoMode(options.hermesHome) }

  const previous = Object.fromEntries(Object.keys(values).map(key => [key, process.env[key]]))

  try {
    Object.assign(process.env, values)

    const result = await upstreamBootstrap({
      ...options,
      sourceRepoRoot: path.join(process.resourcesPath, 'janitor-bootstrap')
    })

    if (result.ok) {
      pending = null
      promptOnRetry = false
    } else if (result.failedStage === 'profile') {
      pending = null
      promptOnRetry = true
    }

    return result
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) {
        delete process.env[key]
      } else {
        process.env[key] = value
      }
    }
  }
}
