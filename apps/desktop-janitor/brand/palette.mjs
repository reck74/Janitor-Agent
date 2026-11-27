// Slash palette in Spanish (patch P14, task F1-19; directive #17).
//
// What the chat palette shows comes from three places:
//   - group headers: the engine's command category (hermes_cli/commands.py,
//     CommandDef.category; tui_gateway/methods_tools.py adds "User commands"
//     and "Plugin commands") or a group the app sets itself
//     (src/app/chat/composer/hooks/use-slash-completions.ts). They are data
//     keys too ('Skills' picks the skill icon), so the patch translates only
//     the rendered header, never the value;
//   - descriptions: es.ts `composer.commandDescs` when it has the command,
//     else the engine's English text. desktopSlashDescription keeps the
//     engine's " (usage: /cmd <hint>)" suffix verbatim, so the hint is
//     translated here, pinned to the engine's English hint;
//   - skill rows: the SKILL.md `description`. Janitor's own skills carry it in
//     Spanish at the source (janitor/skills/**/SKILL.md); the upstream skills
//     the Janitor catalog offers (janitor/catalog.yaml) get a Spanish
//     `composer.commandDescs['/<id>']` entry, which desktopSlashDescription
//     already prefers. A user's own skill with another name keeps its text.
//
// scripts/palette.test.mjs ties each table to its source: every engine
// category has a header, every command the build offers has a Spanish
// description and a pinned hint, every upstream catalog skill has a row.

// Header text by group value. Values the engine sends AND values the app sets.
export const PALETTE_GROUP_LABELS = {
  // hermes_cli/commands.py categories
  Session: 'Sesión',
  Configuration: 'Configuración',
  Info: 'Información',
  'Tools & Skills': 'Herramientas y skills',
  Exit: 'Salir',
  // tui_gateway: _TUI_EXTRA, quick_commands, plugin commands
  TUI: 'Terminal',
  'User commands': 'Comandos propios',
  'Plugin commands': 'Comandos de plugins',
  // set by the app (use-slash-completions.ts, slashCompletionGroup)
  Skills: 'Skills',
  Commands: 'Comandos',
  Options: 'Opciones',
  Themes: 'Temas',
  Sessions: 'Sesiones'
}

// Categories the engine adds outside CommandDef (tui_gateway); the test reads
// CommandDef categories live and needs these named.
export const ENGINE_EXTRA_GROUPS = ['TUI', 'User commands', 'Plugin commands']

// Groups the app assigns on its own.
export const APP_GROUPS = ['Skills', 'Commands', 'Options', 'Themes', 'Sessions']

// Engine command → [English args_hint as the engine sends it, Spanish hint].
// Subcommands and flags (on|off, --global, list…) are typed literally and
// stay; only the placeholders change. A row whose English no longer matches
// the engine renders the engine's hint under «uso:» and fails the test.
export const USAGE_HINTS = {
  '/new': ['[name]', '[nombre]'],
  '/save': ['<json|md|html> [filename] [redact]', '<json|md|html> [archivo] [redact]'],
  '/prompt': ['[initial text]', '[texto inicial]'],
  '/undo': ['[N]', '[N]'],
  '/title': ['[name]', '[nombre]'],
  '/handoff': ['<platform>', '<plataforma>'],
  '/branch': ['[--here] [name]', '[--here] [nombre]'],
  '/worktree': ['[new [name]|list|prune [--dry-run]]', '[new [nombre]|list|prune [--dry-run]]'],
  '/compress': ['[here [N] | focus topic | --preview|--dry-run]', '[here [N] | focus <tema> | --preview|--dry-run]'],
  '/rollback': ['[number] [--all]', '[número] [--all]'],
  '/export': ['[profile] [-o output.tar.gz]', '[perfil] [-o salida.tar.gz]'],
  '/import': ['<archive.tar.gz> [--name <name>]', '<archivo.tar.gz> [--name <nombre>]'],
  '/bg': ['<prompt>', '<prompt>'],
  '/btw': ['<question>', '<pregunta>'],
  '/journey': ['[list|delete <id>|edit <id>]', '[list|delete <id>|edit <id>]'],
  '/queue': ['[<prompt>|list|edit N <prompt>|rm N|move A B|clear]', '[<prompt>|list|edit N <prompt>|rm N|move A B|clear]'],
  '/steer': ['<prompt>', '<prompt>'],
  '/goal': [
    '[text | draft <text> | show | gate add <cmd> | pause | resume | clear | status | wait <pid> | unwait]',
    '[texto | draft <texto> | show | gate add <comando> | pause | resume | clear | status | wait <pid> | unwait]'
  ],
  '/heartbeat': [
    '[every <interval> <prompt> | status | pause | resume | clear]',
    '[every <intervalo> <prompt> | status | pause | resume | clear]'
  ],
  '/refine': ['[focus instructions]', '[en qué fijarse]'],
  '/review': ['[review instructions]', '[instrucciones de revisión]'],
  '/loop': [
    '[interval] <prompt> [--times N] [--until <condition>] | status | pause | resume | stop',
    '[intervalo] <prompt> [--times N] [--until <condición>] | status | pause | resume | stop'
  ],
  '/plan': ['[task]', '[tarea]'],
  '/moa': ['<prompt>', '<prompt>'],
  '/subgoal': ['[text | remove N | clear]', '[texto | remove N | clear]'],
  '/egress': ['[status]', '[status]'],
  '/context': ['[all]', '[all]'],
  '/resume': ['[name]', '[nombre]'],
  '/codex-runtime': ['[auto|codex_app_server]', '[auto|codex_app_server]'],
  '/personality': ['[name]', '[nombre]'],
  '/battery': ['[on|off|status]', '[on|off|status]'],
  '/timestamps': ['[on|off|status]', '[on|off|status]'],
  '/diff': ['[staged|all|session] [--stat] [path...]', '[staged|all|session] [--stat] [ruta...]'],
  '/focus': ['[on|off|status]', '[on|off|status]'],
  '/approvals': ['[manual|smart|off]', '[manual|smart|off]'],
  '/reasoning': ['[level|show|hide|full|clamp] [--global]', '[nivel|show|hide|full|clamp] [--global]'],
  '/skin': ['[name]', '[nombre]'],
  '/wake': ['[on|off|status]', '[on|off|status]'],
  '/tools': ['[list|disable|enable] [name...]', '[list|disable|enable] [nombre...]'],
  '/memory': ['[pending|approve|reject|approval] [id|on|off]', '[pending|approve|reject|approval] [id|on|off]'],
  '/pet': ['[toggle|list|scale <n>|<slug>]', '[toggle|list|scale <n>|<slug>]'],
  '/hatch': ['[description]', '[descripción]'],
  '/learn': ['<what to learn from>', '<de qué aprender>'],
  '/init': ['[notes]', '[notas]'],
  '/suggestions': ['[accept|dismiss N | catalog]', '[accept|dismiss N | catalog]'],
  '/blueprint': ['[name] [slot=value ...]', '[nombre] [campo=valor ...]'],
  '/browser': ['[connect|disconnect|status|use]', '[connect|disconnect|status|use]'],
  '/help': ['[skills|<filter>]', '[skills|<filtro>]'],
  '/usage': ['[reset [--force]]', '[reset [--force]]']
}

// Engine commands the palette never shows with the engine's own text, and why.
export const NOT_OFFERED_BY_ENGINE_TEXT = {
  '/sessions': 'Alias of /resume in the desktop table (session picker); the engine row is never listed.'
}

// Spanish palette text for the UPSTREAM skills of janitor/catalog.yaml, by
// catalog id. Same wording as the «Skills» screen of the Janitor desktop
// plugin (janitor/desktop_plugin/.../plugin.js, SKILLS).
export const SKILL_DESCRIPTIONS = {
  pdf: 'Crea, lee, une, rellena y edita PDF, con reconocimiento de texto.',
  docx: 'Crea, lee, edita y revisa archivos .docx.',
  xlsx: 'Crea, lee y edita libros .xlsx y archivos CSV.',
  powerpoint: 'Crea, lee y edita presentaciones .pptx.',
  'document-to-action-items': 'Saca obligaciones, plazos y tareas de un documento, citando dónde está cada una.',
  'weekly-review-planning': 'Repasa compromisos y trabajo parado y arma el plan de la semana.',
  'grounded-citations': 'Respalda respuestas y documentos con fuentes citadas y comprobables.',
  'blocked-page-recovery': 'Qué hacer cuando una web no deja leerla: errores 403/429, muros de pago, bloqueos.',
  arxiv: 'Busca artículos científicos por tema, autor, categoría o identificador.',
  'llm-wiki': 'Construye y consulta una base de notas enlazadas en markdown.',
  'competitor-news-monitor': 'Sigue noticias relevantes de empresas concretas, con resúmenes citados.',
  'youtube-content': 'Convierte transcripciones de vídeos en resúmenes, hilos o artículos.',
  github: 'Pull requests, issues, revisiones y repositorios con la CLI gh.',
  spike: 'Experimentos desechables para validar una idea antes de construirla.',
  'systematic-debugging': 'Encuentra la causa real de un fallo antes de tocar el código.',
  'test-driven-development': 'Primero la prueba que falla, luego el código, luego la limpieza.',
  'google-workspace': 'Gmail, Calendar, Drive, Docs y Sheets.',
  'email-inbox-triage': 'Prioriza la bandeja de entrada y prepara borradores sin enviar nada solo.',
  notion: 'Páginas y bases de datos de Notion.',
  obsidian: 'Lee, busca, crea y edita notas de tu bóveda de Obsidian.',
  'computer-use': 'Controla aplicaciones del escritorio cuando no hay otra forma.',
  'apple-notes': 'Crea, busca y edita Notas de Apple.',
  'apple-reminders': 'Añade, lista y completa Recordatorios.',
  findmy: 'Localiza tus dispositivos Apple y AirTags.',
  imessage: 'Envía y recibe iMessage y SMS.'
}

const quote = value => `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`

function objectLiteral(entries, indent) {
  return `{\n${entries.map(([key, value]) => `${indent}  ${quote(key)}: ${value}`).join(',\n')}\n${indent}}`
}

export function groupLabelsSource() {
  return objectLiteral(
    Object.entries(PALETTE_GROUP_LABELS).map(([key, value]) => [key, quote(value)]),
    ''
  )
}

export function usageHintsSource() {
  return objectLiteral(
    Object.entries(USAGE_HINTS).map(([command, [en, es]]) => [command, `[${quote(en)}, ${quote(es)}]`]),
    ''
  )
}

export function skillDescriptionLines(indent = '      ') {
  return Object.entries(SKILL_DESCRIPTIONS)
    .map(([id, text]) => `${indent}${quote(`/${id}`)}: ${quote(text)},\n`)
    .join('')
}

export function palettePatches() {
  return [
    {
      id: 'P14-palette-group-map',
      purpose: 'Spanish text for the slash palette group headers (the group value stays: it is also a data key)',
      file: 'src/app/chat/composer/trigger-popover.tsx',
      find: 'const GROUP_HEADER_CLASS =',
      replace:
        '// Janitor build (apps/desktop-janitor/brand/palette.mjs): header text only.\n' +
        `const JANITOR_PALETTE_GROUPS: Record<string, string | undefined> = ${groupLabelsSource()}\n\n` +
        'const GROUP_HEADER_CLASS =',
      count: 1
    },
    {
      id: 'P14-palette-group-header',
      purpose: 'Render the Spanish header for each palette group',
      file: 'src/app/chat/composer/trigger-popover.tsx',
      find: "{showHeader && <div className={cn(GROUP_HEADER_CLASS, isFirstHeader ? 'pt-0.5' : 'pt-2')}>{group}</div>}",
      replace:
        "{showHeader && <div className={cn(GROUP_HEADER_CLASS, isFirstHeader ? 'pt-0.5' : 'pt-2')}>{JANITOR_PALETTE_GROUPS[group ?? ''] ?? group}</div>}",
      count: 1
    },
    {
      id: 'P14-palette-usage-helper',
      purpose: 'Spanish usage hints: «uso:» and placeholders pinned to the engine English hint',
      file: 'src/lib/desktop-slash-commands.ts',
      find: "export function desktopSlashDescription(command: string, fallback = ''): string {",
      replace:
        '// Janitor build (apps/desktop-janitor/brand/palette.mjs): [engine hint, Spanish hint].\n' +
        `const JANITOR_USAGE_HINTS: Record<string, [string, string] | undefined> = ${usageHintsSource()}\n\n` +
        'function janitorUsageHint(command: string, usage: string): string {\n' +
        '  if (!usage) {\n' +
        "    return ''\n" +
        '  }\n\n' +
        '  const hint = JANITOR_USAGE_HINTS[command]\n\n' +
        '  if (hint && usage.trim() === `(usage: ${command} ${hint[0]})`) {\n' +
        '    return ` (uso: ${command} ${hint[1]})`\n' +
        '  }\n\n' +
        "  return usage.replace('(usage:', '(uso:')\n" +
        '}\n\n' +
        "export function desktopSlashDescription(command: string, fallback = ''): string {",
      count: 1
    },
    {
      id: 'P14-palette-usage-call',
      purpose: 'desktopSlashDescription appends the Spanish usage hint',
      file: 'src/lib/desktop-slash-commands.ts',
      find: "  const usage = fallback.match(/\\s+\\(usage:\\s+(.+)\\)$/s)?.[0] ?? ''",
      replace: "  const usage = janitorUsageHint(canonical, fallback.match(/\\s+\\(usage:\\s+(.+)\\)$/s)?.[0] ?? '')",
      count: 1
    },
    {
      id: 'P14-palette-skill-descs',
      purpose: 'Spanish palette rows for the upstream skills of the Janitor catalog',
      file: 'src/i18n/es.ts',
      find: '    commandDescs: {\n',
      replace: `    commandDescs: {\n${skillDescriptionLines()}`,
      count: 1
    }
  ]
}
