---
name: janitor-maintenance
description: "Revisión programada del equipo que dice qué cambió."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [system, maintenance, cron, health, report, linux]
    category: devops
    related_skills: [janitor-system-health, janitor-cleanup]
---

# Janitor Maintenance Skill

Sets up, on request, a recurring cron job (weekly by default) that runs the
`janitor-system-health` audit, compares it with the previous run and delivers a short
Spanish report: what got worse, what is new, what was fixed and what still stands. The
scheduled run is report-only: it never applies a fix. Fixes happen later, in an
interactive session, with the user's confirmation.

## When to Use

- "Check my machine every week and tell me what changed."
- "Pause / change / remove the maintenance report."
- A cron tick of the job created here (the prompt below invokes this skill).
- A manual "what changed since last time?" outside the schedule.

Never create the job unless the user asked for it.

## Prerequisites

- `janitor-system-health` in the same install tree (the run script finds
  `../janitor-system-health/scripts/system_health.py` next to this skill).
- This skill active in the profile, so the job can load it by name.
- A running scheduler. Cron jobs fire only while a gateway ticks: the gateway service
  (`janitor gateway install`, or `janitor gateway` in the foreground) or the desktop
  app's backend, which runs the ticker while the app is open. `janitor cron status`
  says whether it is alive; a closed app plus no gateway means overdue jobs.
- `cronjob_manage` is available in interactive sessions (CLI, TUI, desktop app) and on
  messaging platforms; `janitor cron …` is the same scheduler from a shell.

## How to Run

The job and manual runs execute one script with the `terminal` tool:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/maintenance_run.py
```

- Runs the read-only audit, diffs it against `last.json`, rotates `last.json` →
  `previous.json`, saves the new report as `last.json` and prints the diff JSON.
- State lives in `$HERMES_HOME/janitor/system-health/` — the active profile's home,
  exported to the agent's terminal and to cron runs. Never hardcode a home path.
- `--no-save` compares without touching the state (use it for ad-hoc checks so the
  weekly baseline is not reset). `--compare OLD NEW` diffs two saved reports.
- `--skip docker,home_usage` passes probe exclusions to the audit.
- Exit 0 on success; exit 2 when `HERMES_HOME` is unset (pass `--state-dir`), the audit
  script is missing or failed, or the state directory is not writable.

Diff JSON: `first_run`, `previous_generated_at`, `current_generated_at`, `summary`,
`skipped`, `counts`, and the lists `worse`, `new`, `fixed`, `improved`, `still_open`,
`not_verified`. Entries carry `id`, `severity` (`previous_severity` when it changed),
`title`, `evidence`, `suggested_fix`, `requires_privileges`. `info` findings are
context and never appear in the lists. A finding that disappeared while its probe was
skipped goes to `not_verified`, never to `fixed`.

## Quick Reference

Create (only on request). Agent tool:

```text
cronjob_manage(action="create", name="janitor-mantenimiento",
  schedule="every monday 9am", skills=["janitor-maintenance"],
  enabled_toolsets=["terminal"], deliver="<see Delivery>",
  prompt="<job prompt below>")
```

Same from the CLI (the CLI has no `enabled_toolsets` flag):

```bash
janitor cron create "every monday 9am" "<job prompt>" --skill janitor-maintenance --name janitor-mantenimiento --deliver telegram
```

Job prompt (self-contained — the run has no chat context):

```text
Ejecuta el mantenimiento programado de Janitor siguiendo la skill janitor-maintenance:
corre su script, compara con la ejecución anterior y entrega el informe en español.
Solo informe: no apliques ninguna corrección ni ejecutes comandos que cambien el sistema.
```

Manage — always list first, never guess the id (a name also works if unique):

| Action | Agent tool | CLI |
|---|---|---|
| List | `cronjob_manage(action="list")` | `janitor cron list` |
| Pause | `action="pause", job_id=…` | `janitor cron pause <id>` |
| Resume | `action="resume", job_id=…` | `janitor cron resume <id>` |
| Change cadence | `action="update", job_id=…, schedule="every day at 9am"` | `janitor cron edit <id> --schedule "0 9 * * 1"` |
| Change delivery | `action="update", job_id=…, deliver="local"` | `janitor cron edit <id> --deliver local` |
| Run now | `action="run", job_id=…` (background) | `janitor cron run <id>` (next tick) |
| Remove | `action="remove", job_id=…` | `janitor cron remove <id>` |
| History / health | — | `janitor cron runs <id>`, `janitor cron status`, `janitor cron doctor` |

Schedules (verified with `cron.jobs.parse_schedule`): `every monday 9am` (= `0 9 * * 1`),
`every day at 9am`, `every 7d` (interval from creation), or any 5-field cron such as
`0 9 1,15 * *`. `every 1d at 09:00` and `every 2w` are rejected. Times use the profile's
configured `timezone`, else the machine's local zone.

Delivery (`deliver`):
- Created from Telegram: omit it — it returns to that chat (`origin`).
- Created from the desktop app, TUI or CLI: those sessions record no origin. With
  `origin` the scheduler falls back to the first configured home channel
  (`TELEGRAM_HOME_CHANNEL`), else it only saves the output. So say it explicitly:
  `telegram` (home channel) when Telegram is set up, otherwise `local` — the report is
  then read in the app's scheduled-tasks view (run history opens the run's session) or
  under the profile's `cron/output/`.
- Do not use `bot-chat`: it feeds the report to the bot as a message to act on, which
  defeats report-only.

## Procedure

Setting up (interactive, on request):
1. Confirm cadence (default weekly, Monday 09:00 local), delivery target and whether
   the user wants silence when nothing changed. State that runs are report-only.
2. `cronjob_manage(action="list")`; if a `janitor-mantenimiento` job exists, update it
   instead of creating a duplicate.
3. Create the job as in Quick Reference, with `enabled_toolsets=["terminal"]`.
4. Optionally run `maintenance_run.py` once now so the first scheduled run already has
   a baseline. Report the job id, schedule and delivery target in Spanish.

Scheduled run (cron tick, nobody to ask):
1. Run `maintenance_run.py` (no flags). If it exits non-zero, answer with
   `[CRON_FAILURE]` alone on the first line, then the stderr reason.
2. Write the report in Spanish, at most ~25 lines, most severe first:
   - **Empeoró** (`worse`) and **Nuevo** (`new`): every entry, with evidence and fix.
   - **Corregido** (`fixed`): one line each.
   - **Sigue igual** (`still_open`): count per severity plus the `critical`/`high` titles.
   - **Sin verificar**: `not_verified` entries and `skipped` probes with the reason.
   - First run (`first_run: true`): say it is the baseline and list `critical`/`high`.
3. If the user asked for silence when nothing changed and `worse`, `new` and `fixed`
   are all empty, the whole answer is `[SILENT]`.
4. Do not fix anything, do not call `janitor-cleanup`, do not run `sudo`. Fixes are
   listed as suggestions for the user to confirm in an interactive session.

## Pitfalls

- Unattended safety: `approvals.cron_mode` defaults to `deny`, so a command the
  approval system flags as dangerous is blocked instantly in a cron run. It does not
  block every state-changing command — report-only rests on this skill, the prompt and
  `enabled_toolsets=["terminal"]`. Never set `cron_mode: approve` for this job.
- `--no-save` for ad-hoc runs; a saved ad-hoc run becomes the next baseline.
- Per-profile state: each profile has its own baseline and its own job.
- Delivered text is secret-redacted, but evidence can include paths and process names:
  route it to a chat the user owns.
- The audit's own limits (missing tools, unreadable journal) show up as
  `not_verified`/`skipped`; do not report them as fixed.

## Verification

- `janitor cron list` shows the job with the expected schedule and delivery.
- `python3 ${HERMES_SKILL_DIR}/scripts/maintenance_run.py --no-save` prints a diff JSON.
- After a fire: `janitor cron runs <id>` shows the run; the report arrived where
  `deliver` points.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_system_maintenance.py`.
