import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { EventEmitter } from 'node:events'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const native = vi.hoisted(() => ({ handlers: new Map(), windows: [] }))
vi.mock('electron', () => ({
  app: { whenReady: async () => {} },
  ipcMain: { handle: (name, handler) => native.handlers.set(name, handler), removeHandler: name => native.handlers.delete(name) },
  BrowserWindow: class extends EventEmitter {
    static getFocusedWindow() { return null }
    constructor(options) { super(); this.options = options; this.destroyed = false;
      this.webContents = { mainFrame: {}, setWindowOpenHandler: handler => { this.openHandler = handler }, on: () => {} }; native.windows.push(this) }
    async loadURL(url) { this.url = url; queueMicrotask(() => this.emit('ready-to-show')) }
    show() { this.shown = true }
    isDestroyed() { return this.destroyed }
    destroy() { this.destroyed = true; this.emit('closed') }
  }
}))
import { collectSetupCredentials, hasSetupCredentials, setupHonchoMode, validateSetupCredentials } from '../janitor/bootstrap-credentials'
const descriptor = Object.getOwnPropertyDescriptor(process, 'resourcesPath')
beforeAll(() => Object.defineProperty(process, 'resourcesPath', { configurable: true, value: '/fixture/resources' }))
afterAll(() => descriptor ? Object.defineProperty(process, 'resourcesPath', descriptor) : delete process.resourcesPath)
afterEach(() => { native.handlers.clear(); native.windows.splice(0) })

describe('Janitor setup credentials', () => {
  it('requires only keys for the selected Honcho mode and rejects multiline secrets', () => {
    expect(validateSetupCredentials({ mode: 'local', minimax: ' mm ', embeddings: 'embedding' })).toMatchObject({ minimax: 'mm', mode: 'local' })
    expect(validateSetupCredentials({ mode: 'cloud', minimax: 'mm', honcho: 'cloud' })).toMatchObject({ honcho: 'cloud', mode: 'cloud' })
    expect(() => validateSetupCredentials({ mode: 'local', minimax: 'mm' })).toThrow(/claves/)
    expect(() => validateSetupCredentials({ mode: 'cloud', minimax: 'mm\nSECRET=bad', honcho: 'cloud' })).toThrow(/caracteres/)
  })
  it('does not mistake empty quoted values for a completed profile', () => {
    const home = mkdtempSync(path.join(os.tmpdir(), 'janitor-setup-test-'))
    try {
      writeFileSync(path.join(home, '.env'), 'MINIMAX_API_KEY=""\nHONCHO_API_KEY=cloud\n')
      expect(hasSetupCredentials(home, {})).toBe(false)
      expect(hasSetupCredentials(home, { MINIMAX_API_KEY: 'mm', HONCHO_API_KEY: 'cloud' })).toBe(true)
      expect(setupHonchoMode(home, { HONCHO_API_KEY: 'cloud' })).toBe('cloud')
      expect(setupHonchoMode(home, { HONCHO_API_KEY: 'cloud', HONCHO_BASE_URL: 'http://127.0.0.1:1973' })).toBe('local')
      expect(hasSetupCredentials(home, { MINIMAX_API_KEY: 'mm', HONCHO_BASE_URL: 'http://127.0.0.1:1973', OPENAI_API_KEY: 'embedding' })).toBe(true)
    } finally { rmSync(home, { recursive: true, force: true }) }
  })
  it('uses an isolated sandboxed window and accepts credentials only from its main frame', async () => {
    const waiting = collectSetupCredentials(); await Promise.resolve()
    const window = native.windows[0], [channel, handler] = [...native.handlers][0]
    expect(window.options.webPreferences).toMatchObject({ sandbox: true, contextIsolation: true, nodeIntegration: false })
    expect(window.options.webPreferences.partition).not.toMatch(/^persist:/)
    expect(window.options.webPreferences.additionalArguments).toEqual([`--janitor-setup-channel=${channel}`])
    const credentials = { mode: 'cloud', minimax: 'secret-mm', honcho: 'secret-cloud' }
    expect(handler({ sender: {}, senderFrame: {} }, credentials)).toMatchObject({ error: 'Invalid setup window' })
    expect(native.handlers.has(channel)).toBe(true)
    handler({ sender: window.webContents, senderFrame: window.webContents.mainFrame }, credentials)
    expect(await waiting).toMatchObject(credentials)
    expect(native.handlers.size).toBe(0)
    expect(window.url).not.toContain('secret-mm')
    expect(window.destroyed).toBe(true)
  })
  it('cancels without persisting or leaving an IPC handler behind', async () => {
    const controller = new AbortController(), waiting = collectSetupCredentials(controller.signal)
    await Promise.resolve(); controller.abort()
    expect(await waiting).toBe(null)
    expect(native.handlers.size).toBe(0)
    expect(native.windows[0].destroyed).toBe(true)
  })
})
