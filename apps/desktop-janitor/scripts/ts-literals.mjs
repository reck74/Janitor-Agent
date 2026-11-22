// Minimal, dependency-free TypeScript/JavaScript lexer used by the brand layer.
//
// It does not build an AST. It finds every string and template literal, tells
// object keys apart from values, and gives each value a key path
// (`settings.updates.title`, `slash./quit`, `list[2]`). That is enough to
// rewrite only the text inside literals and to prove nothing else changed.
// The desktop-overlay CI job has no node_modules, so this cannot lean on
// typescript or esbuild.

const IDENT_START = /[A-Za-z_$À-￿]/
const IDENT_PART = /[A-Za-z0-9_$À-￿]/
const REGEX_PREFIX_KEYWORDS = new Set(['return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw', 'yield', 'await'])

/**
 * Tokenize `source`. Tokens: { type, start, end, value? }.
 *   type 'string'   — quoted literal; `inner` = [start, end) of its body
 *   type 'template' — template literal; `chunks` = [[start, end), ...] of its
 *                     literal text, `exprs` = tokens inside each `${}`
 *   type 'ident' | 'number' | 'punct' | 'regex'
 * Comments and whitespace are skipped.
 */
export function tokenize(source) {
  let i = 0

  function readTemplate() {
    // At the opening backtick.
    const start = i
    const chunks = []
    const exprs = []
    i++
    let chunkStart = i

    while (i < source.length) {
      const ch = source[i]

      if (ch === '\\') {
        i += 2
        continue
      }

      if (ch === '`') {
        chunks.push([chunkStart, i])
        i++

        return { type: 'template', start, end: i, chunks, exprs }
      }

      if (ch === '$' && source[i + 1] === '{') {
        chunks.push([chunkStart, i])
        i += 2
        exprs.push(readUntilClosingBrace())
        chunkStart = i
        continue
      }

      i++
    }

    throw new Error(`unterminated template literal at offset ${start}`)
  }

  function readUntilClosingBrace() {
    // Inside `${ ... }`: lex tokens until the matching `}`.
    const tokens = []
    let depth = 0

    for (;;) {
      const token = next(tokens)

      if (!token) {
        throw new Error('unterminated template expression')
      }

      if (token.type === 'punct' && token.value === '{') depth++

      if (token.type === 'punct' && token.value === '}') {
        if (depth === 0) {
          return tokens
        }

        depth--
      }

      tokens.push(token)
    }
  }

  function regexAllowed(prev) {
    if (!prev) return true
    if (prev.type === 'ident') return REGEX_PREFIX_KEYWORDS.has(prev.value)
    if (prev.type === 'punct') return !/^[)\]}]$/.test(prev.value)

    return false
  }

  function next(context) {
    for (;;) {
      if (i >= source.length) return null
      const ch = source[i]

      if (/\s/.test(ch)) {
        i++
        continue
      }

      if (ch === '/' && source[i + 1] === '/') {
        const nl = source.indexOf('\n', i)
        i = nl === -1 ? source.length : nl
        continue
      }

      if (ch === '/' && source[i + 1] === '*') {
        const close = source.indexOf('*/', i + 2)

        if (close === -1) throw new Error(`unterminated comment at offset ${i}`)
        i = close + 2
        continue
      }

      break
    }

    const start = i
    const ch = source[i]

    if (ch === '"' || ch === "'") {
      i++

      while (i < source.length && source[i] !== ch) {
        if (source[i] === '\\') i++
        if (source[i] === '\n') throw new Error(`unterminated string literal at offset ${start}`)
        i++
      }

      i++

      return { type: 'string', start, end: i, quote: ch, inner: [start + 1, i - 1] }
    }

    if (ch === '`') {
      return readTemplate()
    }

    if (IDENT_START.test(ch)) {
      while (i < source.length && IDENT_PART.test(source[i])) i++

      return { type: 'ident', start, end: i, value: source.slice(start, i) }
    }

    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(source[i + 1] || ''))) {
      while (i < source.length && /[0-9A-Za-z_.]/.test(source[i])) i++

      return { type: 'number', start, end: i, value: source.slice(start, i) }
    }

    const prev = context[context.length - 1]

    if (ch === '/' && regexAllowed(prev)) {
      i++
      let inClass = false

      while (i < source.length) {
        const c = source[i]

        if (c === '\\') {
          i += 2
          continue
        }

        if (c === '\n') throw new Error(`unterminated regex at offset ${start}`)
        if (c === '[') inClass = true
        else if (c === ']') inClass = false
        else if (c === '/' && !inClass) break
        i++
      }

      i++
      while (i < source.length && /[a-z]/.test(source[i])) i++

      return { type: 'regex', start, end: i, value: source.slice(start, i) }
    }

    for (const op of ['...', '=>', '?.', '??', '&&', '||', '===', '!==', '==', '!=', '<=', '>=']) {
      if (source.startsWith(op, i)) {
        i += op.length

        return { type: 'punct', start, end: i, value: op }
      }
    }

    i++

    return { type: 'punct', start, end: i, value: ch }
  }

  const tokens = []

  for (;;) {
    const token = next(tokens)

    if (!token) return tokens
    tokens.push(token)
  }
}

function keyName(source, token) {
  if (token.type === 'string') return source.slice(token.inner[0], token.inner[1])

  return token.value
}

/**
 * Walk the tokens and classify every literal.
 * Returns { keys: [{ path, start, end }], values: [literal] } where a literal
 * is { path, kind, start, end, segments: [[start, end), ...] } and `segments`
 * are the raw source ranges holding user text (string body / template chunks).
 */
export function classifyLiterals(source) {
  const tokens = tokenize(source)
  const keys = []
  const values = []
  const seen = new Map()

  function uniquePath(path) {
    const n = seen.get(path) ?? 0
    seen.set(path, n + 1)

    return n === 0 ? path : `${path}~${n + 1}`
  }

  function join(parts) {
    return parts.filter(Boolean).join('.').replace(/\.\[/g, '[')
  }

  function walk(list, basePath) {
    // frames: { kind: '{' | '[' | '(', key: string|null, index: number, path: string[] }
    const frames = [{ kind: 'root', key: null, index: 0, path: basePath }]

    const current = () => frames[frames.length - 1]

    const pathHere = () => {
      const frame = current()

      if (frame.kind === '{') return [...frame.path, frame.key]
      if (frame.kind === '[') return [...frame.path, `[${frame.index}]`]

      return frame.path
    }

    for (let k = 0; k < list.length; k++) {
      const token = list[k]
      const prev = list[k - 1]
      const nextToken = list[k + 1]
      const frame = current()

      if (token.type === 'punct') {
        if (token.value === '{' || token.value === '[' || token.value === '(') {
          frames.push({ kind: token.value, key: null, index: 0, path: pathHere() })
        } else if (token.value === '}' || token.value === ']' || token.value === ')') {
          if (frames.length > 1) frames.pop()
        } else if (token.value === ',') {
          if (frame.kind === '{') frame.key = null
          if (frame.kind === '[') frame.index++
        }

        continue
      }

      const isKey =
        frame.kind === '{' &&
        (token.type === 'ident' || token.type === 'string' || token.type === 'number') &&
        nextToken?.type === 'punct' &&
        nextToken.value === ':' &&
        prev?.type === 'punct' &&
        (prev.value === '{' || prev.value === ',')

      if (isKey) {
        frame.key = keyName(source, token)
        keys.push({ path: join([...frame.path, frame.key]), start: token.start, end: token.end })
        continue
      }

      const isModuleSpecifier =
        token.type === 'string' &&
        ((prev?.type === 'ident' && (prev.value === 'from' || prev.value === 'import')) ||
          (prev?.type === 'punct' && prev.value === '(' && list[k - 2]?.type === 'ident' && ['import', 'require'].includes(list[k - 2].value)))

      if (isModuleSpecifier) continue

      if (token.type === 'string') {
        values.push({
          path: uniquePath(join(pathHere())),
          kind: 'string',
          start: token.start,
          end: token.end,
          segments: [token.inner]
        })
      } else if (token.type === 'template') {
        const path = uniquePath(join(pathHere()))
        values.push({ path, kind: 'template', start: token.start, end: token.end, segments: token.chunks })

        for (const expr of token.exprs) {
          walk(expr, pathHere())
        }
      }
    }
  }

  walk(tokens, [])

  return { keys, values, tokens }
}

/** The user-visible text of a literal, with `${…}` standing in for interpolations. */
export function literalText(source, literal) {
  return literal.segments.map(([s, e]) => source.slice(s, e)).join('${…}')
}

/**
 * Every non-literal token as text. Two sources whose skeletons are equal
 * differ only inside literal text: same keys, identifiers, imports, structure.
 */
export function skeleton(source) {
  const out = []

  function emit(list) {
    for (const token of list) {
      if (token.type === 'string') out.push('<str>')
      else if (token.type === 'template') {
        out.push('<tpl>')
        for (const expr of token.exprs) emit(expr)
        out.push('</tpl>')
      } else out.push(source.slice(token.start, token.end))
    }
  }

  emit(tokenize(source))

  return out
}

/**
 * Rewrite the text segments of selected literals. `rewrite(text, literal)`
 * returns the new raw text for one segment. Segments never overlap, so a
 * right-to-left splice keeps every offset valid.
 */
export function rewriteLiterals(source, literals, rewrite) {
  const edits = []

  for (const literal of literals) {
    for (const [s, e] of literal.segments) {
      const before = source.slice(s, e)
      const after = rewrite(before, literal)

      if (after !== before) edits.push([s, e, after])
    }
  }

  edits.sort((a, b) => b[0] - a[0])
  let out = source

  for (const [s, e, text] of edits) {
    out = out.slice(0, s) + text + out.slice(e)
  }

  return out
}
