/**
 * Install Janitor user themes on first launch.
 *
 * Idempotent: writes a sentinel key to localStorage so re-runs do nothing.
 * Should be invoked synchronously before `createRoot().render()` so the
 * themes are visible to the boot-time paint (see `context.tsx:261-268`).
 */

import './overrides.css'

import { persistString } from '@/lib/storage'
import { installUserTheme } from '@/themes/user-themes'

import { JANITOR_DEFAULT_SKIN, JANITOR_THEMES } from './theme-presets'

const SKIN_KEY = 'hermes-desktop-theme-v2'
const MODE_KEY = 'hermes-desktop-mode-v1'
const INSTALLED_KEY = 'janitor-desktop-themes-installed-v1'

/**
 * Install every Janitor theme into the user-theme registry and, if the user
 * hasn't chosen a skin yet, apply the Janitor default + dark mode.
 *
 * Safe to call repeatedly: after the first successful run, this is a no-op.
 * Safe in non-browser contexts (returns immediately when `window` is undefined).
 */
export function installJanitorThemes(): void {
  if (typeof window === 'undefined') {
    return
  }

  if (window.localStorage.getItem(INSTALLED_KEY)) {
    return
  }

  let installed = 0

  for (const theme of JANITOR_THEMES) {
    try {
      installUserTheme(theme)
      installed++
    } catch (err) {
      console.warn(`[janitor] failed to install theme ${theme.name}:`, err)
    }
  }

  if (installed > 0) {
    if (!window.localStorage.getItem(SKIN_KEY)) {
      persistString(SKIN_KEY, JANITOR_DEFAULT_SKIN)
      persistString(MODE_KEY, 'dark')
    }

    window.localStorage.setItem(INSTALLED_KEY, String(Date.now()))
  }
}