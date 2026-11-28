// The signed manifest of a Janitor release (plan Fase 9, F9-01).
//
//   node update-manifest.mjs build  --version <0.21.5-janitor.4> --commit <sha> --out <dir> <file>...
//   node update-manifest.mjs sign   --manifest <janitor-update.json> --key-env <NAME>
//   node update-manifest.mjs verify --manifest <file> --signature <file> --public-key <pem> [--dir <dir>]
//   node update-manifest.mjs keygen --out <dir>          # a throwaway pair, for tests and rehearsals only
//
// `build` writes janitor-update.json: version, tag, engine commit, delivery
// number and, per installer, name, size and SHA-256. `sign` writes
// janitor-update.json.sig, the base64 of the Ed25519 signature over the
// manifest's exact bytes. The private key is read from the environment variable
// NAMED by --key-env (PEM, PKCS#8) and from nowhere else: it never appears on a
// command line or in a file this script writes. `verify` checks the signature
// with the public key and, with --dir, that every listed file is there with the
// signed size and sum: the release workflow runs it on what it is about to
// publish, with the public key committed in brand/update-key.pem.
//
// The layout is fixed on purpose — one file entry per line, exactly
//     {"name": "<name>", "size": <bytes>, "sha256": "<64 hex>"}
// — because the Arch updater (packaging/arch/janitor-update-helper, root) reads
// its entry by that line instead of carrying a JSON parser.

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  JanitorUpdateError,
  MANIFEST_NAME,
  MANIFEST_SCHEMA,
  SIGNATURE_NAME,
  hashFile,
  sequenceForVersion,
  tagForVersion,
  verifyManifest
} from '../brand/app-update.mjs'

const COMMIT_RE = /^[0-9a-f]{40}$/
const FILE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/

/** The manifest text for `files` ([{ name, size, sha256 }]), in the fixed layout. */
export function renderManifest({ version, commit, files }) {
  const tag = tagForVersion(version)

  if (!COMMIT_RE.test(commit ?? '')) throw new Error(`commit must be 40 lowercase hex digits, got ${JSON.stringify(commit)}`)
  if (!Array.isArray(files) || files.length === 0) throw new Error('a manifest needs at least one file')

  const seen = new Set()

  const lines = [...files]
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .map(file => {
      if (!FILE_NAME_RE.test(file.name)) throw new Error(`file name not allowed in a manifest: ${JSON.stringify(file.name)}`)
      if (seen.has(file.name)) throw new Error(`file listed twice: ${file.name}`)
      if (!Number.isSafeInteger(file.size) || file.size <= 0) throw new Error(`bad size for ${file.name}`)
      if (!/^[0-9a-f]{64}$/.test(file.sha256)) throw new Error(`bad sha256 for ${file.name}`)

      seen.add(file.name)

      return `    {"name": "${file.name}", "size": ${file.size}, "sha256": "${file.sha256}"}`
    })

  return [
    '{',
    `  "schema": ${MANIFEST_SCHEMA},`,
    `  "version": "${version}",`,
    `  "tag": "${tag}",`,
    `  "commit": "${commit}",`,
    `  "sequence": ${sequenceForVersion(version)},`,
    '  "files": [',
    lines.join(',\n'),
    '  ]',
    '}',
    ''
  ].join('\n')
}

/** Hash `paths` and write <outDir>/janitor-update.json. Returns its path. */
export async function buildManifest({ version, commit, paths, outDir }) {
  const files = []

  for (const file of paths) {
    files.push({ name: path.basename(file), ...(await hashFile(file)) })
  }

  const manifestPath = path.join(outDir, MANIFEST_NAME)

  fs.mkdirSync(outDir, { recursive: true })
  fs.writeFileSync(manifestPath, renderManifest({ version, commit, files }))

  return manifestPath
}

/** Ed25519 signature of the manifest's bytes with a PEM private key; writes <manifest>.sig. */
export function signManifest({ manifestPath, privateKeyPem }) {
  const key = crypto.createPrivateKey(privateKeyPem)

  if (key.asymmetricKeyType !== 'ed25519') throw new Error(`the signing key must be Ed25519, got ${key.asymmetricKeyType}`)

  const signaturePath = path.join(path.dirname(manifestPath), SIGNATURE_NAME)

  fs.writeFileSync(signaturePath, `${crypto.sign(null, fs.readFileSync(manifestPath), key).toString('base64')}\n`)

  return signaturePath
}

/** Signature, then (with `dir`) every listed file's size and sum. Returns the manifest. */
export async function verifyRelease({ manifestPath, signaturePath, publicKeyPem, dir = null }) {
  const manifest = verifyManifest({
    bytes: fs.readFileSync(manifestPath),
    signatureText: fs.readFileSync(signaturePath, 'utf8'),
    publicKeyPem
  })

  if (dir) {
    for (const file of manifest.files) {
      const got = await hashFile(path.join(dir, file.name)).catch(() => null)

      if (!got) throw new Error(`${file.name}: listed in the manifest but missing from ${dir}`)
      if (got.size !== file.size || got.sha256 !== file.sha256) throw new Error(`${file.name}: does not match the signed manifest`)
    }
  }

  return manifest
}

/** A throwaway Ed25519 pair as PEM text. Never used for a real release. */
export function generateTestKeyPair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519')

  return {
    publicKeyPem: publicKey.export({ type: 'spki', format: 'pem' }),
    privateKeyPem: privateKey.export({ type: 'pkcs8', format: 'pem' })
  }
}

function options(argv, known) {
  const out = { _: [] }

  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) {
      out._.push(argv[i])
      continue
    }

    const key = argv[i].slice(2)

    if (!known.includes(key) || argv[i + 1] === undefined) throw new Error(`unknown or incomplete option ${argv[i]}`)

    out[key] = argv[(i += 1)]
  }

  for (const key of known) {
    if (key !== 'dir' && !out[key]) throw new Error(`missing --${key}`)
  }

  return out
}

async function main([command, ...argv]) {
  if (command === 'build') {
    const args = options(argv, ['version', 'commit', 'out'])
    const manifestPath = await buildManifest({ version: args.version, commit: args.commit, paths: args._, outDir: args.out })

    process.stdout.write(fs.readFileSync(manifestPath, 'utf8'))
  } else if (command === 'sign') {
    const args = options(argv, ['manifest', 'key-env'])
    const privateKeyPem = process.env[args['key-env']]

    if (!privateKeyPem) throw new Error(`the environment variable ${args['key-env']} is empty: no signing key`)

    console.log(`signed → ${signManifest({ manifestPath: args.manifest, privateKeyPem })}`)
  } else if (command === 'verify') {
    const args = options(argv, ['manifest', 'signature', 'public-key', 'dir'])

    const manifest = await verifyRelease({
      manifestPath: args.manifest,
      signaturePath: args.signature,
      publicKeyPem: fs.readFileSync(args['public-key'], 'utf8'),
      dir: args.dir ?? null
    })

    console.log(`signature valid: ${manifest.tag} @ ${manifest.commit}, delivery ${manifest.sequence}, ${manifest.files.length} file(s)${args.dir ? ' checked' : ''}`)
  } else if (command === 'keygen') {
    const args = options(argv, ['out'])
    const pair = generateTestKeyPair()

    fs.mkdirSync(args.out, { recursive: true })
    fs.writeFileSync(path.join(args.out, 'test-update-key.pem'), pair.publicKeyPem)
    fs.writeFileSync(path.join(args.out, 'test-update-key.private.pem'), pair.privateKeyPem, { mode: 0o600 })
    console.log(`throwaway test key pair in ${args.out} (never use it for a release)`)
  } else {
    throw new Error('usage: update-manifest.mjs build|sign|verify|keygen ... (see the header of this file)')
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => {
    console.error(error instanceof JanitorUpdateError ? `${error.code}: ${error.message}` : error.message)
    process.exit(1)
  })
}
