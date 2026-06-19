import { beforeEach, describe, expect, it } from 'vitest'

import { $userThemes, listAllThemes, resolveTheme } from '@/themes/user-themes'

import { installJanitorThemes } from './install-themes'
import { JANITOR_DEFAULT_SKIN, janitorTheme } from './theme-presets'

const SKIN_KEY = 'hermes-desktop-theme-v2'
const MODE_KEY = 'hermes-desktop-mode-v1'
const INSTALLED_KEY = 'janitor-desktop-themes-installed-v1'

describe('installJanitorThemes', () => {
  beforeEach(() => {
    window.localStorage.clear()
    $userThemes.set({})
  })

  it('registers the janitor theme into the user-themes registry', () => {
    installJanitorThemes()

    expect(resolveTheme(janitorTheme.name)).toBeDefined()
    expect(resolveTheme(janitorTheme.name)?.name).toBe(janitorTheme.name)
    expect(listAllThemes().map(t => t.name)).toContain(janitorTheme.name)
  })

  it('writes the installed sentinel so subsequent calls are a no-op', () => {
    installJanitorThemes()
    const sentinel = window.localStorage.getItem(INSTALLED_KEY)

    expect(sentinel).not.toBeNull()

    // Mutate the registry out-of-band; a second call must not re-install.
    $userThemes.set({})

    installJanitorThemes()

    // If re-installation had happened, the registry would have been repopulated.
    expect(Object.keys($userThemes.get())).toEqual([])
  })

  it('applies the janitor default skin + dark mode when no skin is set yet', () => {
    installJanitorThemes()

    expect(window.localStorage.getItem(SKIN_KEY)).toBe(JANITOR_DEFAULT_SKIN)
    expect(window.localStorage.getItem(MODE_KEY)).toBe('dark')
  })

  it('does not overwrite an existing user skin choice', () => {
    window.localStorage.setItem(SKIN_KEY, 'slate')
    window.localStorage.setItem(MODE_KEY, 'light')

    installJanitorThemes()

    expect(window.localStorage.getItem(SKIN_KEY)).toBe('slate')
    expect(window.localStorage.getItem(MODE_KEY)).toBe('light')
  })
})