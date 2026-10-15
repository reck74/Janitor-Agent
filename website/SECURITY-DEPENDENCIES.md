# Website dependency review — 2026-10-15

The website has its own npm lock and audit scope. Janitor Desktop's application audit does not certify this toolchain. `npm ci` succeeds with the checked-in lock. The current website audit reports **0 critical, 30 high, 0 moderate and 3 low** affected package entries. These are **two distinct advisories**, propagated through dependent package entries; they must not be described as 30 separate vulnerabilities or as a clean audit.

## Temporary build dependency exception

[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) affects braces through 3.0.3. The official advisory currently lists no patched release. Deeply nested glob patterns can exhaust the Node call stack. This repository receives braces through Docusaurus's file matching/build/watch dependencies. It is not a Janitor Python runtime dependency.

The exception is limited to **braces 3.0.3**, expires **2026-10-29**, and is machine-readable in `security-exceptions.json`. The CI checker resolves transitive entries to the reviewed advisory and fails on any new high/critical advisory, version drift, malformed report or expired exception. It preserves the raw audit count instead of suppressing findings.

Mitigations: build only reviewed repository configuration/globs; keep PR builds on isolated, time-limited runners without deployment credentials; publish only the generated static `build/` directory; do not expose `docusaurus start` or webpack's development server to the public network. Repository contributors who can alter build code already execute within the isolated CI trust boundary. This assessment is specific to that build workflow and does not claim that braces is safe for arbitrary user-provided patterns.

Before expiry, check the maintainer release/advisory again. Prefer a compatible upstream patch and rebuild. Do not use `npm audit fix --force`, replace Docusaurus with an unrelated old version or erase the exception deadline to obtain a green badge.

## Low-severity rendering advisory

[GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7) affects KaTeX below 0.18.2. Exploitation requires prior prototype pollution or attacker-controlled option prototypes, mathematical input and unsanitized insertion of the output. Mermaid pulls the older KaTeX branch; the application keeps default untrusted rendering and the patched DOMPurify dependency. A KaTeX 0.18.2 override crosses Mermaid's declared dependency contract and must be validated separately with mathematical/diagram rendering before adoption. These three low-severity dependent package entries remain visible in npm audit.

## Reproducibility and major-version overrides

The lock pins security updates including Tinypool 2.1.2, postcss-selector-parser 7.1.6, serialize-javascript 7.0.7, uuid 14.0.1 and minimatch 10.2.6. Docusaurus's use of Tinypool (constructor, run and destroy) was checked against its installed API; real static generation is the integration gate. `npm ci`, typecheck and the bilingual production build validate the override set rather than trusting version numbers alone.

The global 14-day npm release quarantine remains enabled. The sole newly added name exception is `http-cache-semantics`, pinned to 4.3.0 for [GHSA-ch52-4w7c-c8xp](https://github.com/advisories/GHSA-ch52-4w7c-c8xp); remove it after 2026-10-18. npm's exclusion matcher accepts package names, while the exact version is enforced by package.json and package-lock.json.

To reproduce:

```bash
cd website
npm ci
audit_report=$(mktemp)
npm audit --json > "$audit_report"
python ../scripts/ci/janitor_website_audit.py "$audit_report"
rm -f "$audit_report"
npm run typecheck
DOCUSAURUS_SSR_CONCURRENCY=2 DOCUSAURUS_SSG_WORKER_THREAD_COUNT=2 npm run build
```

`npm audit` intentionally exits nonzero while the known advisories remain. Evaluate its complete JSON through the explicit checker; do not ignore network errors or unknown findings.
