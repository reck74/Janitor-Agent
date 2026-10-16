import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React, { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { turnController } from '../app/turnController.js'
import { resetTurnState } from '../app/turnStore.js'
import { getUiState, resetUiState } from '../app/uiStore.js'
import { useSessionLifecycle } from '../app/useSessionLifecycle.js'

function mountLifecycle(request: (method: string, params: any) => Promise<any>) {
  let api: null | ReturnType<typeof useSessionLifecycle> = null

  function Probe() {
    const lifecycle = useSessionLifecycle({
      colsRef: { current: 80 },
      composerActions: { setComposerTokens: vi.fn() } as any,
      gw: { request } as any,
      rpc: request,
      panel: vi.fn(),
      scrollRef: { current: null },
      setHistoryItems: vi.fn(),
      setLastUserMsg: vi.fn(),
      setSessionStartedAt: vi.fn(),
      setStickyPrompt: vi.fn(),
      setVoiceProcessing: vi.fn(),
      setVoiceRecording: vi.fn(),
      sys: vi.fn()
    })

    useEffect(() => {
      api = lifecycle
    })

    return null
  }

  const stream = () => Object.assign(new PassThrough(), { columns: 80, isTTY: false, rows: 24 })

  const app = renderSync(React.createElement(Probe), {
    patchConsole: false,
    stderr: stream() as unknown as NodeJS.WriteStream,
    stdin: stream() as unknown as NodeJS.ReadStream,
    stdout: stream() as unknown as NodeJS.WriteStream
  })

  return { get: () => api!, close: () => app.unmount() }
}

describe('session navigation during startup', () => {
  beforeEach(() => {
    resetUiState()
    resetTurnState()
    turnController.fullReset()
  })

  it('a late startup create cannot replace a completed explicit resume', async () => {
    const created = Promise.withResolvers<any>()

    const request = vi.fn(async (method: string) => {
      if (method === 'setup.status') {return { provider_configured: true }}

      if (method === 'session.create') {return created.promise}

      if (method === 'session.resume') {return { session_id: 'chosen', stored_session_id: 'durable', messages: [] }}

      return {}
    })

    const api = mountLifecycle(request)

    try {
      await vi.waitFor(() => expect(api.get()).toBeTruthy())
      const startup = api.get().newSession()
      await vi.waitFor(() => expect(request).toHaveBeenCalledWith('session.create', expect.anything()))
      await api.get().resumeById('durable')
      expect(getUiState().sid).toBe('chosen')
      created.resolve({ session_id: 'startup', stored_session_id: 'discarded' })
      await startup
      expect(getUiState().sid).toBe('chosen')
      expect(getUiState().storedSid).toBe('durable')
      expect(request).toHaveBeenCalledWith('session.close', { session_id: 'startup' })
    } finally {
      api.close()
    }
  })

  it('the latest resume wins even when an older request finishes last', async () => {
    const older = Promise.withResolvers<any>()

    const request = vi.fn(async (method: string, params: any) => {
      if (method === 'setup.status') {return { provider_configured: true }}

      if (method === 'session.resume' && params.session_id === 'old') {return older.promise}

      if (method === 'session.resume') {return { session_id: 'new', stored_session_id: 'new', messages: [] }}

      return {}
    })

    const api = mountLifecycle(request)

    try {
      await vi.waitFor(() => expect(api.get()).toBeTruthy())
      const first = api.get().resumeById('old')
      expect(api.get().hasSessionSelection()).toBe(true)
      await vi.waitFor(() =>
        expect(request).toHaveBeenCalledWith('session.resume', expect.objectContaining({ session_id: 'old' }))
      )
      await api.get().resumeById('new')
      older.resolve({ session_id: 'old', stored_session_id: 'old', messages: [] })
      await first
      expect(getUiState().sid).toBe('new')
    } finally {
      api.close()
    }
  })
})
