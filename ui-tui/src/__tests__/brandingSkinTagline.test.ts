import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { Banner, SessionPanel } from '../components/branding.js'
import { DEFAULT_THEME, fromSkin, type Theme } from '../theme.js'
import type { SessionInfo } from '../types.js'

// A skin's `branding.tagline` / `branding.vendor` replace the stock banner
// tagline tiers and the session-panel vendor label; skins that don't set
// them keep the stock text.

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

async function render(node: React.ReactElement, columns: number): Promise<string> {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns, isTTY: false, rows: 40 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })

  let captured = ''
  stdout.on('data', chunk => {
    captured += chunk.toString()
  })

  const instance = renderSync(node, {
    patchConsole: false,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as NodeJS.ReadStream,
    stdout: stdout as NodeJS.WriteStream
  })

  try {
    await delay(20)

    // eslint-disable-next-line no-control-regex
    return captured.replace(/\u001b\[[0-9;]*m/g, '')
  } finally {
    instance.unmount()
    instance.cleanup()
  }
}

const banner = (t: Theme, columns: number) => render(React.createElement(Banner, { maxWidth: columns, t }), columns)

const info: SessionInfo = { mcp_servers: [], model: 'vendor/test-model', skills: {}, tools: {} }

describe('skin-driven banner tagline', () => {
  const skinned = fromSkin({}, { agent_name: 'Test Operator', tagline: 'Custom Tagline', vendor: 'Acme' })

  it('maps branding.tagline / branding.vendor onto the theme brand', () => {
    expect(skinned.brand.tagline).toBe('Custom Tagline')
    expect(skinned.brand.vendor).toBe('Acme')
  })

  it('uses the skin tagline on wide and mid banners and the vendor on tiny ones', async () => {
    expect(await banner(skinned, 120)).toContain('Custom Tagline')
    expect(await banner(skinned, 58)).toContain('Custom Tagline')
    expect(await banner(skinned, 50)).toContain('Custom Tagline')

    const tiny = await banner(skinned, 40)

    expect(tiny).toContain('Acme')
    expect(tiny).not.toContain('Nous Research')
  })

  it('labels the session panel with the skin vendor', async () => {
    const frame = await render(React.createElement(SessionPanel, { info, sid: 'test', t: skinned }), 100)

    expect(frame).toContain('test-model · Acme')
    expect(frame).not.toContain('Nous Research')
  })

  it('keeps the stock tagline when the skin sets none', async () => {
    const plain = fromSkin({}, { agent_name: 'Test Operator' })

    expect(plain.brand.tagline).toBeUndefined()
    expect(await banner(plain, 120)).toContain('Messenger of the Digital Gods')
    expect(await banner(DEFAULT_THEME, 120)).toContain('Messenger of the Digital Gods')
  })
})
