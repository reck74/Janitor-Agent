---
name: janitor-file-organizer
description: "Organize a messy folder by type or date, with undo."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [files, organize, downloads, undo, linux, system]
    category: system
    related_skills: [janitor-cleanup]
---

# Janitor File Organizer Skill

Puts one messy directory (Downloads, Desktop, a dumping-ground folder) in order. A
read-only `plan` classifies its files and proposes moves into subfolders; `apply`
performs only the confirmed moves as same-filesystem renames that never overwrite and
writes a write-ahead undo journal; `undo` restores the original tree. Nothing is deleted:
duplicates are only reported.

## When to Use

- The user asks to tidy, sort or organize a folder.
- Not for freeing space (use `janitor-cleanup`) and never on the whole home.

## Prerequisites

- Linux, `python3` (stdlib only), optional `git` (a folder inside a git work tree with
  uncommitted/unpushed work is refused; without `git` every work tree counts as dirty).

## How to Run

Every command goes through `terminal`. `${HERMES_SKILL_DIR}` is this skill's directory.

```bash
O=${HERMES_SKILL_DIR}/scripts/janitor_organize.py
python3 $O plan ~/Downloads                     # top level only, by type
python3 $O plan ~/Downloads --by type-date      # Documentos/2026/...
python3 $O plan ~/Escritorio --by date          # 2026/2026-11/...
python3 $O plan ~/Downloads --recursive         # also subfolders (not hidden, not projects)
python3 $O summary PLAN                         # summary + current DIGEST
python3 $O apply PLAN --confirm DIGEST          # only after the user said yes
python3 $O undo PLAN_BASE.undo.jsonl            # restore everything apply moved
```

Plans land in `<agent home>/janitor-plans/` unless `--out` is given; the undo journal
(`<plan>.undo.jsonl`) is written next to the plan.

## Quick Reference

| Type | Folder |
|---|---|
| pdf, office, text, ebooks | `Documentos/` |
| images | `Imagenes/` |
| video / audio | `Videos/` / `Audio/` |
| zip, tar.*, 7z, rar | `Comprimidos/` |
| AppImage, deb, rpm, `.pkg.tar.zst`, iso, exe | `Instaladores/` |
| source files, notebooks | `Codigo/` |
| csv, json, yaml, sqlite, parquet | `Datos/` |
| anything else | `Otros/` |

Never moved: hidden files (unless `--include-hidden`), partial downloads (`.part`,
`.crdownload`, ...), symlinks, files on another filesystem, and in recursive mode
hidden folders, the category folders themselves, and any folder that is a project or
repository (`.git`, `package.json`, `pyproject.toml`, `Cargo.toml`, `Makefile`, ...).

## Procedure

1. Run `plan` on the ONE folder the user named. Recursive only if they asked.
2. Optional smarter grouping: the plan is plain JSON. You may edit `dst` values with
   `patch` (e.g. group invoices of one supplier, a project's assets) as long as every
   `dst` stays inside the same folder and outside hidden subfolders; set
   `"selected": false` to leave a file alone. Then run `summary` to get the new DIGEST.
3. Show the user, in Spanish: moves per target folder with examples, every collision
   rename, the duplicate groups (report only), the notes (projects left alone, partial
   downloads, incomplete scan) and the excluded count.
4. HARD RULE: no `apply` without the user's explicit confirmation of THAT plan; any edit
   changes the DIGEST and needs a new confirmation. Never apply moves the user did not see.
5. Run `apply PLAN --confirm DIGEST` (only `plan` and `summary` print the DIGEST; a
   mismatch error never reveals it). Report exactly what moved, what was renamed on
   collision, what was skipped and why, and the `undo` command.

## Pitfalls

- `apply` re-validates every entry: source still inside the folder, unchanged
  (size+mtime+inode), not protected (same denylist as `janitor-cleanup`: secrets,
  keyrings, browser profiles, VM images, the agent home, `.git`, dirty repos), not a
  symlink; destination inside the folder, not through a symlink, same filesystem.
  Failures are skipped and listed.
- Collisions never overwrite: the file gets ` (2)`, ` (3)`, ... and the summary says so.
- Moves across filesystems are refused, not copied. Applying the same plan twice is
  refused (the undo journal already exists).
- `undo` only removes folders that `apply` created, and only if empty.
- The undo journal is write-ahead: every move and every created folder is recorded and
  fsynced BEFORE it happens. After a crash, `undo` checks the filesystem for the last
  unfinished move (moved → moves it back; not moved → leaves it). It never overwrites
  a file that now occupies an original path (skipped and reported), and it can be
  re-run safely. If the journal cannot be written, `apply` stops before the next move.

## Verification

- After `apply`, `search_files target='files'` on the folder shows the new layout and
  the undo journal exists next to the plan.
- `undo` prints `Restaurados: N archivos` with N equal to the moved count and leaves the
  original tree.
