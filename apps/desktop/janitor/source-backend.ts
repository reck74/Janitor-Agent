import { existsSync } from 'node:fs'
import path from 'node:path'

import { buildDesktopBackendEnv } from '../electron/backend-env'
import { execProbe, PROBE_TIMEOUT_MS } from '../electron/backend-probes'
import {
  type SourceBackend,
  createSourcePythonBackend as upstreamSourceBackend
} from '../electron/source-backend.upstream'
export type { SourceBackend } from '../electron/source-backend.upstream'

export function createSourcePythonBackend(root, python, args, options = {}): SourceBackend | null {
  if (!existsSync(path.join(root, 'janitor_cli.py'))) {
    return null
  }

  const backend = upstreamSourceBackend(root, python, args, options)

  if (backend) {
    backend.args = ['-m', 'janitor_cli', ...args]
  }

  return backend
}

export async function resolveSourceInstallationBackend(root, args, options = {}): Promise<SourceBackend | null> {
  const command = path.join(root, 'scripts', 'janitor')

  if (!existsSync(path.join(root, 'janitor_cli.py')) || !existsSync(command)) {
    return null
  }

  const env = buildDesktopBackendEnv({ currentEnv: options['env'] ?? process.env })

  try {
    await execProbe(command, ['--version'], { cwd: root, env, stdio: 'ignore', timeout: PROBE_TIMEOUT_MS })
  } catch {
    return null
  }

  return {
    kind: 'command',
    label: `Janitor at ${root}`,
    command,
    args: [...args],
    env,
    root,
    bootstrap: false,
    shell: false,
    local: 'installed'
  }
}
