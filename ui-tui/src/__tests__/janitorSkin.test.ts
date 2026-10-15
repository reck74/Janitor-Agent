import { readFileSync } from 'node:fs'

import type { SkinBranding, SkinColors } from '@hermes/shared/skin'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { parse } from 'yaml'

const RELEVANT_ENV = [
  'HERMES_TUI_LIGHT',
  'HERMES_TUI_THEME',
  'HERMES_TUI_BACKGROUND',
  'COLORFGBG',
  'COLORTERM',
  'TERM_PROGRAM'
] as const

const skin = parse(readFileSync(new URL('../../../assets/janitor/sentry-janitor.yaml', import.meta.url), 'utf8')) as {
  colors: SkinColors
  branding: SkinBranding
  banner_logo: string
  banner_hero: string
  tool_prefix: string
}

async function importThemeWithEnv(env: Partial<Record<(typeof RELEVANT_ENV)[number], string>> = {}) {
  for (const key of RELEVANT_ENV) {vi.stubEnv(key, env[key] ?? '')}
  vi.resetModules()

  return import('../theme.js')
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('Janitor skin integration (AGENTS.md #4)', () => {
  it('loads Janitor identity and art from the shipped skin', async () => {
    const { fromSkin } = await importThemeWithEnv()
    const theme = fromSkin(skin.colors, skin.branding, skin.banner_logo, skin.banner_hero, skin.tool_prefix)
    expect(theme.brand.name).toBe('THE JANITOR') // AGENTS.md #12: wrapper/skin output
    expect(theme.brand.icon).toBe('🛠')
    expect(theme.brand.prompt).toBe('❯')
    expect(theme.brand.tool).toBe('│')
    expect(theme.brand.welcome).toBe(skin.branding.welcome)
    expect(theme.bannerLogo).toBe(skin.banner_logo)
    expect(theme.bannerHero).toBe(skin.banner_hero)
  })
  it('applies the shipped Sentry palette through fromSkin', async () => {
    const { fromSkin } = await importThemeWithEnv()
    const { color } = fromSkin(skin.colors, skin.branding)
    expect(color.primary).toBe(skin.colors.ui_primary)
    expect(color.border).toBe(skin.colors.ui_border)
    expect(color.error).toBe(skin.colors.ui_error)
    expect(color.completionBg).toBe(skin.colors.background)
  })
  it('falls back to the base theme for omitted optional skin fields', async () => {
    const { fromSkin, DARK_THEME } = await importThemeWithEnv()
    const theme = fromSkin({}, { agent_name: 'Janitor' })
    expect(theme.brand.name).toBe('Janitor')
    expect(theme.color).toEqual(DARK_THEME.color)
  })
  it('keeps upstream identity and palettes available without Janitor injection', async () => {
    const { BRAND, DARK_THEME, LIGHT_THEME, DEFAULT_THEME, fromSkin } = await importThemeWithEnv()
    expect(DEFAULT_THEME).toBe(DARK_THEME)
    expect(DARK_THEME.brand).toBe(BRAND)
    expect(LIGHT_THEME.brand).toBe(BRAND)
    expect(fromSkin({}, {}).brand.name).toBe(BRAND.name)
    expect(fromSkin(skin.colors, skin.branding).brand.name).not.toBe(BRAND.name)
  })
  it('uses authored dark canvas even on a light terminal', async () => {
    const { fromSkin, skinIsLight, contrastRatio } = await importThemeWithEnv({ HERMES_TUI_BACKGROUND: '#ffffff' })
    expect(skinIsLight(skin.colors)).toBe(false)
    const { color } = fromSkin(skin.colors, skin.branding)
    expect(color.primary).toBe(skin.colors.ui_primary)
    expect(contrastRatio(color.text, skin.colors.background!)).toBeGreaterThanOrEqual(4.5)
  })
})
