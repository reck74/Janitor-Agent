---
name: janitor-config-audit
description: Use when comparing active config.yaml or SOUL.md against janitor-core assets to detect drift, or when applying upstream updates. Runs a diff-and-patch audit with YAML validation and automatic backup.
version: 1.2.0
author: janitor
license: MIT

metadata:
  hermes:
    tags: [config, audit, drift, janitor, maintenance]
    related_skills: [hermes-agent-skill-authoring]
---

# Janitor Config Audit

## Overview

Compara los archivos de configuracion activos (`~/.janitor/config.yaml`, `~/.janitor/SOUL.md`) contra las versiones master en `janitor-core/assets/janitor/`. Reporta diferencias y permite aplicar updates de forma selectiva o automatica.

## When to Use

- User asks to "check for updates" or "sync config with upstream"
- After a Janitor install or update to verify what changed
- When the user wants to know if their active config drifted from the janitor-core asset

## How to Use

The script supports two invocations:

1. **Slash command** (may fail on WSL — see Platform Note below)
2. **Direct terminal** (always works)

```bash
# Dry-run: solo reporte
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py

# Target especifico: config | soul | all (default)
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py config
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py soul

# Aplicar todas las diferencias automaticamente
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py --apply

# Aplicar target especifico
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py config --apply
python3 ~/.janitor/skills/janitor-config-audit/scripts/audit.py soul --apply
```

## Formato de diferencias

| Symbol | Meaning |
|---|---|
| `+` | Solo existe en el asset (falta en activo) |
| `-` | Solo existe en el activo (no existe en asset) |
| `~` | Valor diferente en ambos |

## Security

- La aplicacion crea backup `.bak` antes de modificar
- Valida YAML tras aplicacion; si esta malformado restaura el backup automaticamente
- SOUL.md usa diff de texto plano (no YAML flatten)

## Platform Note

The slash command (`/janitor-config-audit`) may fail with "Failed to load skill" on WSL or non-standard Linux environments due to a platform-check inconsistency in Hermes (the scan phase and the load phase apply `skill_matches_platform()` independently, and the gates can disagree). **If the slash command fails, invoke the script directly via terminal.** The script itself has no platform restrictions.

## Common Pitfalls

1. **Slash command fails with "not supported on this platform".** This is a Hermes internal bug — not a problem with the skill or script. Invoke via terminal instead.

2. **YAML malformado tras aplicacion.** El script detecta el error y restaura el backup automaticamente — no pierdes datos.

3. **Muchas diferencias detectadas.** Aplicar una por una (`config --apply` o `soul --apply`) para mantener visibilidad sobre cada cambio.

## Archivos comparados

| Archivo activo | Asset master |
|---|---|
| `~/.janitor/config.yaml` | `~/.janitor/janitor-core/assets/janitor/config.yaml` |
| `~/.janitor/SOUL.md` | `~/.janitor/janitor-core/assets/janitor/SOUL.md` |

## Verification Checklist

- [ ] El diff reportado es esperado (revisar cada cambio antes de aplicar)
- [ ] Backup `.bak` existe antes de aplicar
- [ ] YAML valido tras aplicacion (script lo valida automaticamente)
- [ ] Sesion de Janitor puede leer la nueva config