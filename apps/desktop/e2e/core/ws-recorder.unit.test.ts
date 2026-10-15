import type { Page } from '@playwright/test'
import { expect, test, vi } from 'vitest'

import { reloadWithWebSocketRecorder, type WsRecorder } from './harness'

function recorder(): WsRecorder {
  return {
    sockets: [{ id: 0, url: 'ws://127.0.0.1:1234/api/ws', closed: false }],
    events: [{ socket: 0, type: 'message.complete', sessionId: 'session', seq: 1, payload: {} }],
    sent: [{ socket: 0, method: 'message.send', params: {} }]
  }
}

test('reload retires only old-document sockets and preserves the transcript', async () => {
  const rec = recorder()
  const events = [...rec.events]
  const sent = [...rec.sent]

  const page = { reload: vi.fn(async () => {
    rec.sockets.push(
      { id: 1, url: rec.sockets[0]!.url, closed: false },
      { id: 2, url: rec.sockets[0]!.url, closed: false }
    )
  }) } as unknown as Page

  await reloadWithWebSocketRecorder(page, rec)
  expect(page.reload).toHaveBeenCalledOnce()
  expect(rec.sockets.filter(socket => !socket.closed).map(socket => socket.id)).toEqual([1, 2])
  expect(rec.events).toEqual(events)
  expect(rec.sent).toEqual(sent)
})

test('a failed reload does not declare existing connections closed', async () => {
  const rec = recorder()
  const page = { reload: vi.fn(async () => { throw new Error('navigation failed') }) } as unknown as Page

  await expect(reloadWithWebSocketRecorder(page, rec)).rejects.toThrow('navigation failed')
  expect(rec.sockets[0]!.closed).toBe(false)
})

test('a close during reload stays closed while a new connection remains observable', async () => {
  const rec = recorder()

  const page = { reload: vi.fn(async () => {
    rec.sockets[0]!.closed = true

    rec.sockets.push({ id: 1, url: rec.sockets[0]!.url, closed: false })
  }) } as unknown as Page

  await reloadWithWebSocketRecorder(page, rec)
  expect(rec.sockets.map(socket => socket.closed)).toEqual([true, false])
})
