/**
 * Janitor desktop theme presets.
 *
 * Two skins (dark + light) registered as USER themes — they ride the existing
 * `installUserTheme()` pipeline, so they show up everywhere built-ins do
 * (Appearance grid, /skin picker, Cmd-K palette) without per-surface wiring.
 *
 * Naming convention: skins use a single `name` (e.g. `janitor-dark`). The
 * light/dark switch is handled by `darkColors` per the upstream contract
 * (`colors` = light palette, `darkColors` = hand-tuned dark palette).
 *
 * The Janitor palette is pulled from the wireframe (`.plans/janitor_theme_wireframe/`):
 *   - Background: deep blue-black (#020A0C)
 *   - Brand: lime green (#B6FF5C)
 *   - Accent: diagnostic cyan (#00D7E8)
 *   - Hairlines: cold blue-grey (#24383E / #34495A)
 *   - Foreground: bone (#D7D7C9)
 *   - Veto: red (#FF3B1F)
 */

import type { DesktopTheme, DesktopThemeColors } from '@/themes/types'

// ─── Color palettes ──────────────────────────────────────────────────────────

const JANITOR_LIGHT_COLORS: DesktopThemeColors = {
  background: '#F4F6F7',
  foreground: '#020A0C',
  card: '#FFFFFF',
  cardForeground: '#020A0C',
  muted: '#E6EAEC',
  mutedForeground: '#657178',
  popover: '#FFFFFF',
  popoverForeground: '#020A0C',
  primary: '#8AE51E',
  primaryForeground: '#020A0C',
  secondary: '#D7D7C9',
  secondaryForeground: '#020A0C',
  accent: '#00A8B8',
  accentForeground: '#FFFFFF',
  border: '#9EA7A4',
  input: '#D7D7C9',
  ring: '#8AE51E',
  midground: '#8AE51E',
  composerRing: '#8AE51E',
  destructive: '#C72E1A',
  destructiveForeground: '#FFFFFF',
  sidebarBackground: '#E6EAEC',
  sidebarBorder: '#9EA7A4',
  userBubble: '#E6EAEC',
  userBubbleBorder: '#9EA7A4'
}

const JANITOR_DARK_COLORS: DesktopThemeColors = {
  background: '#020A0C',
  foreground: '#D7D7C9',
  card: '#0C1D21',
  cardForeground: '#D7D7C9',
  muted: '#061316',
  mutedForeground: '#9EA7A4',
  popover: '#0C1D21',
  popoverForeground: '#D7D7C9',
  primary: '#B6FF5C',
  primaryForeground: '#020A0C',
  secondary: '#34495A',
  secondaryForeground: '#D7D7C9',
  accent: '#00D7E8',
  accentForeground: '#020A0C',
  border: '#24383E',
  input: '#34495A',
  ring: '#B6FF5C',
  midground: '#B6FF5C',
  composerRing: '#B6FF5C',
  destructive: '#FF3B1F',
  destructiveForeground: '#FFFFFF',
  sidebarBackground: '#061316',
  sidebarBorder: '#24383E',
  userBubble: '#0C1D21',
  userBubbleBorder: '#34495A'
}

// ─── Typography ──────────────────────────────────────────────────────────────

const JANITOR_TYPOGRAPHY = {
  fontSans: '"Cascadia Code", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace',
  fontMono: '"Cascadia Code", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace'
}

// ─── Themes ──────────────────────────────────────────────────────────────────
//
// `name` is the upstream-resolvable slug. We expose a single "janitor" skin;
// light/dark is selected via the user's mode preference (the ThemeProvider
// picks `colors` vs `darkColors` based on `mode`).

export const janitorTheme: DesktopTheme = {
  name: 'janitor',
  label: 'Janitor',
  description: 'Industrial green-lime theme — DevSecOps by default',
  colors: JANITOR_LIGHT_COLORS,
  darkColors: JANITOR_DARK_COLORS,
  typography: JANITOR_TYPOGRAPHY
}

export const JANITOR_THEMES: DesktopTheme[] = [janitorTheme]

/** Default skin applied on first Janitor launch. */
export const JANITOR_DEFAULT_SKIN = 'janitor'