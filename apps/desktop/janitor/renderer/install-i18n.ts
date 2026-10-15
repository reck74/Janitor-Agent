import { useMemo } from 'react'

import { useI18n } from '@/i18n'
import type { Translations } from '@/i18n'

// Only product prose in the install selector is branded. Commands, URLs,
// protocol names, provider names and the rest of the Hermes engine stay intact.
const productCopy = [
  'oneTimeTitle',
  'setupChoiceTitle',
  'setupChoiceDesc',
  'setupChoiceDescLocal',
  'connectExistingTitle',
  'installLocalTitle',
  'installLocalDesc',
  'useLocalTitle',
  'useLocalDesc',
  'bundledLocalDesc',
  'localStartUnavailable',
  'remoteSetupTitle',
  'remoteSetupDesc'
] as const

export function janitorInstallCopy(install: Translations['install']): Translations['install'] {
  const result = { ...install }

  for (const key of productCopy) {
    result[key] = install[key].replaceAll('Hermes Desktop', 'Janitor Agent').replaceAll('Hermes', 'Janitor')
  }

  return result
}

export function useJanitorInstallI18n() {
  const original = useI18n()

  return useMemo(
    () => ({ ...original, t: { ...original.t, install: janitorInstallCopy(original.t.install) } }),
    [original]
  )
}
