import { type CSSProperties, useState } from 'react'

import introCopyJsonl from './intro-copy.jsonl?raw'

type IntroCopy = {
  headline: string
  body: string
}

type IntroCopyRecord = IntroCopy & {
  personality: string
}

export type IntroProps = {
  personality?: string
  seed?: number
}

const NEUTRAL_PERSONALITIES = new Set(['', 'default', 'none', 'neutral'])

const FALLBACK_COPY: IntroCopy[] = [
  {
    headline: '¿Qué movemos hoy?',
    body: '>_ Manda bug, rama, plan o idea. Inspecciono el repo y lo convierto en el siguiente paso concreto.'
  },
  {
    headline: '¿Qué tienes en mente?',
    body: '>_ Pasa código, pregunta o el punto atascado. Leo el contexto antes de tocar nada.'
  },
  {
    headline: '¿Qué reviso primero?',
    body: '>_ Manda tarea, path fallido o plan a medias. Lo aterrizamos en acción.'
  },
  {
    headline: '¿Por dónde empezamos?',
    body: '>_ Trae el problema, el objetivo o el archivo. Inspecciono primero, después ejecuto.'
  },
  {
    headline: '¿Qué pide atención?',
    body: '>_ Pásame el contexto que tengas. Lo ordeno en plan o fix.'
  }
]

function normalizeKey(value?: string): string {
  return (value || '').trim().toLowerCase()
}

function titleize(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function isIntroCopyRecord(value: unknown): value is IntroCopyRecord {
  if (!value || typeof value !== 'object') {
    return false
  }

  const record = value as Record<string, unknown>

  return (
    typeof record.personality === 'string' &&
    typeof record.headline === 'string' &&
    typeof record.body === 'string' &&
    Boolean(record.personality.trim()) &&
    Boolean(record.headline.trim()) &&
    Boolean(record.body.trim())
  )
}

function parseIntroCopy(raw: string): Record<string, IntroCopy[]> {
  const byPersonality: Record<string, IntroCopy[]> = {}

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()

    if (!trimmed) {
      continue
    }

    try {
      const parsed: unknown = JSON.parse(trimmed)

      if (!isIntroCopyRecord(parsed)) {
        continue
      }

      const key = normalizeKey(parsed.personality)
      byPersonality[key] ??= []
      byPersonality[key].push({
        headline: parsed.headline.trim(),
        body: parsed.body.trim()
      })
    } catch {
      // Bad generated copy should not break the whole desktop app.
    }
  }

  return byPersonality
}

const INTRO_COPY_BY_PERSONALITY = parseIntroCopy(introCopyJsonl)

function neutralCopy(): IntroCopy[] {
  return INTRO_COPY_BY_PERSONALITY.none || INTRO_COPY_BY_PERSONALITY.default || FALLBACK_COPY
}

function fallbackCopyForPersonality(personalityKey: string): IntroCopy[] {
  if (NEUTRAL_PERSONALITIES.has(personalityKey)) {
    return neutralCopy()
  }

  const label = titleize(personalityKey)

  return [
    {
      headline: `Modo ${label} activo. ¿Qué trabajamos?`,
      body: '>_ Manda tarea, archivo o idea. Mantengo el tono configurado y el trabajo aterrizado en este repo.'
    },
    {
      headline: `¿Qué necesita ver ${label} Janitor?`,
      body: '>_ Trae el contexto o el punto atascado. Me adapto a tu personalidad configurada.'
    },
    {
      headline: `Modo ${label} listo.`,
      body: '>_ Pasa problema, archivo o idea. Sigo la personalidad que configuraste.'
    },
    {
      headline: `¿Qué aborda ${label} Janitor?`,
      body: '>_ Sistema en linea. Habla.'
    },
    {
      headline: '¿Por dónde arrancamos?',
      body: `>_ Pásame el contexto y respondo en modo ${label}.`
    }
  ]
}

function pickCopy(copies: IntroCopy[], seed = 0): IntroCopy {
  return copies[Math.abs(seed) % copies.length] || FALLBACK_COPY[0]
}

// Branding fork Janitor: palabra "HERMES AGENT" reemplazada por "J4NITOR-AGENT".
// Ver .sisyphus/plans/janitor-desktop-customization.md sección 1.1 y AGENTS.md regla 1.
const WORDMARK = 'J4NITOR-AGENT'

function resolveCopy(personality?: string, seed?: number): IntroCopy {
  const personalityKey = normalizeKey(personality)

  const copies = NEUTRAL_PERSONALITIES.has(personalityKey)
    ? INTRO_COPY_BY_PERSONALITY[personalityKey] || neutralCopy()
    : INTRO_COPY_BY_PERSONALITY[personalityKey] || fallbackCopyForPersonality(personalityKey)

  return pickCopy(copies, seed)
}

export function Intro({ personality, seed }: IntroProps) {
  const [mountSeed] = useState(() => Math.floor(Math.random() * 100000))
  const copy = resolveCopy(personality, mountSeed + (seed ?? 0))

  return (
    <div
      className="pointer-events-none flex w-full min-w-0 flex-col items-center justify-center px-0.5 py-6 text-center text-muted-foreground sm:px-6 lg:px-8"
      data-slot="aui_intro"
    >
      <div className="w-full min-w-0">
        <p
          aria-label={WORDMARK}
          className="fit-text mx-auto mb-1 w-[calc(100%-1rem)] font-['Collapse'] font-bold uppercase leading-[0.9] tracking-[0.08em] text-midground mix-blend-plus-lighter dark:text-foreground/90"
          style={{ '--fit-min': '2.75rem' } as CSSProperties}
        >
          <span>
            <span>{WORDMARK}</span>
          </span>
          <span aria-hidden="true">{WORDMARK}</span>
        </p>

        <p className="m-0 text-center leading-normal tracking-tight">{copy.body}</p>
      </div>
    </div>
  )
}
