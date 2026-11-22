---
name: janitor-cleanup
description: "Reclaim disk space on Linux with a plan sent to Trash."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [cleanup, disk, cache, trash, linux, system]
    category: system
    related_skills: [janitor-file-organizer]
---

# Janitor Cleanup Skill

Finds reclaimable disk space on the user's Linux workstation and frees it in two
phases: a read-only `plan` that writes a JSON plan, and an `apply` that executes only
the entries of that plan the user confirmed. Files go to the freedesktop.org Trash,
regenerable caches are cleared with the owning tool's own command, and anything that
needs root is only suggested. Nothing is ever deleted directly and `sudo` is never run.

## When to Use

- The user asks to free space, clean the machine, or find what is eating the disk.
- A health check reports a full or nearly full home filesystem.
- Not for organizing folders (use `janitor-file-organizer`) and not for the agent's own
  temporary files.

## Prerequisites

- Linux, `python3` (stdlib only). Optional: `gio` (preferred Trash backend), `git`
  (without it every git work tree is treated as dirty and left alone), the tools whose
  caches are measured (`pip`, `uv`, `npm`, `yarn`, `pnpm`, `go`, `cargo-cache`,
  `docker`, `trash-empty`, `journalctl`). The script detects each one; it never assumes.

## How to Run

Every command goes through `terminal`. `${HERMES_SKILL_DIR}` is this skill's directory.

```bash
S=${HERMES_SKILL_DIR}/scripts/janitor_cleanup.py
python3 $S plan                                    # read-only; prints summary + DIGEST
python3 $S plan --categories tool-cache,docker     # only some categories
python3 $S select PLAN --ids 12,40                 # user picked these report-only items
python3 $S select PLAN --risk review               # mark every review item (not report-only)
python3 $S select PLAN --ids 7 --off               # unmark
python3 $S summary PLAN                            # summary + current DIGEST
python3 $S apply PLAN --confirm DIGEST             # only after the user said yes
python3 $S restore JOURNAL                         # undo an apply (JOURNAL is printed by apply)
```

The plan lands in `<agent home>/janitor-plans/` unless `--out` is given. Read it with
`read_file` when the summary is not enough.

## Quick Reference

| Category | What | Removal | Default |
|---|---|---|---|
| `pkg-cache` | pacman/apt/dnf package caches | privileged suggestion (`sudo paccache -rk2`, `sudo apt-get clean`, `sudo dnf clean packages`) | never run |
| `tool-cache` | pip, uv, npm, yarn, pnpm, go build/mod, cargo, Gradle, Maven, old Playwright browsers, HuggingFace (suggestion only) | tool command or Trash | safe ones marked |
| `user-cache` | `~/.cache` entries untouched for `--cache-days` (30) | Trash | marked |
| `thumbnails` | `~/.cache/thumbnails` | Trash | marked |
| `trash-old` | Trash items older than `--trash-days` (30) | `trash-empty N` (permanent) or suggestion | unmarked |
| `logs` | `*.log*` under XDG dirs older than `--log-days`; user journal size | Trash; `journalctl --user --vacuum-time=` suggestion | unmarked |
| `docker` | dangling images, stopped containers, build cache. Volumes NEVER | `docker image/container/builder prune -f` | containers unmarked |
| `build-artifacts` | `node_modules`, `target`, `.venv`, `__pycache__`, `dist`, `build` in projects untouched `--project-days` (60), git-ignored, repo clean and pushed | Trash | `.venv`/`dist`/`build` unmarked |
| `large-files` | files ≥ `--large-mb` (500) | Trash, report only | user picks by id |
| `old-downloads` | Downloads older than `--downloads-days` (90) | Trash, report only | user picks by id |
| `duplicates` | identical files ≥ `--dup-min-mb` (size → 64 KiB hash → full hash) | Trash, report only | user picks by id |

Risk: `safe` = regenerable; `review` = the user decides. Budgets: `--max-seconds`
(180), `--max-files` (1,000,000); a hit is printed as `AVISO: escaneo incompleto`.

## Procedure

1. Run `plan` (all categories unless the user narrowed it). Never pass `--root` outside
   the home unless the user named that path.
2. Show the user, in Spanish: totals per category, the marked items with the largest
   first, the report-only candidates, every privileged or manual suggestion as a
   separate block with its exact command, the notes (Docker volumes, incomplete scan,
   excluded count) and that Trash frees space only once it is emptied.
3. HARD RULE: no `apply` without the user's explicit confirmation of THAT plan. Adjust
   it first with `select` (report-only and duplicate items are only marked by explicit
   id, one copy at a time; never choose which duplicate to keep for the user). Any
   `select` changes the DIGEST: show the new summary and confirm again. Never apply a
   subset or superset the user did not see.
4. Run `apply PLAN --confirm DIGEST`. There is no flag that skips the plan or the digest.
   Only `plan` and `summary` print the DIGEST; a mismatch error never reveals it, so
   the only way to get it is to print the plan for the user.
5. Report exactly: what went to the Trash (paths, size), which commands ran and their
   exit codes, what was skipped and why (changed since the plan, now protected, no
   compliant trash on that filesystem), and how to restore: `restore JOURNAL`, or the
   desktop's Trash. Privileged suggestions are for the user to run; never run `sudo`.

## Pitfalls

- The plan is never trusted: `apply` re-checks every path against the roots, the
  denylist (`~/.ssh`, `~/.gnupg`, password stores, keyrings, browser and mail profiles,
  VM storage, cloud credentials, the Trash, the agent home, any directory holding a
  `SOUL.md` + `config.yaml`), symlinks leaving the roots, other filesystems, `.git`
  metadata, git work trees with uncommitted/unpushed/stashed work and the size+mtime
  fingerprint. Anything that fails is skipped, not forced.
- Tool commands come from a fixed table; a hand-edited command in the plan is refused.
- `apply` keeps a write-ahead journal (`<plan>.journal-<time>.jsonl`, fsynced): each
  action is recorded before it runs. If the process dies mid-run, `restore JOURNAL`
  still finds every trashed item through its `.trashinfo`. If the journal cannot be
  written, `apply` stops before touching anything else.
- A file on a filesystem without a spec-compliant Trash is skipped; there is no delete
  fallback. Moving to the Trash does not free space until the Trash is emptied.
- `trash-old` and `docker-containers` are permanent: always `review`, never default.
- A home that is itself a git work tree with uncommitted changes blocks every path in
  it. Report it; do not work around it.

## Verification

- `apply` prints `A la papelera: N elementos` and `Omitidos: M` with reasons, plus a
  `Diario:` journal file. Confirm with `search_files target='files'` on
  `~/.local/share/Trash/files` that the items are there.
- `python3 $S restore JOURNAL` puts every trashed item back at its original path.
