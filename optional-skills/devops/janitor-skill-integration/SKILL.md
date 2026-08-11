---
name: janitor-skill-integration
description: "Adopt local skills into the Janitor-Agent repo core."
version: 1.0.1
author: Carlos Cabra (reck74) + Janitor
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [skills, integration, janitor-agent, distribution, sanitization, devops]
    category: devops
    related_skills: [janitor-firecrawl, janitor-honcho, janitor-core, janitor-onboarding]
---

# janitor-skill-integration

Adopt operator-created skills from `~/.janitor/skills/` into the
Janitor-Agent repository so they ship to all installations via
`janitor update` → `sync_skills()` on every launch.

## When to Use (EXPLICIT ACTIVATION ONLY)

This skill MUST NOT activate automatically when a skill is being created or
modified. It activates ONLY on an explicit operator request to move a skill
into the central repo.

**Activation triggers — the operator must say something like:**
- "integrate this skill into the repo" / "add this skill to the core"
- "make this skill ship with janitor" / "ship this to all installations"
- "migrate this skill to the central repo"
- "agrega esta skill al repo" / "migra esta skill al core"
- Any phrase combining "this skill" + "repo/core/distribution/all installations"

**Do NOT activate for:**
- Creating a new user-local skill in `~/.janitor/skills/` (use `skill_manage`)
- Editing or patching an existing user-local skill
- General skill authoring questions (use `hermes-agent-skill-authoring`)
- Core Hermes skills (those ship with upstream — never modify)
- Skills under `optional-skills/` (different distribution path)
- Routine skill maintenance: updating versions, fixing typos, adding pitfalls
  to a skill that already lives in `~/.janitor/skills/`

## Distribution Mechanism (Verified)

The repo already has a skill distribution pipeline. No new infrastructure needed.

```
<repo>/skills/<category>/<name>/SKILL.md
  ↓  _discover_bundled_skills() — rglob("SKILL.md")
  ↓  sync_skills() — compares directory hashes
  ↓  copies on every janitor launch (hermes_cli/main.py:2465)
~/.janitor/skills/<category>/<name>/
```

- `sync_skills()` runs on EVERY `janitor` launch via
  `_sync_bundled_skills_quietly()` (hermes_cli/main.py:2465)
- It compares the directory hash of each bundled skill against the
  installed copy in `~/.janitor/skills/`
- If the hash changed (new files, modified content), it copies the full
  directory — including `scripts/`, `references/`, `templates/`
- `janitor update` does `git pull` + deps; the next launch propagates
- Category structure is preserved: `skills/devops/janitor-n8n/` →
  `~/.janitor/skills/devops/janitor-n8n/`
- A `.no-bundled-skills` marker file in HERMES_HOME opts out entirely

**Key insight:** the knowledge (SKILL.md) ships bundled and is visible to
the agent from first boot; the deploy of the service is explicit
(`bash ~/.janitor/skills/<category>/<name>/scripts/deploy.sh`).

## Directory Architecture Per Skill

Follow the pattern established by `janitor-firecrawl` and `janitor-honcho`:

```
skills/<category>/<skill-name>/
├── SKILL.md                  # Knowledge — always visible to agent
├── scripts/
│   ├── deploy.sh             # Idempotent deploy (generates creds, starts stack)
│   ├── <service>-compose.yml # Docker Compose definition
│   └── <helper>.sh           # Auth/pairing helpers as needed
└── references/
    └── *.md                  # API reference, extraction playbooks
```

SKILL.md points deploy commands to:
`~/.janitor/skills/<category>/<skill-name>/scripts/deploy.sh`

The sync pipeline places scripts there automatically after `janitor update`.

## Integration Procedure (7 Phases)

### Phase 0: Locate the Repo (CRITICAL — do this first)

The Janitor-Agent repo can live anywhere on disk. Never assume a path.
Find it dynamically before touching anything.

```bash
# Method 1: ask git where the running janitor binary's repo lives
JANITOR_REPO=$(python3 -c "
import pathlib, os
# Walk up from the janitor-core venv to find the repo root
p = pathlib.Path(os.environ.get('HERMES_HOME', os.path.expanduser('~/.janitor')))
# janitor-core symlink or .env might point to the repo
for candidate in [p / 'janitor-core', p / '.janitor-repo']:
    if candidate.is_symlink():
        print(candidate.resolve()); break
" 2>/dev/null)

# Method 2: search common locations
if [ -z "$JANITOR_REPO" ]; then
    for dir in \
        "$HOME/Projects/Janitor-Agent" \
        "$HOME/src/Janitor-Agent" \
        "$HOME/code/Janitor-Agent" \
        "$HOME/Janitor-Agent" \
        "$HOME/.janitor/janitor-core"; do
        if [ -d "$dir/.git" ] && [ -f "$dir/AGENTS.md" ]; then
            JANITOR_REPO="$dir"
            break
        fi
    done
fi

# Method 3: ask the user
if [ -z "$JANITOR_REPO" ]; then
    echo "Could not auto-detect the Janitor-Agent repo path."
    echo "Please provide the full path to your Janitor-Agent clone:"
    read -r JANITOR_REPO
fi

# Verify it's the right repo
if [ ! -f "$JANITOR_REPO/AGENTS.md" ] || [ ! -f "$JANITOR_REPO/janitor_cli.py" ]; then
    echo "ERROR: $JANITOR_REPO does not look like a Janitor-Agent repo"
    echo "       (missing AGENTS.md or janitor_cli.py)"
    exit 1
fi

echo "✓ Janitor-Agent repo: $JANITOR_REPO"
```

Verify the remote is correct (should point to `reck74/Janitor-Agent`):

```bash
cd "$JANITOR_REPO"
git remote -v | grep origin
# Expected: origin  https://github.com/reck74/Janitor-Agent.git (fetch)
```

**Why this matters:** the operator may have the repo at `~/Projects/`,
`~/src/`, `~/code/`, or even on a different disk. Subagents dispatched to
write files MUST receive the resolved `$JANITOR_REPO` path — never
hardcode a guess.

**Completion criterion:** `$JANITOR_REPO` is set, verified to contain
`AGENTS.md` + `janitor_cli.py`, and `git remote -v` shows the correct
origin. All subsequent phases use `$JANITOR_REPO` — never a hardcoded path.

### Phase 1: Survey

1. Identify the source skill in `~/.janitor/skills/`
2. Identify external scripts in `~/.janitor/docker/` that the skill references
   (setup scripts, compose files, auth helpers)
3. Inventory all files that need to be bundled
4. Check for the `test` job lists in `.github/workflows/tests.yml` and
   `.github/workflows/janitor-ci.yml` (directive #11 — new tests must be
   added to both in the same PR)

**Completion criterion:** you have a list of every source file and its
target destination in the repo.

### Phase 2: Branch

```bash
cd "$JANITOR_REPO"
git checkout -b feat/<descriptive-name>
```

### Phase 3: Port + Sanitize (parallel-safe via subagents)

For each skill, produce the target directory with sanitized files.

**Critical: scripts that live in `~/.janitor/docker/` must be bundled
inside the skill's `scripts/` directory.** A skill that references
external scripts that don't exist in a fresh clone is broken.

#### Sanitization rules (MANDATORY — repo is public on GitHub)

| Pattern to find | Replacement | Why |
|-----------------|-------------|-----|
| `/home/<operator>/...` | `${HERMES_HOME:-$HOME/.janitor}/...` or `SCRIPT_DIR`-relative | Machine-specific path |
| `<real-email>@<real-domain>` | `janitor@example.com` | Personal email |
| Hardcoded passwords (any string in clear) | `${ENV_VAR_NAME}` env reference | Credential leak |
| Real phone numbers (`57XXXXXXXXXX`) | `573001234567` (ITU example) | PII |
| Real WhatsApp group IDs (`120...@g.us`) | `120363000000000000@g.us` (synthetic) | PII |
| Real contact names / LIDs | Generic examples (`Maria Example`) | PII |
| Real dashboard usernames | `janitor` | PII |
| `172.17.0.1` or similar bridge IPs | Note about dynamic Docker gateway detection | Machine-specific |
| `~/Projects/<specific-project>/` | `<your-docs-project>/` or remove | Machine-specific |

**What stays as-is (correct conventions):**
- `~/.janitor` — fork convention (`janitor_cli.py:25` forces
  `HERMES_HOME=~/.janitor`)
- `127.0.0.1:PORT` — correct for loopback-only services
- Container names `janitor-*` — AGENTS.md directive #5
- Network names `janitor-*-network` — AGENTS.md directive #5

#### Script portability rules

In `deploy.sh`:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JANITOR_HOME="${HERMES_HOME:-$HOME/.janitor}"
COMPOSE_FILE="$SCRIPT_DIR/<service>-compose.yml"
ENV_FILE="$JANITOR_HOME/docker/<service>.env"
```

- NEVER hardcode `~/.janitor/docker/` as the compose source — the
  compose ships bundled in `scripts/`
- The env file (with generated credentials) stays in
  `~/.janitor/docker/` — `deploy.sh` generates it there
- The env file path is OK to reference from SKILL.md as
  `~/.janitor/docker/<service>.env`

In `<service>-compose.yml`:
- NEVER hardcode absolute paths in volume mount paths
- For bind mounts: use `deploy.sh` to resolve paths from `$JANITOR_HOME`
  and write the compose file, OR use named volumes instead of bind mounts
- Compose files do NOT expand `$ENV_VAR` in `volumes:` paths — use
  `deploy.sh` to sed-substitute or generate the compose at deploy time

#### Frontmatter rules

```yaml
---
name: janitor-<name>           # lowercase, hyphens
description: "<≤60 chars>"     # MUST be ≤60 chars per directive
version: 1.0.0
platforms: [linux]             # or [linux, macos]
metadata:
  hermes:
    tags: [...]
    category: devops
---
```

- `description` MUST be ≤60 characters (fork directive, stricter than
  upstream's 1024). Verify with a char count.
- Front-load the trigger: "Deploy and operate X for Janitor."

**Completion criterion:** every file written to the repo passes:
`bash -n` for shell, `yaml.safe_load` for YAML, `ast.parse` for Python,
and a `grep` sweep for all sanitization patterns returns zero hits.

### Phase 4: Test Registration (Directive #11)

If the PR introduces a new test file matching `tests/**/test_*janitor*.py`:

1. Read `.github/workflows/tests.yml` — find the `test` job's pytest list
2. Read `.github/workflows/janitor-ci.yml` — find the `python-tests` job
3. Add the new test file to BOTH lists in the same PR
4. Both lists must contain the exact same set of Janitor test files

**Failure to do this** = the test runs locally but CI silently skips it.

**Completion criterion:** both workflow files list the new test file.

### Phase 5: Verify

```bash
# Syntax checks (loop so every file is actually checked — globs in
# `python3 -c`/`docker compose -f` are NOT expanded by those tools)
SKILL_DIR="$JANITOR_REPO"/skills/<category>/<name>
for f in "$SKILL_DIR"/scripts/*.sh; do
    [ -f "$f" ] && bash -n "$f"
done
for f in "$SKILL_DIR"/scripts/*.py; do
    [ -f "$f" ] && "$JANITOR_REPO"/.venv/bin/python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$f"
done
for f in "$SKILL_DIR"/scripts/*-compose.yml "$SKILL_DIR"/scripts/*.yml; do
    [ -f "$f" ] && docker compose -f "$f" config --quiet
done

# Sanitization sweep (MUST return zero)
grep -rE '/home/<operator>|airp\.ws|Jan1t0r|573012553871|12036342|<operator-name>[^-]' \
  "$JANITOR_REPO"/skills/<category>/<name>/ && echo "FAIL" || echo "PASS"

# Frontmatter validation
"$JANITOR_REPO"/.venv/bin/python3 -c "
import yaml, re, pathlib
c = pathlib.Path('$JANITOR_REPO/skills/<category>/<name>/SKILL.md').read_text()
m = re.search(r'^description:\s*\"?(.*?)\"?\s*\$', c, re.MULTILINE)
assert len(m.group(1)) <= 60, f'{len(m.group(1))} chars > 60'
print(f'description: {len(m.group(1))} chars OK')
"

# Tests (canonical runner — NOT pytest directly)
cd "$JANITOR_REPO"
scripts/run_tests.sh tests/skills/test_<name>_skill.py -v
```

**Completion criterion:** all checks pass, zero contamination found.

### Phase 6: Commit

```bash
cd "$JANITOR_REPO"
git add skills/<category>/<name>/ tests/ .github/workflows/
git commit -m "feat(skills): integrate <skill-name> into core

<description of what was added>

Sanitization: <summary of what was scrubbed>
Distribution: sync_skills() on every janitor launch
"
```

## Common Pitfalls

1. **Auto-activating during normal skill creation.** This is the #1 risk.
   The skill's description contains "skills" and "repo" — words that appear
   in normal skill-authoring conversations. The skill MUST NOT be loaded
   when the user simply asks to create, edit, or improve a skill. It
   activates ONLY when the user explicitly asks to move/integrate/migrate
   a skill into the central repo. If in doubt, ask "do you want me to
   ship this to the repo, or just create it locally?"

2. **Assuming the repo path.** The Janitor-Agent repo can live at any path
   on any machine. Always run Phase 0 to detect `$JANITOR_REPO` dynamically.
   Subagents must receive the resolved path — never guess
   `/home/<operator>/Projects/Janitor-Agent`.

3. **Forgetting to bundle scripts.** A skill that references
   `~/.janitor/docker/setup-X.sh` is broken in any clone that doesn't have
   that file. Bundle ALL executable scripts inside `scripts/`.

4. **`***` masking breaks scripts.** When sanitizing `$API_KEY` out of
   examples, do NOT replace with literal `***` in executable shell scripts —
   it breaks quoting (`"X-Api-Key: *** "$URL` has unbalanced quotes).
   Replace with the env var reference: `$WAHA_API_KEY`.
   In SKILL.md documentation blocks, `$WAHA_API_KEY` is also correct —
   it shows the reader the actual variable to use.

5. **Compose bind mounts with absolute paths.** Docker Compose does NOT
   expand `$HERMES_HOME` in `volumes:` paths. Either use named volumes
   (preferred) or have `deploy.sh` generate the compose file with
   resolved absolute paths.

6. **Description > 60 chars.** The fork enforces ≤60 (stricter than
   upstream's 1024). Long descriptions are caught by the skill validator
   and by CI. Count characters before committing.

7. **Missing directive #11 registration.** A new `test_*janitor*.py` that
   isn't in both `tests.yml` and `janitor-ci.yml` runs locally but is
   invisible to CI. Always update both in the same commit.

8. **Hardcoded `172.17.0.1` gateway.** The Docker bridge IP varies across
   hosts (Docker Desktop uses different ranges, custom daemon.json changes
   the subnet). Use `host.docker.internal:host-gateway` in `extra_hosts:`
   instead, or document the dependency on a specific network.

9. **Leaving real PII in reference docs.** A `references/contacts-and-groups.md`
   built from a real audit contains real phone numbers, group IDs, and
   contact names. These MUST be replaced with synthetic examples before
   committing to a public repo.

10. **Not running the canonical test runner.** Direct `pytest` invocation
    diverges from CI (missing TZ=UTC, env var contamination, no per-file
    isolation). Always use `scripts/run_tests.sh`.

11. **Expecting the current session to see the new skill.** The skill loader
    is cached at session start. The new skill is visible in the next
    `janitor` launch (or next `sync_skills()` call).

## Verification Checklist

- [ ] `$JANITOR_REPO` detected dynamically (Phase 0), verified `AGENTS.md` + `janitor_cli.py` present
- [ ] `git remote -v` shows `reck74/Janitor-Agent` as origin
- [ ] Source files inventoried (SKILL.md + scripts + references)
- [ ] Branch created: `feat/<descriptive-name>`
- [ ] All scripts bundled inside `skills/<category>/<name>/scripts/`
- [ ] `deploy.sh` uses `SCRIPT_DIR` + `JANITOR_HOME` (no hardcoded paths)
- [ ] Compose files use named volumes or deploy.sh-generated paths
- [ ] Frontmatter: `description` ≤ 60 chars, `platforms` present
- [ ] Sanitization sweep: `grep -rE '/home/<operator>|...' ` returns zero
- [ ] `bash -n` passes on all `.sh` files
- [ ] `yaml.safe_load` passes on all `.yml` files
- [ ] `ast.parse` passes on all `.py` files
- [ ] No `***` masks in executable code (only in prose comments)
- [ ] Test file (if any) added to BOTH `tests.yml` and `janitor-ci.yml`
- [ ] `scripts/run_tests.sh tests/skills/test_<name>_skill.py` passes
- [ ] Commit message follows `feat(skills): integrate ...` format

## Reference: Existing Bundled Skill Patterns

| Skill | Category | Scripts | Deploy Pattern |
|-------|----------|---------|----------------|
| `janitor-firecrawl` | root | `scripts/deploy.sh` + `scripts/firecrawl-compose.yml` | `bash ~/.janitor/skills/janitor-firecrawl/scripts/deploy.sh` |
| `janitor-honcho` | root | `scripts/honcho-compose.yml` | `bash ~/.janitor/skills/janitor-honcho/scripts/deploy.sh` |
| `janitor-n8n` | devops | `scripts/{deploy.sh, n8n-compose.yml, n8n-auth.sh}` | `bash ~/.janitor/skills/devops/janitor-n8n/scripts/deploy.sh` |
| `janitor-lightrag` | devops | `scripts/{deploy.sh, lightrag-compose.yml}` | `bash ~/.janitor/skills/devops/janitor-lightrag/scripts/deploy.sh` |
| `janitor-waha` | devops | `scripts/{deploy.sh, pair-waha.sh, waha-compose.yml, diff-waha-group.py}` | `bash ~/.janitor/skills/devops/janitor-waha/scripts/deploy.sh` |
| `janitor-nocodb` | devops | `scripts/{deploy.sh, nocodb-compose.yml}` | `bash ~/.janitor/skills/devops/janitor-nocodb/scripts/deploy.sh` |

Root-level (`skills/janitor-*/`) is for skills that are meta-operational
to the fork itself (core, onboarding, honcho, firecrawl). Category-level
(`skills/devops/janitor-*/`) is for domain-specific service skills.

## See Also

- AGENTS.md directives #3 (skills isolated), #5 (naming), #11 (test pruning)
- `tools/skills_sync.py` — the sync pipeline source code
- `hermes_cli/main.py:2465` — `_sync_bundled_skills_quietly()` call site
- Skill `hermes-agent-skill-authoring` — general in-repo skill authoring
- Skill `janitor-onboarding` — orientation and capability selector
