// Brand rules for the Spanish desktop catalog (patch P6, directive #17).
//
// Applied at build time to apps/desktop/src/i18n/es.ts and reverted after the
// build. The rules only ever see the TEXT inside string and template literals
// that are object VALUES (scripts/ts-literals.mjs) — never object keys,
// identifiers or imports, so keys such as `restartHermes` keep working.
//
// Order matters: protect (allowlist) → rules in order → restore.

export const CATALOG_FILES = ['src/i18n/es.ts']

// Substrings that legitimately keep "hermes". Each one is masked before the
// rules run, restored afterwards, and ignored by the guard test.
export const ALLOWLIST = [
  {
    // Only the example URLs es.ts really keeps. A new URL with "hermes" in it
    // (an upstream install or docs link) is no longer masked, so the guard
    // names it; Nous links without "hermes" are caught by
    // scripts/nous-urls.test.mjs (brand/inventory/nous-urls.tsv).
    id: 'url',
    pattern: /https:\/\/(?:hermes\.example\.com|gateway\.example\.com\/hermes)\b[^\s'"`<>)]*/g,
    reason:
      'Placeholder URLs of the remote-gateway form (https://hermes.example.com, https://gateway.example.com/hermes): example values the user replaces, not the product name.'
  },
  {
    id: 'matrix-id-placeholder',
    pattern: /@hermes:example\.org/g,
    reason: 'Matrix user-ID placeholder; an example value of an external system, not the product name.'
  },
  {
    id: 'path-prefix-placeholder',
    pattern: /(?<=\s)\/hermes\b/g,
    reason: 'Example URL path prefix ("por ejemplo /hermes") for a reverse proxy; it must match what the remote gateway really serves.'
  },
  {
    id: 'plans-dir',
    pattern: /\.hermes\/plans\//g,
    reason: '/plan writes into <project>/.hermes/plans/; the core path is not renamed (directive #1).'
  },
  {
    id: 'hermes-cloud',
    pattern: /Hermes Cloud/g,
    reason: 'Third-party hosted service by Nous Research (plan 2.8); hidden in F1-08, never renamed.'
  },
  {
    id: 'portal-page-name',
    pattern: /Hermes Agent del portal/g,
    reason: 'Name of the page on the Nous Portal (third-party site) that billing admins must open.'
  },
  {
    id: 'env-var',
    pattern: /HERMES_[A-Z_]+/g,
    reason: 'Environment variable names are part of the unrenamed core (directive #1).'
  },
  {
    id: 'protocol-scheme',
    pattern: /hermes:\/\//g,
    reason: 'The deep-link scheme registered by the app is still hermes://.'
  }
]

// Applied in order to the masked text of every catalog value.
export const RULES = [
  {
    id: 'cli-command',
    pattern: /(?<![\w./~@-])hermes(?= [a-z][\w-]*)/g,
    replace: 'janitor',
    reason: 'CLI invocations (`hermes debug share`, hermes curator restore): the user command is `janitor`.'
  },
  {
    id: 'home-dir',
    pattern: /~\/\.hermes\b/g,
    replace: '~/.janitor',
    reason: 'The app and CLI home is ~/.janitor (plan 4.3).'
  },
  {
    id: 'product-compound',
    pattern: /\bHermes (?:Desktop|Agent)\b/g,
    replace: 'Janitor',
    reason: '"Hermes Desktop" / "Hermes Agent" are both just Janitor to the user.'
  },
  {
    id: 'product-name',
    pattern: /\bHermes\b/g,
    replace: 'Janitor',
    reason: 'Product name.'
  },
  {
    id: 'lowercase-prose',
    pattern: /(?<![\w./~@-])hermes\b/g,
    replace: 'janitor',
    reason: 'Lowercase mentions in prose and slash-command help ("salir de hermes").'
  }
]

// What the guard rejects in a transformed catalog value once allowlisted
// substrings are removed.
export const FORBIDDEN = /hermes/i
