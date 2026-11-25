/**
 * Janitor desktop plugin — the "Servicios", "Skills" and "Agentes" screens.
 *
 * Seeded into `<home>/desktop-plugins/janitor/plugin.js` by
 * `janitor.desktop_plugin.sync` (source: janitor/desktop_plugin/assets/ in the
 * Janitor fork). Plain ESM loaded uncompiled by the desktop runtime loader:
 * no JSX, and only `@hermes/plugin-sdk`, `react` and `react/jsx-runtime` imports.
 *
 * The backend half is `/api/plugins/janitor/` (janitor/desktop_plugin/api.py
 * and perfiles.py).
 * - Servicios shows state and starts/stops installed applications; installing
 *   one activates its guided skill in the active agent and hands the request
 *   to a new chat, where the agent asks before changing anything.
 * - Skills chooses which catalog skills an agent (profile) uses. The change is
 *   written to that profile's config and applies from its next conversation;
 *   an open conversation keeps its prompt (prompt caching).
 * - Agentes creates specialists from templates (empty memory, Janitor's
 *   persona plus the role, the template's skills). It never deletes a profile.
 *
 * The pure helpers are named exports so they can be tested outside the app
 * (apps/desktop-janitor/scripts/servicios-plugin.test.mjs and
 * perfiles-plugin.test.mjs).
 */

import {
  Badge,
  Button,
  ErrorState,
  host,
  Input,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  PALETTE_AREA,
  Switch,
  useQuery,
  useQueryClient,
  useValue
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useState } from 'react'

export const PLUGIN_ID = 'janitor'
export const PAGE_PATH = '/servicios'
export const SKILLS_PATH = '/skills'
export const AGENTS_PATH = '/agentes'
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
    description: 'Extracción y búsqueda web con Firecrawl en tu equipo. El servicio es local; las páginas se siguen pidiendo a Internet.'
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
  running: { label: 'Contenedor en marcha', variant: 'success', actions: ['stop'] },
  partial: { label: 'En marcha a medias', variant: 'warn', actions: ['start', 'stop'] },
  stopped: { label: 'Detenido', variant: 'muted', actions: ['start'] },
  not_installed: { label: 'No instalado', variant: 'outline', actions: ['install'] },
  docker_unavailable: { label: 'Docker no disponible', variant: 'destructive', actions: [] },
  unknown: { label: 'Estado desconocido', variant: 'muted', actions: ['install'] }
}

/** A running service, refined by whether its local address answers (backend `health`).
 *  `unchecked` (no address to ask) keeps the plain container state. */
const HEALTH = {
  responding: { label: 'En marcha', variant: 'success', actions: ['stop'], openable: true },
  not_responding: {
    label: 'Contenedor en marcha, no responde',
    variant: 'warn',
    actions: ['stop'],
    openable: false,
    hint:
      'El contenedor está arriba, pero el servicio no contesta en su dirección. Si lo acabas de iniciar, ' +
      'espera un poco; si sigue así, está caído: revisa sus registros o pídeselo a Janitor.'
  }
}

/** Badge label/variant, the buttons a service in `state` offers, whether «Abrir»
 *  makes sense and, when something is off, a line explaining it. */
export function stateView(state, health) {
  if (state === 'running' && HEALTH[health]) {
    return HEALTH[health]
  }

  const view = STATES[state] ?? STATES.unknown

  return { ...view, openable: state === 'running' || state === 'partial' }
}

const PENDING = {
  start: 'Iniciando… Docker puede tardar hasta un par de minutos.',
  stop: 'Deteniendo…'
}

export function pendingText(action) {
  return PENDING[action] ?? 'Trabajando…'
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

  // Same text as janitor/services.py UNSUPPORTED_OS_TEXT: the API payload
  // carries only the status code, not the reason.
  if (status === 'unsupported') {
    return (
      'Los aplicativos opcionales de Janitor necesitan Linux o macOS con Docker; ' +
      'en Windows no se pueden instalar ni administrar desde Janitor.'
    )
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
  activation_failed: 'No se pudo activar la skill de instalación en este agente. Revisa la pantalla Skills.',
  unreachable: 'No se pudo contactar con el motor de Janitor.'
}

export function errorText(code) {
  return ERRORS[code] ?? 'No se pudo completar la acción.'
}

/** The request the agent receives for "Instalar con Janitor": it names the guided
 *  skill by its catalog id (activated in the agent first) and asks for
 *  confirmation before changes. No path travels in the request. */
export function installRequest({ label, skill }) {
  return (
    `Quiero instalar ${label}. Usa la skill ${skill} y guíame paso a paso: ` +
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
      url: s.url,
      state: s.state,
      health: s.health ?? null,
      containers: Array.isArray(s.containers) ? s.containers : [],
      managed: true,
      ...appInfo(s.skill, s.name)
    })),
    ...unmanaged.map(a => ({
      key: a.skill,
      name: a.skill,
      skill: a.skill,
      url: '',
      state: 'unknown',
      health: null,
      containers: [],
      managed: false,
      ...appInfo(a.skill, a.skill)
    }))
  ]
}

// ---------------------------------------------------------------------------
// Skills and Agentes: pure helpers.
// ---------------------------------------------------------------------------

/** Mirror of hermes_constants.PROFILE_ID_RE (the backend checks it again). */
const PROFILE_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/
/** Catalog ids are skill names: lower case, digits and dashes. */
const SKILL_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/
/** hermes_cli.profiles._RESERVED_NAMES, plus `default` (the main agent). */
const RESERVED_NAMES = new Set(['hermes', 'default', 'test', 'tmp', 'root', 'sudo'])
export const MAIN_PROFILE = 'default'

export function isValidProfileName(name) {
  return typeof name === 'string' && PROFILE_RE.test(name)
}

export function isValidSkillId(id) {
  return typeof id === 'string' && SKILL_ID_RE.test(id)
}

/** REST path of one agent's skills. Throws on a name that could leave the namespace. */
export function skillsPath(profile) {
  if (!isValidProfileName(profile)) {
    throw new Error('perfil no válido')
  }

  return `/perfiles/${profile}/skills`
}

/** The app's active profile as a backend profile name (`default` when unknown). */
function activeProfile() {
  const current = host.state?.profile?.get?.()

  return isValidProfileName(current) ? current : MAIN_PROFILE
}

/** Spanish name and description per catalog id (upstream's SKILL.md text is in English
 *  and is never shown). An id missing here gets a neutral fallback. */
export const SKILLS = {
  'janitor-onboarding': { label: 'Guía de Janitor', description: 'Explica qué agentes, skills y aplicativos tienes y dónde está cada cosa.' },
  'janitor-system-health': { label: 'Salud del sistema', description: 'Revisa el equipo sin tocar nada y te dice qué está mal, por prioridad.' },
  'janitor-maintenance': { label: 'Mantenimiento programado', description: 'Repite la revisión del equipo cada cierto tiempo y te cuenta qué cambió.' },
  'janitor-cleanup': { label: 'Limpieza del equipo', description: 'Libera disco con un plan que apruebas tú; lo borrado va a la papelera.' },
  'janitor-file-organizer': { label: 'Organizar archivos', description: 'Ordena una carpeta por tipo o fecha, y se puede deshacer.' },
  pdf: { label: 'PDF', description: 'Crea, lee, une, rellena y edita PDF, con reconocimiento de texto.' },
  docx: { label: 'Documentos de Word', description: 'Crea, lee, edita y revisa archivos .docx.' },
  xlsx: { label: 'Hojas de cálculo', description: 'Crea, lee y edita libros .xlsx y archivos CSV.' },
  powerpoint: { label: 'Presentaciones', description: 'Crea, lee y edita presentaciones .pptx.' },
  'document-to-action-items': { label: 'Tareas desde documentos', description: 'Saca obligaciones, plazos y tareas de un documento, citando dónde está cada una.' },
  'weekly-review-planning': { label: 'Revisión semanal', description: 'Repasa compromisos y trabajo parado y arma el plan de la semana.' },
  'grounded-citations': { label: 'Respuestas con fuentes', description: 'Respalda respuestas y documentos con fuentes citadas y comprobables.' },
  'blocked-page-recovery': { label: 'Páginas bloqueadas', description: 'Qué hacer cuando una web no deja leerla: errores 403/429, muros de pago, bloqueos.' },
  arxiv: { label: 'arXiv', description: 'Busca artículos científicos por tema, autor, categoría o identificador.' },
  'llm-wiki': { label: 'Wiki de conocimiento', description: 'Construye y consulta una base de notas enlazadas en markdown.' },
  'competitor-news-monitor': { label: 'Vigilancia de competidores', description: 'Sigue noticias relevantes de empresas concretas, con resúmenes citados.' },
  'youtube-content': { label: 'Contenido de YouTube', description: 'Convierte transcripciones de vídeos en resúmenes, hilos o artículos.' },
  'janitor-repo-research': { label: 'Investigar repositorios', description: 'Analiza un repositorio de GitHub de principio a fin.' },
  'janitor-project-create': { label: 'Crear proyectos', description: 'Monta un proyecto nuevo que compila y pasa sus pruebas.' },
  github: { label: 'GitHub', description: 'Pull requests, issues, revisiones y repositorios con la CLI gh.' },
  spike: { label: 'Prototipos de prueba', description: 'Experimentos desechables para validar una idea antes de construirla.' },
  'systematic-debugging': { label: 'Depuración sistemática', description: 'Encuentra la causa real de un fallo antes de tocar el código.' },
  'test-driven-development': { label: 'Desarrollo guiado por pruebas', description: 'Primero la prueba que falla, luego el código, luego la limpieza.' },
  'claude-code': { label: 'Claude Code', description: 'Delega trabajo de programación en la CLI de Claude Code.' },
  codex: { label: 'Codex', description: 'Delega trabajo de programación en la CLI de Codex.' },
  opencode: { label: 'OpenCode', description: 'Delega programación y revisiones en la CLI de OpenCode.' },
  'google-workspace': { label: 'Google Workspace', description: 'Gmail, Calendar, Drive, Docs y Sheets.' },
  'email-inbox-triage': { label: 'Ordenar el correo', description: 'Prioriza la bandeja de entrada y prepara borradores sin enviar nada solo.' },
  notion: { label: 'Notion', description: 'Páginas y bases de datos de Notion.' },
  obsidian: { label: 'Obsidian', description: 'Lee, busca, crea y edita notas de tu bóveda de Obsidian.' },
  'computer-use': { label: 'Manejar el escritorio', description: 'Controla aplicaciones del escritorio cuando no hay otra forma.' },
  'apple-notes': { label: 'Notas de Apple', description: 'Crea, busca y edita Notas de Apple.' },
  'apple-reminders': { label: 'Recordatorios de Apple', description: 'Añade, lista y completa Recordatorios.' },
  findmy: { label: 'Buscar (Apple)', description: 'Localiza tus dispositivos Apple y AirTags.' },
  imessage: { label: 'iMessage', description: 'Envía y recibe iMessage y SMS.' }
}

export function skillInfo(id) {
  if (SKILLS[id]) {
    return SKILLS[id]
  }

  if (APPS[id]) {
    return { label: APPS[id].label, description: `${APPS[id].description} Guía su instalación.` }
  }

  return { label: id, description: 'Skill del catálogo de Janitor.' }
}

const PLATFORM_NAMES = { linux: 'Linux', macos: 'macOS', windows: 'Windows' }

export function platformNote(platforms) {
  const names = (Array.isArray(platforms) ? platforms : []).map(p => PLATFORM_NAMES[p] ?? p)

  return names.length ? `Solo en ${names.join(' y ')}.` : ''
}

/** `ids` with `id` switched on or off, order kept (new ids go last). */
export function toggleSkill(ids, id, on) {
  const without = ids.filter(x => x !== id)

  return on ? [...without, id] : without
}

export function sameSelection(a, b) {
  return a.length === b.length && [...a].sort().join('\n') === [...b].sort().join('\n')
}

/** Purpose groups for the screen, each skill with its Spanish copy and switch state. */
export function skillGroups(payload, selection) {
  const chosen = new Set(selection)
  const groups = Array.isArray(payload?.propositos) ? payload.propositos : []

  return groups.map(group => ({
    id: group.id,
    label: group.nombre || group.id,
    skills: (Array.isArray(group.skills) ? group.skills : []).map(skill => ({
      id: skill.id,
      ...skillInfo(skill.id),
      on: chosen.has(skill.id),
      // A skill of another OS can be switched off but never on.
      locked: !skill.disponible && !chosen.has(skill.id),
      note: skill.otra_plataforma ? platformNote(skill.plataformas) : skill.disponible ? '' : 'No está en esta instalación.'
    }))
  }))
}

const TEMPLATE_NAMES = { investigador: 'Investigador', 'creador-proyectos': 'Creador de proyectos', main: 'Janitor' }

/** How an agent (profile) reads in selectors and lists. */
export function profileLabel(profile) {
  if (!profile) {
    return ''
  }

  if (profile.principal || profile.nombre === MAIN_PROFILE) {
    return 'Janitor (principal)'
  }

  const template = profile.plantilla ? TEMPLATE_NAMES[profile.plantilla] ?? profile.plantilla : null

  return template ? `${profile.nombre} · ${template}` : profile.nombre
}

/** Client-side check of a new agent name, same rules as the backend. Returns an error code or null. */
export function newAgentNameError(name, existing = []) {
  if (!isValidProfileName(name) || RESERVED_NAMES.has(name)) {
    return 'nombre_invalido'
  }

  return existing.includes(name) ? 'existe' : null
}

const SKILLS_ERRORS = {
  400: 'El servidor rechazó la lista: solo se aceptan skills del catálogo. Recarga la pantalla.',
  404: 'Ese agente ya no existe. Elige otro.',
  unreachable: 'No se pudo contactar con el motor de Janitor. No se guardó nada.'
}

export function skillsErrorText(error) {
  const status = restStatus(error)

  return SKILLS_ERRORS[status] ?? SKILLS_ERRORS.unreachable
}

const AGENT_ERRORS = {
  nombre_invalido:
    'Nombre no válido: minúsculas, números, «-» o «_», empezando por letra o número, hasta 64 caracteres. ' +
    'Algunos nombres de sistema, como «default», «root» o «test», están reservados.',
  existe: 'Ya hay un agente con ese nombre. No se sobrescribe nada: elige otro.',
  plantilla_desconocida: 'Esa plantilla ya no existe en esta instalación. Recarga la pantalla.',
  tiempo_agotado: 'Crear el agente tardó demasiado. Revisa la lista antes de reintentar.',
  fallo: 'No se pudo crear el agente. Prueba en la terminal: janitor plantillas crear <plantilla> --nombre <nombre>.',
  unreachable: 'No se pudo contactar con el motor de Janitor.'
}

export function agentErrorText(code) {
  return AGENT_ERRORS[code] ?? AGENT_ERRORS.fallo
}

/** The line shown after creating a specialist. */
export function createdText(agent) {
  const credentials = agent?.credenciales
    ? 'Usa las mismas credenciales del proveedor que el principal.'
    : 'No había credenciales del proveedor que copiar: configúralas en ese agente antes de usarlo.'

  return `Listo: «${agent?.nombre}» existe, con memoria vacía y sus propias skills. ${credentials}`
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
  spacer: { flex: 1 },
  ok: { color: 'var(--ui-text-secondary)', fontSize: '0.75rem', lineHeight: 1.5, margin: 0 },
  field: { alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: '8px' },
  label: { color: 'var(--ui-text-secondary)', fontSize: '0.8125rem' },
  select: {
    background: 'transparent',
    border: '1px solid var(--ui-stroke-secondary)',
    borderRadius: '6px',
    color: 'var(--ui-text-primary)',
    fontSize: '0.8125rem',
    padding: '4px 8px'
  },
  group: { color: 'var(--ui-text-primary)', fontSize: '0.9375rem', fontWeight: 600, margin: '12px 0 0' },
  skill: {
    alignItems: 'flex-start',
    borderBottom: '1px solid var(--ui-stroke-tertiary)',
    display: 'flex',
    gap: '12px',
    padding: '10px 0'
  },
  skillText: { display: 'flex', flex: 1, flexDirection: 'column', gap: '2px' },
  sticky: {
    alignItems: 'center',
    // Opaque on purpose: rows scroll underneath this bar.
    background: 'var(--ui-bg-chrome, var(--background, #0b0b0c))',
    borderTop: '1px solid var(--ui-stroke-tertiary)',
    bottom: 0,
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    padding: '10px 0',
    position: 'sticky',
    zIndex: 1
  },
  input: { maxWidth: '240px' }
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

/** HTTP status of a failed REST call (the transport's message starts with it), or null. */
export function restStatus(error) {
  const match = /^(\d{3})\b/.exec(String(error?.message ?? error ?? '').trim())

  return match ? Number(match[1]) : null
}

/** Error code for a failed Servicios REST call. */
export function restErrorCode(error) {
  return restStatus(error) === 404 ? 'unknown_service' : 'unreachable'
}

function ServiceRow({ ctx, entry, onChanged }) {
  const [pending, setPending] = useState(null)
  const [error, setError] = useState(null)
  const view = stateView(entry.state, entry.health)

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

  // The guided skill is activated in the active agent first (it is not in any
  // template), so the new chat — a new conversation — sees it by its id.
  const install = async () => {
    setError(null)

    if (!isValidSkillId(entry.skill)) {
      setError(errorText('activation_failed'))

      return
    }

    try {
      const result = await ctx.rest(`${skillsPath(activeProfile())}/${entry.skill}`, { method: 'POST' })

      if (!result?.ok) {
        setError(errorText('activation_failed'))

        return
      }
    } catch (failure) {
      setError(errorText(restStatus(failure) === null ? 'unreachable' : 'activation_failed'))

      return
    }

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
      view.hint ? jsx('p', { style: S.note, children: view.hint }) : null,
      pending ? jsx('p', { role: 'status', style: S.meta, children: pendingText(pending) }) : null,
      error ? jsx('p', { role: 'alert', style: S.error, children: error }) : null,
      jsxs('div', {
        style: S.actions,
        children: [
          ...buttons,
          view.openable && isOpenableUrl(entry.url)
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

// --- Skills (F4-04) ----------------------------------------------------------

const SKILLS_QUERY = ['plugin:janitor', 'skills']
const AGENTS_QUERY = ['plugin:janitor', 'agentes']

function ProfileSelect({ profiles, value, onChange, locked }) {
  return jsxs('label', {
    style: S.field,
    children: [
      jsx('span', { style: S.label, children: 'Agente' }),
      jsx('select', {
        'aria-label': 'Agente',
        disabled: locked,
        onChange: event => onChange(event.target.value),
        style: S.select,
        value,
        children: profiles.map(p => jsx('option', { value: p.nombre, children: profileLabel(p) }, p.nombre))
      }),
      locked ? jsx('span', { style: S.meta, children: 'Guarda o descarta los cambios antes de cambiar de agente.' }) : null
    ]
  })
}

function SkillRow({ skill, onToggle, disabled }) {
  return jsxs('div', {
    style: S.skill,
    children: [
      jsxs('div', {
        style: S.skillText,
        children: [
          jsx('span', { style: S.name, children: skill.label }),
          jsx('p', { style: S.text, children: skill.description }),
          skill.note ? jsx('p', { style: S.meta, children: skill.note }) : null
        ]
      }),
      jsx(Switch, {
        'aria-label': skill.label,
        checked: skill.on,
        disabled: disabled || skill.locked,
        onCheckedChange: on => onToggle(skill.id, on === true)
      })
    ]
  })
}

function makeSkillsPage(ctx) {
  return function SkillsPage() {
    const queryClient = useQueryClient()
    const appProfile = useValue(host.state.profile)
    const [chosenProfile, setChosenProfile] = useState(null)
    const [draft, setDraft] = useState(null) // { profile, ids } while there are unsaved changes
    const [saving, setSaving] = useState(false)
    const [status, setStatus] = useState(null) // { kind: 'ok' | 'error', text }
    const profile = chosenProfile ?? (isValidProfileName(appProfile) ? appProfile : MAIN_PROFILE)

    const query = useQuery({
      queryKey: [...SKILLS_QUERY, profile],
      queryFn: () => ctx.rest(skillsPath(profile)),
      retry: false
    })

    const payload = query.data
    const saved = Array.isArray(payload?.activas) ? payload.activas : []
    const selection = draft && draft.profile === profile ? draft.ids : saved
    const dirty = !sameSelection(selection, saved)
    const profiles = Array.isArray(payload?.perfiles) ? payload.perfiles : [{ nombre: profile, principal: profile === MAIN_PROFILE }]

    const pickProfile = name => {
      setDraft(null)
      setStatus(null)
      setChosenProfile(name)
    }

    const toggle = (id, on) => {
      setStatus(null)
      setDraft({ profile, ids: toggleSkill(selection, id, on) })
    }

    const save = async () => {
      setSaving(true)
      setStatus(null)

      try {
        const result = await ctx.rest(skillsPath(profile), { method: 'PUT', body: { skills: selection } })
        queryClient.setQueryData([...SKILLS_QUERY, profile], result)
        setDraft(null)
        setStatus({
          kind: 'ok',
          text: 'Guardado. Se aplica en la próxima conversación de este agente; la que tengas abierta sigue igual.'
        })
      } catch (failure) {
        setStatus({ kind: 'error', text: skillsErrorText(failure) })
      } finally {
        setSaving(false)
      }
    }

    let body

    if (query.isPending) {
      body = jsx('p', { style: S.help, children: 'Leyendo las skills de este agente…' })
    } else if (query.isError) {
      body = jsx(ErrorState, {
        title: 'No se pudieron leer las skills',
        description: skillsErrorText(query.error),
        children: jsx(Button, {
          onClick: () => {
            setChosenProfile(MAIN_PROFILE)
            void queryClient.invalidateQueries({ queryKey: SKILLS_QUERY })
          },
          size: 'sm',
          variant: 'secondary',
          children: 'Volver al principal'
        })
      })
    } else {
      const groups = skillGroups(payload, selection)
      const legacy = payload?.gestionado === false
      const outside = Array.isArray(payload?.fuera_del_catalogo) ? payload.fuera_del_catalogo : []

      body = jsxs('div', {
        style: S.list,
        children: [
          legacy
            ? jsx('p', {
                style: S.note,
                children:
                  'Este agente todavía no usa el catálogo. Al guardar, verá solo las skills que marques aquí.'
              })
            : null,
          outside.length
            ? jsx('p', {
                style: S.note,
                children: `Tiene skills que ya no están en el catálogo y se quitarán al guardar: ${outside.join(', ')}.`
              })
            : null,
          ...groups.flatMap(group => [
            jsx('h2', { style: S.group, children: group.label }, `${group.id}-title`),
            ...group.skills.map(skill => jsx(SkillRow, { disabled: saving, onToggle: toggle, skill }, skill.id))
          ]),
          jsxs('div', {
            style: S.sticky,
            children: [
              jsx(Button, {
                disabled: !dirty || saving,
                loading: saving,
                onClick: () => void save(),
                size: 'sm',
                variant: 'default',
                children: 'Guardar'
              }),
              jsx(Button, {
                disabled: !dirty || saving,
                onClick: () => {
                  setDraft(null)
                  setStatus(null)
                },
                size: 'sm',
                variant: 'ghost',
                children: 'Descartar cambios'
              }),
              dirty ? jsx('span', { style: S.meta, children: 'Cambios sin guardar.' }) : null,
              status
                ? jsx('p', {
                    role: status.kind === 'error' ? 'alert' : 'status',
                    style: status.kind === 'error' ? S.error : S.ok,
                    children: status.text
                  })
                : null
            ]
          })
        ]
      })
    }

    return jsx('div', {
      style: S.scroll,
      children: jsxs('div', {
        style: S.page,
        children: [
          jsx('h1', { style: S.title, children: 'Skills' }),
          jsx('p', {
            style: S.lead,
            children:
              'Qué sabe hacer cada agente. Solo aparecen las skills del catálogo de Janitor: lo que no marques aquí, ' +
              'ese agente no lo ve. Los cambios se aplican en la próxima conversación; la que tienes abierta no se toca.'
          }),
          jsx(ProfileSelect, { locked: dirty || saving, onChange: pickProfile, profiles, value: profile }),
          body
        ]
      })
    })
  }
}

// --- Agentes (F4-05) ---------------------------------------------------------

function TemplateCard({ ctx, template, existing, onCreated }) {
  const [name, setName] = useState(template.id)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)
  const skills = (Array.isArray(template.skills) ? template.skills : []).map(id => skillInfo(id).label)

  const create = async () => {
    const problem = newAgentNameError(name, existing)
    setCreated(null)

    if (problem) {
      setError(agentErrorText(problem))

      return
    }

    setPending(true)
    setError(null)

    try {
      const result = await ctx.rest('/agentes', {
        method: 'POST',
        body: { plantilla: template.id, nombre: name },
        timeoutMs: 150_000
      })

      if (result?.ok) {
        setCreated(result.agente)
        onCreated()
      } else {
        setError(agentErrorText(result?.error))
      }
    } catch {
      setError(agentErrorText('unreachable'))
    } finally {
      setPending(false)
    }
  }

  return jsxs('section', {
    style: S.row,
    'aria-label': template.nombre,
    children: [
      jsx('span', { style: S.name, children: template.nombre }),
      jsx('p', { style: S.text, children: template.descripcion }),
      skills.length ? jsx('p', { style: S.meta, children: `Skills: ${skills.join(', ')}.` }) : null,
      jsxs('div', {
        style: S.actions,
        children: [
          jsx('span', { style: S.label, children: 'Nombre' }),
          jsx(Input, {
            'aria-label': `Nombre del agente ${template.nombre}`,
            disabled: pending,
            onChange: event => {
              setName(event.target.value)
              setError(null)
            },
            style: S.input,
            value: name
          }),
          jsx(Button, {
            disabled: pending,
            loading: pending,
            onClick: () => void create(),
            size: 'sm',
            variant: 'default',
            children: 'Crear'
          })
        ]
      }),
      pending ? jsx('p', { role: 'status', style: S.meta, children: 'Creando el agente…' }) : null,
      error ? jsx('p', { role: 'alert', style: S.error, children: error }) : null,
      created
        ? jsxs('div', {
            style: S.actions,
            children: [
              jsx('p', { role: 'status', style: S.ok, children: createdText(created) }),
              jsx(Button, {
                onClick: () => host.newChat(created.nombre),
                size: 'sm',
                variant: 'secondary',
                children: 'Abrir un chat con él'
              })
            ]
          })
        : null
    ]
  })
}

function makeAgentsPage(ctx) {
  return function AgentsPage() {
    const queryClient = useQueryClient()

    const query = useQuery({
      queryKey: AGENTS_QUERY,
      queryFn: () => ctx.rest('/agentes'),
      retry: false
    })

    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: AGENTS_QUERY })
      void queryClient.invalidateQueries({ queryKey: SKILLS_QUERY })
    }

    const payload = query.data
    const templates = Array.isArray(payload?.plantillas) ? payload.plantillas : []
    const profiles = Array.isArray(payload?.perfiles) ? payload.perfiles : []
    const existing = profiles.map(p => p.nombre)

    let body

    if (query.isPending) {
      body = jsx('p', { style: S.help, children: 'Leyendo plantillas y agentes…' })
    } else if (query.isError && !payload) {
      body = jsx(ErrorState, {
        title: 'No se pudieron leer los agentes',
        description: agentErrorText('unreachable'),
        children: jsx(Button, { onClick: refresh, size: 'sm', variant: 'secondary', children: 'Reintentar' })
      })
    } else {
      body = jsxs('div', {
        style: S.list,
        children: [
          jsx('h2', { style: S.group, children: 'Plantillas' }),
          ...templates.map(template =>
            jsx(TemplateCard, { ctx, existing, onCreated: refresh, template }, template.id)
          ),
          jsx('h2', { style: S.group, children: 'Agentes que ya tienes' }),
          ...profiles.map(p =>
            jsxs(
              'div',
              {
                style: S.skill,
                children: [
                  jsx('span', { style: { ...S.name, flex: 1 }, children: profileLabel(p) }),
                  typeof p.skills === 'number'
                    ? jsx('span', { style: S.meta, children: `${p.skills} skills` })
                    : jsx('span', { style: S.meta, children: 'sin catálogo' })
                ]
              },
              p.nombre
            )
          )
        ]
      })
    }

    return jsx('div', {
      style: S.scroll,
      children: jsxs('div', {
        style: S.page,
        children: [
          jsx('h1', { style: S.title, children: 'Agentes' }),
          jsx('p', {
            style: S.lead,
            children:
              'Especialistas creados desde una plantilla. Cada uno nace con la personalidad de Janitor, su rol, ' +
              'sus skills y la memoria vacía: no comparte memoria con el principal, que es quien te conoce.'
          }),
          body,
          jsx('p', {
            style: S.help,
            children:
              'Sus skills se cambian en la pantalla Skills. Esta pantalla no borra agentes: eso se hace desde los ' +
              'perfiles de la app, a propósito.'
          })
        ]
      })
    })
  }
}

export default {
  id: PLUGIN_ID,
  name: 'Janitor',
  description: 'Pantallas Servicios, Skills y Agentes de Janitor.',
  register(ctx) {
    const ServiciosPage = makeServiciosPage(ctx)
    const SkillsPage = makeSkillsPage(ctx)
    const AgentsPage = makeAgentsPage(ctx)

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
      },
      {
        id: 'skills-page',
        area: ROUTES_AREA,
        data: { path: SKILLS_PATH },
        render: () => jsx(SkillsPage, {})
      },
      {
        id: 'skills-nav',
        area: SIDEBAR_NAV_AREA,
        order: 61,
        data: { codicon: 'extensions', label: 'Skills', path: SKILLS_PATH }
      },
      {
        id: 'skills-open',
        area: PALETTE_AREA,
        data: {
          id: 'janitor.skills.open',
          label: 'Abrir Skills',
          keywords: ['skills', 'habilidades', 'catálogo', 'agente'],
          run: () => host.navigate(SKILLS_PATH)
        }
      },
      {
        id: 'agentes-page',
        area: ROUTES_AREA,
        data: { path: AGENTS_PATH },
        render: () => jsx(AgentsPage, {})
      },
      {
        id: 'agentes-nav',
        area: SIDEBAR_NAV_AREA,
        order: 62,
        data: { codicon: 'organization', label: 'Agentes', path: AGENTS_PATH }
      },
      {
        id: 'agentes-open',
        area: PALETTE_AREA,
        data: {
          id: 'janitor.agentes.open',
          label: 'Abrir Agentes',
          keywords: ['agentes', 'plantillas', 'especialista', 'investigador', 'perfil'],
          run: () => host.navigate(AGENTS_PATH)
        }
      }
    ])
  }
}
