# Janitor Restructuring v5 — Minimal Installer + Optional Skills

## Summary

The Janitor installer has been restructured from a monolithic full-stack deployment
(Infisical + Honcho + Firecrawl + Playwright + AgentMemory) to a minimal first-run
model where only the agent identity, configuration, and optional Honcho memory are
deployed by default. All additional services become opt-in skills installed post-first-run.

## What Changed

### Installer (`scripts/janitor-install.sh`)

- **Before**: asked for Firecrawl API key, checked Infisical health, called
  `setup-stack.sh` which deployed Infisical + Honcho + Firecrawl + systemd + vault
  bootstrap.
- **After**: asks only for `OPENAI_API_KEY` and `MINIMAX_API_KEY`, then offers three
  Honcho modes:
  1. Cloud — user provides `HONCHO_API_KEY`.
  2. Local — runs `setup-honcho.sh` to deploy Honcho Docker only.
  3. Skip — no memory configured; user installs `janitor-honcho` skill later.
- No longer calls `setup-stack.sh`.
- No longer asks for `FIRECRAWL_API_KEY`.
- No longer probes Infisical.

### Runtime (`janitor_cli.py`)

- **Before**: auto-loaded secrets from Infisical CLI at startup; if Infisical was
  missing, fell back to `~/.janitor/.env`. Hardcoded `JANITOR_SOUL` string was
  monkey-patched into `prompt_builder.load_soul_md`, overriding any local
  `SOUL.md`.
- **After**: loads only `~/.janitor/.env`. Reads `~/.janitor/SOUL.md` if it exists
  and uses it as the canonical persona source. If missing, falls back to the
  original Hermes soul loader. Removed forced `DEFAULT_CONFIG` overrides for
  memory and skin — uses `setdefault` so installed `config.yaml` remains
  authoritative.

### Stack Orchestrator (`scripts/setup-stack.sh`)

- Marked as **legacy** with a deprecation header.
- Still available for users who need the old full-stack behavior, but not called
  by the default installer.

### New Scripts

- `scripts/setup-honcho.sh` — minimal Honcho-only Docker deployer.
- `scripts/migrate-janitor-minimal.sh` — migration helper for existing installs.

### Skills Restructuring

`skills/janitor-onboarding/` used to deploy 5 Docker services. It is now an
orientation guide that lists available skills.

New skills extracted:

| Skill | Contents | Former Location |
|-------|----------|-----------------|
| `skills/janitor-honcho/` | `SKILL.md`, `honcho-compose.yml` | `setup-stack.sh` (Honcho block) |
| `skills/janitor-vault/` | `SKILL.md`, Infisical compose, `vault-bootstrap.sh`, `load-infisical-secrets.sh` | `scripts/vault-bootstrap.sh`, `scripts/load-infisical-secrets.sh` |
| `skills/janitor-firecrawl/` | `SKILL.md`, `firecrawl-compose.yml` | `setup-stack.sh` (Firecrawl block) |
| `skills/janitor-browser/` | `SKILL.md`, `install.sh` (Playwright) | `scripts/bootstrap.sh` |
| `skills/janitor-agentmemory/` | `SKILL.md`, `deploy.sh` | `setup-stack.sh` (AgentMemory block) |

## Migration for Existing Users

If you installed Janitor before this change and are running the full stack:

1. **Backup**: run `bash scripts/migrate-janitor-minimal.sh`. It backs up
   `~/.janitor/.env`, `config.yaml`, `SOUL.md`, and offers to export Infisical
   secrets into `.env`.
2. **Clean shell RC**: the migration script detects and optionally removes
   `load-infisical-secrets.sh` source lines from `~/.bashrc` / `.zshrc`.
3. **Preserve Docker volumes**: the script never deletes volumes. If you want to
   stop old services, run:
   ```bash
   cd ~/.janitor/docker
   docker compose -f docker-compose.yml down
   docker compose -f firecrawl-compose.yml down
   docker compose -f honcho-compose.yml down
   ```
4. **Install skills as needed**: if you still want Infisical or Firecrawl, install
   their respective skills from `skills/janitor-vault/` and `skills/janitor-firecrawl/`.

## Fresh Install Workflow

```bash
curl -fsSL https://raw.githubusercontent.com/reck74/Janitor-Agent/main/scripts/bootstrap.sh | bash
```

This clones the repo, installs Python deps, and runs `janitor-install.sh`, which now:

1. Creates `~/.janitor` with `.env`, `config.yaml`, `SOUL.md`, skin.
2. Optionally deploys Honcho local.
3. Prints a message listing optional skills.

Then:

```bash
janitor
```

The agent starts with persona, skin, and memory configured. Additional capabilities
are added by installing skills.

## Philosophy

- **First run should not fail** because Docker, Infisical, or Firecrawl are unavailable.
- **Skills are the expansion mechanism** — updates ship new skills; users opt in.
- **Hermes core remains untouched** — all Janitor changes stay in wrapper files,
  scripts, and `skills/janitor-*`.
