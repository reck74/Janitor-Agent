---
name: janitor-repo-research
description: "Investiga un repositorio de GitHub de principio a fin."
version: 2.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [research, github, analysis, documentation, security]
    category: research
---

# janitor-repo-research

End-to-end investigation of a GitHub repository: architecture, stack, code
quality, security and community health. Produces a set of markdown documents and
a self-contained HTML report. No inflated praise: if the project is a mess, the
report says so and shows the evidence. The Investigador profile carries this
skill; the main Janitor agent hands repository due diligence to that profile.

## When to Use

- The user wants to adopt a library or tool and needs to know if it is trash.
- Code quality and architecture review of an open-source project.
- Comparing open-source alternatives.
- Due-diligence report on a dependency before it lands in production.

Input: a GitHub URL or `owner/repo`
(e.g. `investigar repo: https://github.com/NousResearch/hermes-agent`).

## Rules

- NEVER modify the investigated repository. No commits, no pushes, no PRs.
- Work on a shallow clone in a temporary directory or read the remote directly.
- Before cloning or writing anything, tell the user the clone location and the
  report directory. Nothing is written outside those two places.
- Be honest about deficiencies; every finding cites a file path or link.
- Rate limited by the GitHub API → fall back to scraping and state the limits.

## Procedure

### 1. Discovery
Collect metadata (GitHub API, `gh` or scraping): language, license, stars,
forks, contributors, last update, open issues/PRs ratio.

### 2. Deep analysis (in parallel where possible)
- **Arquitectura:** directory layout, entry points, key modules and their
  relationships, data flow.
- **Stack tecnológico:** languages and versions, frameworks, major dependencies,
  build tooling, deployment patterns.
- **Código:** design patterns, duplication and tech debt, quality hotspots, test
  coverage and quality.
- **Seguridad:** vulnerable dependencies (`npm audit`, `pip-audit`, ...),
  hardcoded secrets, insecure configuration, secrets in git history.
- **Comunidad:** commit cadence, issue response time, contributor diversity,
  documentation completeness.

When the deepwiki MCP tool is available, use it to check whether a pattern is
idiomatic or to compare with other popular projects; if it is not, note it and
continue.

### 3. Synthesis
Write the report to `${HERMES_HOME:-~/.janitor}/docs/<project-name>/`:

| File | Content |
|---|---|
| `_index.md` | Master navigation |
| `_resumen.md` | Executive summary |
| `analisis/_metadata.md` | GitHub stats |
| `analisis/arquitectura.md` | Architecture |
| `analisis/stack.md` | Technology stack |
| `analisis/dependencias.md` | Dependencies |
| `analisis/patrones.md` | Design patterns |
| `evaluacion/calidad.md` | Code quality |
| `evaluacion/seguridad.md` | Security |
| `evaluacion/docs.md` | Documentation |
| `evaluacion/community.md` | Community |
| `reporte.html` | Visual report |

Each markdown file follows `${HERMES_SKILL_DIR}/references/research-template.md`
(checklists included) and ends with:

```
## Recomendaciones

1. [Acción concreta] — [Por qué importa]
2. [Acción concreta] — [Por qué importa]
```

`reporte.html` follows `${HERMES_SKILL_DIR}/design.md`: all CSS inline, no
external dependencies, responsive, printable, navigation between sections,
highlighted code blocks.

## Error Handling

| Situation | Response |
|---|---|
| Repository missing or private | Clear error, nothing written |
| Rate limited | Fall back to scraping, note the limitation |
| Empty repository | Partial report with the limitations stated |
| deepwiki unavailable | Warn and continue |

## Verification

- `_index.md` links to every generated file and none is empty.
- `reporte.html` opens offline (no external URLs in `<link>` / `<script>`).
- The investigated checkout has no local changes (`git status --porcelain` empty).
