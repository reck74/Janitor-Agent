import { expect, it, vi } from 'vitest'

import { createGatewayEventHandler } from '../app/createGatewayEventHandler.js'
import { resetUiState } from '../app/uiStore.js'

function buildCtx(_messages: unknown[]) {
  resetUiState()

  return {
    composer: { setInput: vi.fn() },
    gateway: { gw: { request: vi.fn(async () => null) }, rpc: vi.fn(async () => null) },
    session: { STARTUP_RESUME_ID: '', colsRef: { current: 80 }, newSession: vi.fn(),
      resumeById: vi.fn(), resetSession: vi.fn(), setCatalog: vi.fn() },
    submission: { submitRef: { current: vi.fn() } },
    system: { bellOnComplete: false, sys: vi.fn() },
    transcript: { appendMessage: vi.fn(), panel: vi.fn(), setHistoryItems: vi.fn() },
    voice: { setProcessing: vi.fn(), setRecording: vi.fn(), setVoiceEnabled: vi.fn() }
  } as any
}

  it('does not auto-create after an explicit selection while config is loading', async () => {
    const ctx = buildCtx([])
    const config = Promise.withResolvers<any>()
    let selected = false
    ctx.session.hasSessionSelection = () => selected
    ctx.gateway.rpc = vi.fn(async (method: string) => (method === 'config.get' ? config.promise : null))
    createGatewayEventHandler(ctx)({ payload: {}, type: 'gateway.ready' } as any)
    selected = true
    config.resolve({ config: { display: { tui_auto_resume_recent: false } } })
    await config.promise
    await new Promise<void>(resolve => setImmediate(resolve))
    expect(ctx.session.newSession).not.toHaveBeenCalled()
    expect(ctx.session.resumeById).not.toHaveBeenCalled()
  })

