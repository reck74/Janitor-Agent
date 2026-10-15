import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'

import { app, BrowserWindow, ipcMain } from 'electron'

export interface JanitorSetupCredentials {
  mode: 'local' | 'cloud'
  minimax: string
  honcho: string
  embeddings: string
}

export function validateSetupCredentials(value: unknown): JanitorSetupCredentials {
  if (!value || typeof value !== 'object') {
    throw new Error('Completa la configuración de Janitor.')
  }

  const input = value as Record<string, unknown>

  if (input.mode !== 'local' && input.mode !== 'cloud') {
    throw new Error('Elige Honcho local o cloud.')
  }

  const secret = (key: string): string => {
    const text = typeof input[key] === 'string' ? input[key].trim() : ''

    if (text.length > 8192 || /[\r\n\0]/.test(text)) {
      throw new Error('La clave contiene caracteres no válidos.')
    }

    return text
  }

  const result = {
    mode: input.mode,
    minimax: secret('minimax'),
    honcho: secret('honcho'),
    embeddings: secret('embeddings')
  }

  if (!result.minimax || !(result.mode === 'cloud' ? result.honcho : result.embeddings)) {
    throw new Error('Completa las claves del modo elegido.')
  }

  return result as JanitorSetupCredentials
}

function setupValues(home: string, env: NodeJS.ProcessEnv): (key: string) => string {
  let text = ''

  try {
    text = readFileSync(path.join(home, '.env'), 'utf8')
  } catch {
    /* New profile. */
  }

  return key => {
    if (env[key]?.trim()) {
      return env[key]!.trim()
    }

    const match = new RegExp(`^\\s*(?:export\\s+)?${key}\\s*=\\s*(.*)$`, 'm').exec(text)

    if (!match) {
      return ''
    }

    const value = match[1]
      .trim()
      .replace(/^(['"])(.*)\1$/, '$2')
      .trim()

    return value.startsWith('#') ? '' : value
  }
}

export function setupHonchoMode(home: string, env: NodeJS.ProcessEnv = process.env): 'local' | 'cloud' {
  const value = setupValues(home, env)

  return value('HONCHO_BASE_URL') || !value('HONCHO_API_KEY') ? 'local' : 'cloud'
}

export function hasSetupCredentials(home: string, env: NodeJS.ProcessEnv = process.env): boolean {
  const value = setupValues(home, env)

  return Boolean(
    value('MINIMAX_API_KEY') &&
    (setupHonchoMode(home, env) === 'cloud'
      ? value('HONCHO_API_KEY')
      : value('HONCHO_BASE_URL') && value('OPENAI_API_KEY'))
  )
}

const form = `<!doctype html><html lang="es"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<style>body{background:#151515;color:#eee;font:15px system-ui;margin:30px}h1{font-size:25px;margin-bottom:8px}p{color:#bbb;line-height:1.5}label{display:block;margin:16px 0 6px}input,select{box-sizing:border-box;width:100%;background:#242424;color:#fff;border:1px solid #666;border-radius:6px;padding:11px;font:inherit}button{font:inherit;border:0;border-radius:6px;padding:11px 16px;cursor:pointer}footer{display:flex;gap:12px;justify-content:flex-end;margin-top:26px}#submit{background:#e9b46b;color:#171717}#error{color:#ffaba1;min-height:22px}small{color:#aaa}</style>
<h1>Preparar Janitor Agent</h1><p>Conecta MiniMax y elige dónde guardar la memoria. Las otras integraciones se pueden añadir después.</p>
<form id="setup"><label for="minimax">Clave API de MiniMax</label><input id="minimax" type="password" autocomplete="off" spellcheck="false" required>
<label for="mode">Memoria Honcho</label><select id="mode"><option value="local">Local con Docker</option><option value="cloud">Honcho cloud</option></select>
<div id="local"><label for="embeddings">Clave OpenAI para embeddings de Honcho local</label><input id="embeddings" type="password" autocomplete="off" spellcheck="false"><small>MiniMax sigue siendo el proveedor principal de conversación.</small></div>
<div id="cloud" hidden><label for="honcho">Clave API de Honcho cloud</label><input id="honcho" type="password" autocomplete="off" spellcheck="false"></div>
<p>Docker debe estar instalado, en ejecución y accesible para este usuario. La instalación mostrará cómo recuperarse si falta.</p>
<p id="error" role="alert"></p><footer><button id="cancel" type="button">Cancelar</button><button id="submit" type="submit">Preparar Janitor</button></footer></form>
<script>
const byId=id=>document.getElementById(id);
byId('mode').onchange=()=>{byId('local').hidden=byId('mode').value!=='local';byId('cloud').hidden=byId('mode').value!=='cloud';};
byId('cancel').onclick=()=>window.janitorSetup.submit(null);
byId('setup').onsubmit=async event=>{event.preventDefault();byId('error').textContent='';
try { const result=await window.janitorSetup.submit({mode:byId('mode').value,minimax:byId('minimax').value,honcho:byId('honcho').value,embeddings:byId('embeddings').value});
if(result?.error)byId('error').textContent=result.error; } catch {byId('error').textContent='No se pudo guardar la configuración. Inténtalo de nuevo.';} };
</script></html>`

export async function collectSetupCredentials(signal?: AbortSignal): Promise<JanitorSetupCredentials | null> {
  await app.whenReady()

  if (signal?.aborted) {
    return null
  }

  const channel = `janitor:setup:${randomUUID()}`

  const window = new BrowserWindow({
    width: 520,
    height: 720,
    resizable: false,
    show: false,
    title: 'Configurar Janitor Agent',
    parent: BrowserWindow.getFocusedWindow() || undefined,
    modal: true,
    webPreferences: {
      preload: path.join(process.resourcesPath, 'janitor-setup-preload.cjs'),
      additionalArguments: [`--janitor-setup-channel=${channel}`],
      partition: `janitor-setup-${randomUUID()}`,
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', event => event.preventDefault())

  return new Promise((resolve, reject) => {
    let settled = false

    const finish = (credentials: JanitorSetupCredentials | null, error?: Error) => {
      if (settled) {
        return
      }

      settled = true
      ipcMain.removeHandler(channel)
      signal?.removeEventListener('abort', cancel)

      if (error) {
        reject(error)
      } else {
        resolve(credentials)
      }

      if (!window.isDestroyed()) {
        window.destroy()
      }
    }

    const cancel = () => finish(null)
    signal?.addEventListener('abort', cancel, { once: true })
    ipcMain.handle(channel, (event, input: unknown) => {
      if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
        return { error: 'Invalid setup window' }
      }

      if (input === null) {
        finish(null)

        return {}
      }

      try {
        finish(validateSetupCredentials(input))

        return {}
      } catch (error) {
        return { error: error.message }
      }
    })
    window.once('closed', cancel)
    window.once('ready-to-show', () => window.show())
    window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(form)}`).catch(error => finish(null, error))
  })
}
