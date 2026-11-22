---
name: janitor-system-health
description: "Read-only Linux health audit with prioritised findings."
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux]

metadata:
  hermes:
    tags: [system, health, audit, linux, security, disks, backups, systemd]
    category: devops
    related_skills: [janitor-maintenance, janitor-cleanup]
---

# Janitor System Health Skill

Audits the user's Linux machine and returns a prioritised list of findings: disks,
memory, load, systemd units, updates, kernel, SMART, filesystem errors, time sync,
exposed ports, firewall, SSH, permissions of sensitive files, backups and Docker. The
audit is strictly read-only: it never calls `sudo`, never changes state and writes
nothing unless asked to save its JSON. It does not fix anything — fixes are proposed,
confirmed by the user and executed through the right skill or command.

## When to Use

- "How is my machine doing?", "audit this box", "why is it slow / full / noisy?"
- Before a risky change (upgrade, migration) to get a baseline.
- When `janitor-maintenance` asks for the current state.

Not for: freeing space (`janitor-cleanup`), scheduled reports (`janitor-maintenance`),
remote hosts (this audits the machine the agent's `terminal` runs on).

## Prerequisites

- Linux with Python 3.10+ (stdlib only). systemd distros give the most coverage.
- Optional tools, each detected on `PATH` and skipped when missing: `df`, `ps`,
  `systemctl`, `journalctl`, `timedatectl`, `ss`, `sshd`, `smartctl`, `docker`,
  `pacman` / `apt` / `dnf`, `arch-audit`, `needs-restarting`, `crontab`, `lsblk`,
  `ufw` / `firewall-cmd` / `nft` / `iptables`.
- No privileges. Whatever needs root is reported with `requires_privileges: true`
  and the exact command the user can run.

## How to Run

Run the script with the `terminal` tool:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/system_health.py
```

- stdout: one JSON document. stderr: one progress line per probe (Spanish).
- `--only disk,ssh` / `--skip docker,home_usage` restrict probes (`--list-probes`).
- `--home-budget 20` caps the seconds spent measuring the home directory.
- `--output FILE` also writes the JSON to FILE (the only write it ever does).
- Exit code is 0 whatever it finds; non-zero only on bad arguments or an
  unwritable `--output`.

A full run takes 5–40 s (the home scan and `docker system df` dominate).

## Quick Reference

Report schema (`schema_version: 1`):

| Key | Content |
|---|---|
| `findings[]` | `id` (`<probe>:<key>`, stable across runs), `probe`, `severity` (`critical`/`high`/`medium`/`low`/`info`), `area`, `title`, `evidence` (raw quote), `suggested_fix` (command or step), `requires_privileges` |
| `skipped[]` | `probe` (or `probe.part`) and `reason` — tool missing, no permission, daemon down |
| `probes` | probe → `ok` / `skipped` / `error` |
| `summary` | count per severity |
| `system` | OS name/id, kernel, whether it ran as root |

Probes: `disk` (space + inodes per device), `home_usage` (top consumers, `~/.cache`,
trash), `memory` (available RAM, swap, PSI), `load` (load vs cores, top processes),
`systemd_units` (failed, system + user), `unit_flapping` (restart loops, 24 h),
`updates` (pending, security where the distro exposes it, reboot required, stale
metadata), `kernel` (version, uptime), `smart`, `fs_errors` (kernel log, 7 days),
`time_sync`, `firewall`, `listening_ports` (bound to all interfaces, per process),
`ssh` (password auth, root login), `permissions` (`~/.ssh`, keys, `~/.gnupg`, rc files,
world-writable files in config/bin dirs), `backups` (any evidence), `docker`
(`docker system df`, dangling images, stopped containers).

## Procedure

1. Run the script. If the user named an area, use `--only` with the matching probes.
2. Parse the JSON. Do not re-run probes by hand to "double check" unless a finding is
   ambiguous; the evidence field is the quote.
3. Report to the user **in Spanish**, in this order:
   - One line with the totals per severity.
   - Findings from most to least severe (`critical` → `low`). For each: title, the
     evidence quoted verbatim (trim long blocks, never paraphrase numbers), and the
     concrete fix from `suggested_fix`. Mark the ones with `requires_privileges`.
   - `info` findings condensed into a short context block (kernel, top processes, home
     consumers, backup evidence).
   - Every entry of `skipped[]` with its reason, stated as "not checked" — never as
     "fine". If SMART, security updates or the system journal were not readable, say
     what could not be verified and the command that would verify it.
4. Never invent findings, thresholds or evidence that are not in the JSON. If the
   report is empty apart from `info`, say so and stop.
5. Offer fixes; do not apply them. Any fix that changes the system needs the user's
   explicit confirmation of that specific action, and goes through the owning tool:
   - space, caches, trash, Docker images/containers/build cache → `janitor-cleanup`
     (shows what it will remove and uses the trash);
   - privileged commands (package upgrades, firewall, sshd, `systemctl` on system
     units, SMART) → give the exact command for the user to run; run it through
     `terminal` only if the user explicitly asks, after showing it;
   - Docker volumes hold data: list them, never prune volumes in bulk.
6. If the user wants this to recur, hand over to `janitor-maintenance`.

## Pitfalls

- A missing tool or denied permission is a gap in the audit, not a clean result.
- `ps` `%CPU` is the average since the process started, not current load.
- `pacman -Qu` and `apt list --upgradable` read local metadata; the `stale-metadata`
  finding says when that list may be incomplete. The audit never refreshes it (that
  writes to disk and needs the network).
- Listening ports owned by other users show "proceso no visible sin privilegios";
  `sudo ss -tulpn` shows the owner.
- sshd settings come from `sshd -T` when readable, else from parsing
  `/etc/ssh/sshd_config` + `Include` (global section only, up to the first `Match`).
  Treat a parsed verdict as the configuration on disk, not proof of the running daemon.
- `backups:snapshots-only` is deliberate: snapshots on the same disk are not a backup.

## Verification

- `python3 ${HERMES_SKILL_DIR}/scripts/system_health.py --quiet | python3 -m json.tool`
  prints valid JSON and exits 0.
- `--list-probes` lists the probes above.
- Tests: `scripts/run_tests.sh tests/janitor/test_janitor_system_health.py`.
