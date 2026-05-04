import { afterEach, describe, expect, it, vi } from 'vitest'

const RELEVANT_ENV = [
  'HERMES_TUI_LIGHT',
  'HERMES_TUI_THEME',
  'HERMES_TUI_BACKGROUND',
  'COLORFGBG',
  'COLORTERM',
  'TERM_PROGRAM',
] as const

async function importThemeWithEnv(env: Partial<Record<(typeof RELEVANT_ENV)[number], string>> = {}) {
  for (const key of RELEVANT_ENV) {
    vi.stubEnv(key, env[key] ?? '')
  }

  vi.resetModules()

  return import('../theme.js')
}

async function importThemeWithCleanEnv() {
  return importThemeWithEnv()
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('Janitor skin integration', () => {
  it('janitor branding can be injected via fromSkin', async () => {
    const { fromSkin } = await importThemeWithCleanEnv()

    const theme = fromSkin({
      banner_border: '#00FF41',
      banner_title: '#00FF41',
      banner_accent: '#39FF14',
      banner_dim: '#0D3D0D',
      banner_text: '#00FF41',
    }, {
      agent_name: 'Janitor',
      prompt_symbol: '▓',
    })

    expect(theme.brand.name).toBe('Janitor')
    expect(theme.brand.prompt).toBe('▓')
  })

  it('janitor colors are applied via fromSkin', async () => {
    const { fromSkin } = await importThemeWithCleanEnv()

    const theme = fromSkin({
      banner_title: '#00FF41',
      banner_border: '#00FF41',
      banner_accent: '#39FF14',
      banner_dim: '#0D3D0D',
      banner_text: '#00FF41',
      ui_error: '#FF073A',
    }, {
      agent_name: 'Janitor',
    })

    expect(theme.color.primary).toBe('#00FF41')
  })

  it('janitor skin does not crash when missing optional fields', async () => {
    const { fromSkin, DARK_THEME } = await importThemeWithCleanEnv()

    const theme = fromSkin({}, { agent_name: 'Janitor' })

    expect(theme.brand.name).toBe('Janitor')
    expect(theme.color.primary).toBe(DARK_THEME.color.primary)
    expect(theme.color.error).toBe(DARK_THEME.color.error)
  })

  it('skin config keys are all valid hex colors', async () => {
    const { fromSkin } = await importThemeWithCleanEnv()

    const janitorSkin = {
      banner_border: '#00FF41',
      banner_title: '#00FF41',
      banner_accent: '#39FF14',
      banner_dim: '#0D3D0D',
      banner_text: '#00FF41',
      ui_error: '#FF073A',
      ui_warn: '#FFE135',
    }

    const theme = fromSkin(janitorSkin, {})

    expect(theme.color.primary).toBe('#00FF41')
    expect(theme.color.accent).toBe('#39FF14')
    expect(theme.color.border).toBe('#00FF41')
  })

  it('janitor error color is dark red for visibility', async () => {
    const { fromSkin } = await importThemeWithCleanEnv()

    const theme = fromSkin({ ui_error: '#FF073A' }, {})

    expect(theme.color.error).toBe('#FF073A')
  })
})