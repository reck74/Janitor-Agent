/**
 * Janitor desktop plugin — the "Servicios" screen.
 *
 * Seeded into `<home>/desktop-plugins/janitor/plugin.js` by
 * `janitor.desktop_plugin.sync` (source: janitor/desktop_plugin/assets/ in the
 * Janitor fork). Plain ESM loaded uncompiled by the desktop runtime loader:
 * no JSX, and only `@hermes/plugin-sdk`, `react` and `react/jsx-runtime` imports.
 *
 * The backend half is `/api/plugins/janitor/` (janitor/desktop_plugin/api.py).
 * The screen shows state and starts/stops installed applications; installing
 * one is handed to the agent, which runs the application's guided skill and
 * asks before changing anything. Uninstalling stays in the terminal.
 *
 * The pure helpers are named exports so they can be tested outside the app
 * (apps/desktop-janitor/scripts/servicios-plugin.test.mjs).
 */

import {
  Badge,
  Button,
  ErrorState,
  host,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  PALETTE_AREA,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useState } from 'react'

export const PLUGIN_ID = 'janitor'
export const PAGE_PATH = '/servicios'
export const REFRESH_MS = 10_000
const LIST_TIMEOUT_MS = 45_000
const ACTION_TIMEOUT_MS = 130_000
const QUERY_KEY = ['plugin:janitor', 'servicios']

/** Mirror of the backend's NAME_RE (janitor/desktop_plugin/api.py). */
const NAME_RE = /^[a-z0-9][a-z0-9-]{0,39}$/

export function isValidServiceName(name) {
  return typeof name === 'string' && NAME_RE.test(name)
}

/** Spanish display data per skill id. Unknown applications get a neutral fallback. */
export const APPS = {
  'janitor-honcho': {
    label: 'Honcho',
    description: 'Memoria avanzada: recuerda conversaciones y preferencias entre sesiones.'
  },
  'janitor-n8n': {
    label: 'n8n',
    description: 'Automatizaciones: flujos de trabajo entre aplicaciones y servicios.'
  },
  'janitor-lightrag': {
    label: 'LightRAG',
    description: 'Base de conocimiento: consultas sobre tus documentos.'
  },
  'janitor-nocodb': {
    label: 'NocoDB',
    description: 'Bases de datos con vista de hoja de cálculo para tus proyectos.'
  },
  'janitor-waha': {
    label: 'WAHA (WhatsApp)',
    description: 'Revisa tu WhatsApp personal y avisa de lo importante u olvidado.',
    note:
      'Privacidad: lee tu WhatsApp personal y las conversaciones llegan al proveedor de IA configurado. ' +
      'Solo lectura: no envía mensajes salvo que se lo ordenes.'
  },
  'janitor-firecrawl': {
    label: 'Firecrawl',
    description: 'Búsqueda y lectura de páginas web totalmente local.'
  },
  'janitor-opendesign': {
    label: 'Open Design',
    description: 'Generación de diseños con Janitor como agente.',
    note: 'No funciona con contenedores: esta pantalla no puede ver si está instalado ni en marcha.'
  }
}

export function appInfo(skill, fallbackName) {
  return APPS[skill] ?? { label: fallbackName || skill, description: 'Aplicativo opcional de Janitor.' }
}

const STATES = {
  running: { label: 'En marcha', variant: 'success', actions: ['stop'] },
  partial: { label: 'En marcha a medias', variant: 'warn', actions: ['start', 'stop'] },
  stopped: { label: 'Detenido', variant: 'muted', actions: ['start'] },
  not_installed: { label: 'No instalado', variant: 'outline', actions: ['install'] },
  docker_unavailable: { label: 'Docker no disponible', variant: 'destructive', actions: [] },
  unknown: { label: 'Estado desconocido', variant: 'muted', actions: ['install'] }
}

/** Badge label/variant and the buttons a service in `state` offers. */
export function stateView(state) {
  return STATES[state] ?? STATES.unknown
}

const CONTAINER_STATES = {
  running: 'en marcha',
  exited: 'detenido',
  created: 'creado',
  paused: 'en pausa',
  restarting: 'reiniciando',
  removing: 'eliminándose',
  dead: 'con error',
  absent: 'no existe',
  unknown: 'desconocido'
}

export function containerStateLabel(state) {
  return CONTAINER_STATES[state] ?? state
}

export function dockerLine(docker) {
  const status = docker?.status

  if (status === 'ok') {
    return 'Docker está disponible.'
  }

  if (status === 'missing') {
    return 'Docker no está instalado. Janitor te guía para instalarlo cuando instales un aplicativo.'
  }

  if (status === 'timeout') {
    return 'Docker no responde a tiempo.'
  }

  return 'Docker está instalado pero no responde: el servicio está detenido o tu usuario no tiene permiso.'
}

const ERRORS = {
  busy: 'Ya hay una acción en curso para este aplicativo.',
  docker_unavailable: 'Docker no responde, así que no se puede iniciar ni detener nada.',
  not_installed: 'No está instalado. Usa «Instalar con Janitor».',
  timeout: 'Docker tardó demasiado en responder. Revisa el estado y vuelve a intentarlo.',
  docker_failed: 'Docker devolvió un error. Revisa el estado del aplicativo.',
  unknown_service: 'Este aplicativo ya no existe en esta instalación.',
  unreachable: 'No se pudo contactar con el motor de Janitor.'
}

export function errorText(code) {
  return ERRORS[code] ?? 'No se pudo completar la acción.'
}

/** The request the agent receives for "Instalar con Janitor": it names the guided
 *  skill and where its instructions are, and asks for confirmation before changes. */
export function installRequest({ label, skill, skillMd }) {
  const where = skillMd ? ` (si no la tienes cargada, sus instrucciones están en ${skillMd})` : ''

  return (
    `Quiero instalar ${label}. Usa la skill ${skill}${where} y guíame paso a paso: ` +
    'dime qué vas a hacer y pídeme confirmación antes de cambiar nada.'
  )
}

export function isOpenableUrl(url) {
  return typeof url === 'string' && /^https?:\/\/[^\s]+$/.test(url)
}

/** Services from the backend plus the stateless applications, in display order. */
export function entriesFrom(payload) {
  const services = Array.isArray(payload?.services) ? payload.services : []
  const unmanaged = Array.isArray(payload?.unmanaged) ? payload.unmanaged : []

  return [
    ...services.map(s => ({
      key: s.skill,
      name: s.name,
      skill: s.skill,
      skillMd: s.skill_md,
      url: s.url,
      state: s.state,
      containers: Array.isArray(s.containers) ? s.containers : [],
      managed: true,
      ...appInfo(s.skill, s.name)
    })),
    ...unmanaged.map(a => ({
      key: a.skill,
      name: a.skill,
      skill: a.skill,
      skillMd: a.skill_md,
      url: '',
      state: 'unknown',
      containers: [],
      managed: false,
      ...appInfo(a.skill, a.skill)
    }))
  ]
}

// ---------------------------------------------------------------------------
// UI. Inline styles with theme variables only: a disk plugin's class names are
// not seen by the app's Tailwind build, and no colour is hardcoded.
// ---------------------------------------------------------------------------

const S = {
  scroll: { height: '100%', overflowY: 'auto' },
  page: {
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    margin: '0 auto',
    maxWidth: '880px',
    padding: '28px 32px 40px'
  },
  title: { color: 'var(--ui-text-primary)', fontSize: '1.125rem', fontWeight: 600, margin: 0 },
  lead: { color: 'var(--ui-text-secondary)', fontSize: '0.8125rem', lineHeight: 1.5, margin: 0 },
  help: { color: 'var(--ui-text-tertiary)', fontSize: '0.75rem', lineHeight: 1.5, margin: 0 },
  banner: {
    alignItems: 'center',
    borderBottom: '1px solid var(--ui-stroke-tertiary)',
    borderTop: '1px solid var(--ui-stroke-tertiary)',
    color: 'var(--ui-text-secondary)',
    display: 'flex',
    flexWrap: 'wrap',
    fontSize: '0.8125rem',
    gap: '8px',
    padding: '10px 0'
  },
  list: { display: 'flex', flexDirection: 'column' },
  row: {
    borderBottom: '1px solid var(--ui-stroke-tertiary)',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    padding: '14px 0'
  },
  head: { alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: '8px' },
  name: { color: 'var(--ui-text-primary)', fontSize: '0.875rem', fontWeight: 600 },
  text: { color: 'var(--ui-text-secondary)', fontSize: '0.8125rem', lineHeight: 1.5, margin: 0 },
  meta: { color: 'var(--ui-text-tertiary)', fontSize: '0.75rem', lineHeight: 1.5, margin: 0, wordBreak: 'break-word' },
  note: {
    borderLeft: '2px solid var(--ui-accent)',
    color: 'var(--ui-text-secondary)',
    fontSize: '0.75rem',
    lineHeight: 1.5,
    margin: 0,
    paddingLeft: '8px'
  },
  error: { color: 'var(--ui-red)', fontSize: '0.75rem', lineHeight: 1.5, margin: 0 },
  actions: { alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' },
  spacer: { flex: 1 }
}

function sleep(ctx, ms) {
  return new Promise(resolve => ctx.setTimeout(resolve, ms))
}

/** Open a fresh chat and put `text` in its composer for the user to review and
 *  send. Never submits. Falls back to the clipboard + a toast with the text. */
async function handOffToAgent(ctx, text) {
  host.newChat()

  for (let attempt = 0; attempt < 20; attempt += 1) {
    await sleep(ctx, 150)
    const current = await host.composer.getDraft('new')
    const placed = current?.trim()
      ? await host.composer.insertText('new', text, { mode: 'block' })
      : await host.composer.setDraft('new', text)

    if (placed) {
      host.composer.focus('new')

      return true
    }
  }

  await ctx.os.writeClipboard(text)
  host.notify({
    kind: 'info',
    title: 'Pídeselo a Janitor',
    message: 'No se pudo escribir en el chat. La petición está en el portapapeles: pégala y envíala.',
    detail: text
  })

  return false
}

/** Error code for a failed REST call: the transport's message starts with the HTTP status. */
export function restErrorCode(error) {
  const message = String(error?.message ?? error ?? '')

  return /^404\b/.test(message.trim()) ? 'unknown_service' : 'unreachable'
}

function ServiceRow({ ctx, entry, onChanged }) {
  const [pending, setPending] = useState(null)
  const [error, setError] = useState(null)
  const view = stateView(entry.state)
  const running = entry.state === 'running' || entry.state === 'partial'

  const run = async action => {
    if (!isValidServiceName(entry.name)) {
      setError(errorText('unknown_service'))

      return
    }

    setPending(action)
    setError(null)

    try {
      const result = await ctx.rest(`/servicios/${entry.name}/${action}`, {
        method: 'POST',
        timeoutMs: ACTION_TIMEOUT_MS
      })

      if (!result?.ok) {
        setError(errorText(result?.error))
      }
    } catch (failure) {
      setError(errorText(restErrorCode(failure)))
    } finally {
      setPending(null)
      onChanged()
    }
  }

  const install = async () => {
    setError(null)
    await handOffToAgent(ctx, installRequest(entry))
  }

  const buttons = view.actions.map(action => {
    if (action === 'install') {
      return jsx(
        Button,
        { onClick: () => void install(), size: 'sm', variant: 'default', children: 'Instalar con Janitor' },
        action
      )
    }

    return jsx(
      Button,
      {
        disabled: pending !== null,
        loading: pending === action,
        onClick: () => void run(action),
        size: 'sm',
        variant: action === 'start' ? 'default' : 'secondary',
        children: action === 'start' ? 'Iniciar' : 'Detener'
      },
      action
    )
  })

  const containers = entry.containers.length
    ? 'Contenedores: ' + entry.containers.map(c => `${c.name} (${containerStateLabel(c.state)})`).join(', ')
    : null

  return jsxs('section', {
    style: S.row,
    'aria-label': entry.label,
    children: [
      jsxs('div', {
        style: S.head,
        children: [
          jsx('span', { style: S.name, children: entry.label }),
          jsx(Badge, { variant: view.variant, children: view.label })
        ]
      }),
      jsx('p', { style: S.text, children: entry.description }),
      entry.note ? jsx('p', { style: S.note, children: entry.note }) : null,
      entry.url ? jsx('p', { style: S.meta, children: `Dirección: ${entry.url}` }) : null,
      containers ? jsx('p', { style: S.meta, children: containers }) : null,
      error ? jsx('p', { role: 'alert', style: S.error, children: error }) : null,
      jsxs('div', {
        style: S.actions,
        children: [
          ...buttons,
          running && isOpenableUrl(entry.url)
            ? jsx(
                Button,
                { onClick: () => void ctx.os.openExternal(entry.url), size: 'sm', variant: 'ghost', children: 'Abrir' },
                'open'
              )
            : null
        ]
      })
    ]
  })
}

function makeServiciosPage(ctx) {
  return function ServiciosPage() {
    const queryClient = useQueryClient()

    const query = useQuery({
      queryKey: QUERY_KEY,
      queryFn: () => ctx.rest('/servicios', { timeoutMs: LIST_TIMEOUT_MS }),
      refetchInterval: REFRESH_MS,
      refetchIntervalInBackground: false
    })

    const refresh = () => void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    const payload = query.data
    const entries = entriesFrom(payload)

    let body

    if (query.isPending) {
      body = jsx('p', { style: S.help, children: 'Leyendo el estado de los servicios…' })
    } else if (query.isError && !payload) {
      body = jsx(ErrorState, {
        title: 'No se pudo leer el estado de los servicios',
        description:
          'El motor de Janitor no respondió. Si acabas de actualizar, reinicia la app; si sigue igual, abre ' +
          '«janitor» una vez en la terminal para reinstalar esta pantalla.',
        children: jsx(Button, { onClick: refresh, size: 'sm', variant: 'secondary', children: 'Reintentar' })
      })
    } else {
      body = jsx('div', {
        style: S.list,
        children: entries.map(entry => jsx(ServiceRow, { ctx, entry, onChanged: refresh }, entry.key))
      })
    }

    return jsx('div', {
      style: S.scroll,
      children: jsxs('div', {
        style: S.page,
        children: [
          jsx('h1', { style: S.title, children: 'Servicios' }),
          jsx('p', {
            style: S.lead,
            children:
              'Aplicativos opcionales de Janitor. Janitor los instala contigo en el chat; aquí ves su estado y los ' +
              'inicias o detienes.'
          }),
          jsxs('div', {
            style: S.banner,
            role: 'status',
            children: [
              jsx('span', { children: 'Los aplicativos opcionales necesitan Docker.' }),
              payload ? jsx('span', { children: dockerLine(payload.docker) }) : null
            ]
          }),
          body,
          jsx('p', {
            style: S.help,
            children:
              'Para desinstalar un aplicativo usa la terminal: janitor services uninstall <nombre>. ' +
              'Se borran los contenedores y se conservan tus datos.'
          })
        ]
      })
    })
  }
}

export default {
  id: PLUGIN_ID,
  name: 'Janitor',
  description: 'Pantalla Servicios: estado de los aplicativos opcionales de Janitor.',
  register(ctx) {
    const ServiciosPage = makeServiciosPage(ctx)

    ctx.registerMany([
      {
        id: 'servicios-page',
        area: ROUTES_AREA,
        data: { path: PAGE_PATH },
        render: () => jsx(ServiciosPage, {})
      },
      {
        id: 'servicios-nav',
        area: SIDEBAR_NAV_AREA,
        order: 60,
        data: { codicon: 'server-process', label: 'Servicios', path: PAGE_PATH }
      },
      {
        id: 'servicios-open',
        area: PALETTE_AREA,
        data: {
          id: 'janitor.servicios.open',
          label: 'Abrir Servicios',
          keywords: ['servicios', 'aplicativos', 'docker', 'honcho', 'n8n', 'whatsapp', 'waha'],
          run: () => host.navigate(PAGE_PATH)
        }
      }
    ])
  }
}
