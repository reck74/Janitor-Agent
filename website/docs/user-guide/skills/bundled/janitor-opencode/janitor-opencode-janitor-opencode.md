---
title: "Janitor Opencode — Explicit health check for an optional OpenCode server"
sidebar_label: "Janitor Opencode"
description: "Explicit health check for an optional OpenCode server"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Opencode

Explicit health check for an optional OpenCode server.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-opencode` |
| Version | `1.0.0` |
| Author | Janitor Contributors |
| License | MIT |
| Platforms | linux, macos |
| Tags | `opencode`, `optional`, `experimental` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# OpenCode opcional

Cliente HTTP conservado del fork y consolidado en una sola implementación. Es una integración experimental, fuera del arranque base; no inicia servidores, registra herramientas en el core ni instala OpenCode automáticamente.

Con un servidor OpenCode configurado explícitamente, comprueba su endpoint:

```bash
janitor --run-module janitor_ext.optional_deploy skills/janitor-opencode/scripts/health.sh --port 3000
```

Usa el puerto real de tu servidor. La contraseña opcional se lee de `OPENCODE_SERVER_PASSWORD` del perfil; no se pasa como argumento. El chequeo sólo consulta `/global/health` y falla con salida no cero ante errores. No crea sesiones ni envía prompts.

Para desarrollo, `scripts/client.py` conserva `OpenCodeOrchestrator`; úsalo desde esta skill. Las antiguas copias bajo `agent/` y `tools/` fueron retiradas. El gestor de sesiones y el router experimental están archivados en `legacy/prototypes/`; no forman parte de esta integración. Los proveedores OpenCode/ACP actuales de Hermes permanecen disponibles mediante sus propias interfaces upstream.
