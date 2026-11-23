---
name: janitor-project-create
description: "Monta un proyecto nuevo que compila y pasa sus pruebas."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [projects, scaffold, python, uv, node, typescript, ops, ci, git]
    category: software-development
    related_skills: [spike, test-driven-development, github, systematic-debugging]
---

# Janitor Project Create Skill

Turns a defined idea into a project skeleton that builds and passes its own lint and
tests from the first commit: git on `main`, `.gitignore` that keeps secrets out,
pinned dependencies, formatter + linter, a passing test, GitHub Actions CI, README in
Spanish and an `AGENTS.md`. A script does the scaffolding deterministically in four
steps (`plan` → `apply` → `verify` → optional `publish`). It does not validate ideas
(`spike`), write features (`test-driven-development`) or manage PRs (`github`).

## When to Use

- "Créame un proyecto / repo / esqueleto para X", "monta la estructura de…".
- A spike ended VALIDATED and the user wants the real build.

Not for: an unvalidated idea ("¿esto funcionaría?") → `spike`; adding code to an
existing repo → `test-driven-development`; stacks the script does not support (see
Quick Reference) — say so, never improvise a half skeleton and call it done.

## Prerequisites

- Linux, Python 3.10+ (the script is stdlib only).
- `git` with `user.name` and `user.email` configured. The script never invents an
  identity: without one it stops and gives the user the commands.
- Per type: `uv` (python), `node` ≥ the pinned major plus `npm` or `pnpm` (node),
  `make`, `bash`, `shellcheck` (ops). Missing tools do not block creation; they make
  `verify` report the affected steps as not verified.
- `gh` authenticated (`gh auth status`) only if a remote repository is wanted.

## How to Run

All through the `terminal` tool. `SCRIPT=${HERMES_SKILL_DIR}/scripts/project_create.py`.

```bash
python3 $SCRIPT plan --type python|node|ops [--kind cli|service] --name NAME \
  --target DIR --problem "..." --users "..." --license MIT|Apache-2.0|none \
  [--package-manager auto|npm|pnpm] [--install] \
  [--remote OWNER/NAME --visibility private|public] [--output PLAN.json]
python3 $SCRIPT apply PLAN.json --confirmed
python3 $SCRIPT verify PLAN.json [--install]
python3 $SCRIPT publish PLAN.json --confirmed
```

- `plan` is read-only: prints the plan text (tree, purpose of every file, pinned
  versions, detected tools, every command tagged `local` / `RED`) and writes the plan
  JSON, by default to `$HERMES_HOME/janitor/project-create/`, never inside the target.
- `apply` re-derives the plan from its inputs and refuses if files or commands differ
  (hand-edited or stale plan), refuses a non-empty or symlinked target, creates files
  with no-overwrite / no-follow semantics only inside the target, runs the install only
  if the plan selected it, then `git init --initial-branch=main`, `git add`, `git commit`.
- `verify` runs the project's lint and tests offline in the target and prints JSON:
  `overall` = `passed` | `failed` | `unverified`, `steps[]` with `status`
  (`pass`/`fail`/`not_verified`), `output_tail` or `reason`, and `uncommitted`.
  `--install` first runs the dependency install (network).
- `publish` runs `gh repo create` + `git push` from the plan; refuses without a
  remote in the plan, without commits, or when `origin` already exists.
- Exit codes: 0 ok/passed, 1 a command or check failed, 2 refused (stderr starts with
  `RECHAZADO:`), 3 `verify` unverified.

## Quick Reference

| Type | `--kind` | Stack | Lint / test |
|---|---|---|---|
| `python` | `cli` | uv, `src/` layout, `uv_build`, pytest, ruff, `exclude-newer = "14 days"` | `ruff check`, `ruff format --check`, `pytest` |
| `node` | `cli`, `service` | TypeScript strict (nodenext), `node:test`, Biome, `node:http` for services | `biome check` + `tsc --noEmit`, `tsc && node --test` |
| `ops` | `ops` | Bash scripts (dry-run by default), `scripts/lib/common.sh`, Makefile, `.shellcheckrc`, `.env.example` | `make lint` (ShellCheck), `make test` |

Every type also gets `.editorconfig`, `.gitignore` (secrets block: `.env*`, keys,
`credentials.json`…), `README.md` (Spanish), `AGENTS.md`, `LICENSE` (unless `none`),
`.github/workflows/ci.yml` (actions pinned by SHA, `permissions: contents: read`).

Pins (one file per type): `templates/python-uv/pins.json`,
`templates/node-ts/pins.json`, `templates/ops/pins.json`; action SHAs in
`templates/common/common.json`, copied from this repo's `.github/workflows/`.
Templates are plain files under `templates/<type>/files/` (+ `variants/<kind>/`) with
`{{UPPER_CASE}}` placeholders; `dot-` prefixes become `.`, the `.tmpl` suffix is dropped.

## Procedure

1. **Intake gate — DENEGADO until complete.** Do not run `plan` while any mandatory
   answer is missing. If the request is vague, tear it apart and list exactly what is
   missing, in Spanish. Mandatory (no defaults):
   - the problem it solves, one sentence (`--problem`);
   - who uses it (`--users`);
   - project type and, for `node`, `cli` or `service`;
   - the target directory (must not exist, or be empty) and the project name
     (propose one from the problem; the user confirms it);
   - the licence: `MIT`, `Apache-2.0` or `none` (all rights reserved). Never pick it;
   - whether a remote GitHub repository is wanted (yes → `OWNER/NAME`).
   Defaults, stated in the plan, changeable on request: python `--kind cli`; package
   manager `auto` (npm when present, else pnpm); `--visibility private`.
   Ask about `--install` separately: it downloads from PyPI / npm. Without it there is
   no lockfile in the first commit, CI fails, and `verify` cannot pass; recommend it.
   A stack outside the table (Go, Rust, Django, React app…): say this version does not
   scaffold it; do not fake one. An unproven idea: send it to `spike` first.
2. Run `plan`. Show the user the plan text **verbatim** (tree, purposes, pins,
   commands, warnings). Point out every `RED` line and every warning.
3. Wait for an explicit yes to that plan. Any change → run `plan` again and show the
   new one; never edit the plan JSON by hand (apply refuses it anyway).
4. Run `apply PLAN --confirmed`. Exit 2: report the `RECHAZADO` reason and stop.
   Exit 1: report which command failed with its `output_tail`; files exist, no commit.
5. Run `verify PLAN`. Report every step with its status and, for failures, the real
   `output_tail`. Rules:
   - `passed` is the only state in which the project may be called done.
   - `failed`: fix the cause in the new project (use `systematic-debugging`), commit
     the fix, run `verify` again. Never weaken a test or lint rule to get green.
   - `unverified`: say exactly which steps were not verified and why (tool missing,
     dependencies not installed). The project stays created but flagged
     **sin verificar**. If the reason is missing dependencies and the user agrees to
     the download, run `verify PLAN --install`, then commit the new lockfile.
   - `uncommitted` not empty after a fix: commit it before finishing.
6. **Remote — separate, outward-facing.** Only if the plan has `--remote`, and only
   after showing the two `publish` commands (repo name, visibility, `git push`) and
   getting a new explicit yes for that action: `publish PLAN --confirmed`. Never
   publish an unverified or failing project without the user accepting that state.
   Auth or PR work after that → `github`.
7. Final report in Spanish: path, type, pinned versions, verify result per step, what
   was not verified, commit hash (`git log --oneline -1` via `terminal`), remote URL.

## Pitfalls

- Pins age. Refresh a type by editing its `pins.json` only: pick releases at least
  14 days old (PyPI JSON / `npm view <pkg> time`), keep the ceiling rule (Python
  `<next major`, pre-1.0 `<0.(minor+2)`; Node exact), update `refreshed`, then generate
  that type in a scratch directory with `--install` and require `verify` = `passed`.
  Action SHAs only change by copying them from this repo's workflows.
- `--install` with pnpm may fetch the pnpm version pinned in `packageManager`.
- `uv sync` downloads Python if the pinned version is not installed (plan warns).
- A failed `git commit` (signing, hooks) leaves files without a commit: report it,
  do not retry with `--no-verify` or a different identity.
- `verify` runs `uv run --offline --frozen` / `npm run`; it never downloads.
- Never put tokens, passwords or keys in `--problem` / `--users` or any generated file.

## Verification

- `plan` prints the plan and leaves the target untouched; `apply` + `verify` on a
  scratch target ends with `"overall": "passed"` when the toolchain is installed.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_project_create.py`.
