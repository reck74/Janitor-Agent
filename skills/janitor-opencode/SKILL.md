---
name: janitor-opencode
description: "Explicit health check for an optional OpenCode server."
version: 1.0.0
author: Janitor Contributors
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [opencode, optional, experimental]
    category: software-development
---

# OpenCode opcional

Cliente HTTP conservado del fork y consolidado en una sola implementación. Es una integración experimental, fuera del arranque base; no inicia servidores, registra herramientas en el core ni instala OpenCode automáticamente.

Con un servidor OpenCode configurado explícitamente, comprueba su endpoint:

```bash
janitor --run-module janitor_ext.optional_deploy skills/janitor-opencode/scripts/health.sh --port 3000
```

Usa el puerto real de tu servidor. La contraseña opcional se lee de `OPENCODE_SERVER_PASSWORD` del perfil; no se pasa como argumento. El chequeo sólo consulta `/global/health` y falla con salida no cero ante errores. No crea sesiones ni envía prompts.

Para desarrollo, `scripts/client.py` conserva `OpenCodeOrchestrator`; úsalo desde esta skill. Las antiguas copias bajo `agent/` y `tools/` fueron retiradas. El gestor de sesiones y el router experimental están archivados en `legacy/prototypes/`; no forman parte de esta integración. Los proveedores OpenCode/ACP actuales de Hermes permanecen disponibles mediante sus propias interfaces upstream.
